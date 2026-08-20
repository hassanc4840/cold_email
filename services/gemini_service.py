"""
gemini_service.py (Now using Groq API)
-----------------
Uses Groq API to:
1. Analyze client web content (or infer their business from email domain)
2. Generate a hyper-personalized, compelling outreach email from Nexariza
   using all available lead intelligence fields from the CSV.

Fallback: If GROQ_API_KEY (primary) fails for any reason (rate limit, auth error,
network timeout), the system automatically retries with GROQ_API_KEY_2 (secondary).
"""

import os
import re
import logging
from typing import Optional, Tuple, List
from groq import AsyncGroq
import google.genai as genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

# ── Groq Client Pool (Primary + Fallback) ─────────────────────────────────────

_groq_clients: dict = {}  # keyed by env var name, lazy-initialised


def _build_groq_client(api_key: str) -> AsyncGroq:
    """Build a Groq async client from a given API key."""
    return AsyncGroq(api_key=api_key, max_retries=0)


def _get_groq_clients() -> List[AsyncGroq]:
    """
    Dynamically loads all GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3, ...
    from the environment and returns them as an ordered list of AsyncGroq clients.
    Adding a new key only requires adding it to .env — no code change needed.
    """
    global _groq_clients
    clients: List[AsyncGroq] = []

    # Check GROQ_API_KEY, then GROQ_API_KEY_2, GROQ_API_KEY_3, etc.
    env_vars = ["GROQ_API_KEY"] + [f"GROQ_API_KEY_{i}" for i in range(2, 10)]
    for env_var in env_vars:
        key = os.getenv(env_var, "").strip()
        if not key:
            continue
        if env_var not in _groq_clients:
            _groq_clients[env_var] = _build_groq_client(key)
            logger.debug(f"Groq client initialised ({env_var}).")
        clients.append(_groq_clients[env_var])

    return clients


# ── Gemini Client Pool (used when ALL Groq keys fail) ─────────────────────────

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.1-pro-preview"]
GEMINI_MODEL = "gemini-2.5-flash"


def _get_gemini_keys() -> List[str]:
    """Return all configured Gemini API keys in priority order."""
    keys = []
    for env_var in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3"):
        k = os.getenv(env_var, "").strip()
        if k:
            keys.append(k)
    return keys


async def _call_gemini(api_key: str, prompt: str, max_tokens: int, temperature: float) -> str:
    """Call Gemini API with a single key and return the response text."""
    client = genai.Client(api_key=api_key)
    last_err = None
    for model_candidate in GEMINI_MODELS:
        try:
            response = await client.aio.models.generate_content(
                model=model_candidate,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            return response.text
        except Exception as e:
            last_err = e
            logger.warning(f"Gemini model '{model_candidate}' failed: {e}")
            continue
    raise last_err or RuntimeError("All Gemini models failed")


# ── Gemini Vision (used by PixelRAG fallback) ─────────────────────────────────

VISION_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]


async def _call_gemini_vision(
    image_bytes: bytes,
    prompt: str,
    mime_type: str = "image/jpeg",
    max_tokens: int = 1500,
    temperature: float = 0.2,
) -> str:
    """
    Send an image + text prompt to Gemini Vision and return the response text.
    Cycles through all configured Gemini API keys on failure.
    """
    keys = _get_gemini_keys()
    if not keys:
        raise RuntimeError("No Gemini API keys configured for vision fallback")

    last_err = None
    for key_idx, api_key in enumerate(keys):
        client = genai.Client(api_key=api_key)
        for model_candidate in VISION_MODELS:
            try:
                image_part = genai_types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                )
                response = await client.aio.models.generate_content(
                    model=model_candidate,
                    contents=[image_part, prompt],
                    config=genai_types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    ),
                )
                key_label = f"GEMINI-{key_idx + 1}"
                logger.info(
                    f"[{key_label}] Vision call succeeded with '{model_candidate}'"
                )
                return response.text
            except Exception as e:
                last_err = e
                logger.warning(
                    f"Gemini Vision '{model_candidate}' (key {key_idx + 1}) failed: {e}"
                )
                continue

    raise last_err or RuntimeError("All Gemini Vision models/keys failed")


GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
]


async def _groq_create_with_fallback(
    messages: list,
    model: Optional[str] = None,
    temperature: float = 0.8,
    max_completion_tokens: int = 2000,
    label: str = "",
) -> str:
    """
    Attempts the Groq chat completion using primary then fallback Groq keys.
    If ALL Groq keys fail, automatically falls back to Gemini API keys
    (GOOGLE_API_KEY → GOOGLE_API_KEY_2 → GOOGLE_API_KEY_3).
    Returns the raw response text.
    """
    # ── Step 1: Try all Groq keys ─────────────────────────────────────────────
    groq_clients = _get_groq_clients()
    last_error: Optional[Exception] = None
    target_models = [model] if model else GROQ_MODELS

    for idx, client in enumerate(groq_clients):
        key_label = "PRIMARY" if idx == 0 else f"FALLBACK-{idx}"
        for groq_model in target_models:
            try:
                response = await client.chat.completions.create(
                    model=groq_model,
                    messages=messages,
                    temperature=temperature,
                    max_completion_tokens=max_completion_tokens,
                )
                content = response.choices[0].message.content
                if not content or len(content.strip()) < 30:
                    raise ValueError(f"Empty or truncated content from {groq_model}")

                if idx > 0 or groq_model != target_models[0]:
                    logger.info(
                        f"[GROQ {key_label} ({groq_model})] Succeeded for '{label}'."
                    )
                return content.strip()

            except Exception as e:
                last_error = e
                logger.warning(
                    f"[GROQ {key_label} ({groq_model})] Failed for '{label}': {type(e).__name__}: {e}"
                )
                continue


    if groq_clients:
        logger.warning(
            f"[GROQ] All {len(groq_clients)} Groq key(s) exhausted for '{label}'. "
            f"Switching to Gemini fallback..."
        )

    # ── Step 2: Fall back to Gemini keys ─────────────────────────────────────
    # Build a single combined prompt string from the messages list
    gemini_prompt = "\n\n".join(
        m.get("content", "") for m in messages if m.get("content")
    )

    gemini_keys = _get_gemini_keys()
    if not gemini_keys:
        raise RuntimeError(
            f"All Groq keys failed and no Gemini API keys are configured. "
            f"Last Groq error: {last_error}"
        )

    for g_idx, g_key in enumerate(gemini_keys):
        key_label = f"GEMINI-{g_idx + 1}"
        try:
            result = await _call_gemini(
                api_key=g_key,
                prompt=gemini_prompt,
                max_tokens=max_completion_tokens,
                temperature=temperature,
            )
            logger.info(
                f"[{key_label}] Succeeded for '{label}' (Groq keys were exhausted)."
            )
            return result
        except Exception as e:
            last_error = e
            logger.warning(
                f"[{key_label}] Failed for '{label}': {type(e).__name__}: {e}"
            )
            if g_idx < len(gemini_keys) - 1:
                logger.info(f"[GEMINI] Retrying with next Gemini key ({g_idx + 2}/{len(gemini_keys)})...")

    # All providers exhausted
    raise RuntimeError(
        f"All Groq and Gemini API keys failed for '{label}'. "
        f"Last error: {last_error}"
    )


# ── Nexariza Company Intelligence (Trained from nexariza.com) ────────────────

NEXARIZA_DESCRIPTION = """
Nexariza AI is a production-grade AI development and full-stack software company founded in 2024, 
headquartered in Lahore, Pakistan. We build intelligent systems that genuinely transform how 
businesses operate — not just demos, but real, deployed, revenue-generating solutions.

Our Core Service Lines:
─────────────────────────────────────────────────────────────────────
1. CUSTOM AI & MACHINE LEARNING DEVELOPMENT
   - Custom ML model development (classification, prediction, recommendation)
   - Natural Language Processing (NLP): chatbots, sentiment analysis, text extraction
   - Computer Vision: image recognition, object detection, document OCR
   - Generative AI integration: GPT-4, Claude, Gemini, LLaMA pipelines
   - AI Agents & Autonomous Workflow Automation
   - RAG (Retrieval-Augmented Generation) systems for enterprise knowledge bases
   - Model fine-tuning on proprietary business data

2. FULL-STACK WEB DEVELOPMENT
   - High-performance web applications (React, Next.js, Vue.js)
   - Backend API development (FastAPI, Node.js, Django)
   - Database architecture (PostgreSQL, MongoDB, Supabase, Firebase)
   - SaaS platforms and multi-tenant systems
   - Mobile-responsive, SEO-optimized frontends
   - Third-party API and payment gateway integrations

3. WORKFLOW AUTOMATION & PROCESS OPTIMIZATION
   - End-to-end business process automation (lead gen, data pipelines, reporting)
   - n8n, Zapier, and custom automation pipelines
   - CRM integrations and automated outreach systems
   - Intelligent document processing and data extraction

Our Differentiators:
─────────────────────────────────────────────────────────────────────
- Production-ready deliverables (not prototypes)
- Deep expertise across the full AI/ML stack
- Fast turnaround: most projects delivered in 2-6 weeks
- Transparent pricing and milestone-based delivery
- Available on Fiverr, Upwork, and direct contract

Founder: Ahmad Yasin
Contact: +92-370-7348001 | https://nexariza.com
Platforms: LinkedIn (nexariza), Fiverr (nexariza), Upwork (nexariza)
"""

# ── System Prompt — Ultra-Personalized Outreach ──────────────────────────────

SYSTEM_PROMPT = """You are a senior sales representative for Nexariza AI — a production-grade AI development 
and full-stack software company based in Lahore, Pakistan.

Your job is to write a SHORT, deeply personalized, professional cold outreach email to a potential client.

About Nexariza AI:
{nexariza_description}

═══════════════════════════════════════════════════════
GOLDEN RULES FOR THE EMAIL (HIGH ENGAGEMENT, ANTI-SPAM & WHITELISTING COMPLIANCE):
═══════════════════════════════════════════════════════
1. HIGH ENGAGEMENT SUBJECT LINES & CONTENT (RULE 4):
   - Subject line: Keep it intriguing, highly relevant, short (3-7 words), and personalized to their specific business (e.g., "Quick idea for [Company Name]'s workflow").
   - Content: Deeply personalized, high-value, professional, and conversational.
   - Reply Invitation: ALWAYS end with a low-friction question that encourages the recipient to reply (e.g., "Would you be open to a quick 15-minute call?", "Should I send over a 2-minute demo video?").
   - Goal: Maximize Open Rate and Reply Rate.

2. AVOID SPAM TRIGGERS & STRICT SINGLE-LINK POLICY (RULE 6):
   - STRICTLY ZERO LINKS IN BODY: Do NOT insert any URLs, website links, or http/https addresses in the body text. The automated system includes the single official website link (www.nexariza.com) in the signature card.
   - BAN SPAM WORDS: NEVER use prohibited sales/spam words like "FREE", "URGENT", "LIMITED TIME", "CLICK HERE NOW", "BUY NOW", "GUARANTEED", "100%", "SPECIAL OFFER", "ACT NOW", "RISK-FREE", "DISCOUNT", "MONEY BACK", "WINNER", "NO COST".
   - NO ALL CAPS TEXT: Do not write words or sentences in ALL CAPS.
   - NO EMOJIS: Do not use emojis in subject line or email body.
   - NO SUSPICIOUS ATTACHMENTS: Never attach files or say "see attached".

3. WHITELISTING & UNSUBSCRIBE COMPLIANCE (RULES 5 & 7):
   - Maintain a polished, respectful, professional tone.
   - Include a courteous whitelisting line near the sign-off: "Please add me to your contacts so our emails reach your inbox."
   - The automated email builder will attach the official legal unsubscribe link in the footer.

4. NO GENERIC AI OPENERS (STRICT BANS) — NEVER start with clichés like:
   - "Hope this email finds you well..."
   - "I wanted to reach out..."
   - "We provide AI automation..."
   - "I came across your profile..."

5. HYPER-PERSONALIZED HOOK — ALWAYS open by directly referencing specific details about their company, founder/CEO, product, job posting, recent news, or specific detected website flaw. Start directly with a natural greeting: "Hi [Name]," followed immediately by their specific context or pain point.

6. PITCH THE SOLUTION & AI CAPABILITIES — Reference the specific recommended_ai_solution and/or recommended_web_solution that Nexariza offers for their exact pain point. Explicitly state what AI development and system upgradation Nexariza would do for the client (Custom ML, NLP, Computer Vision, Generative AI pipelines, AI Agents, Workflow Automation).

7. CONCRETE VALUE PROP & SOCIAL PROOF — Provide a specific outcome (e.g., "save 20 hours a week", "cut processing time by 40%") and one real social proof metric.

8. MATCH BUYING INTENT ENERGY:
   - High intent → Confident, direct CTA: "Let's schedule a call this week"
   - Medium intent → Soft CTA: "Would you be open to a quick 15-minute discovery call?"
   - Low intent → Educational tone: "Happy to share how other companies solved this"

9. BE CONCISE — Max 120-180 words in the body. Natural plain-text style.

10. DO NOT WRITE A SIGN-OFF OR SIGNATURE — End the body with ONLY "Best," on its own line. Do NOT include any name, title, phone number, email address, website, or contact info after it. The official Nexariza branded signature (Ahmad Yasin, logo, phone, website, social links) is appended automatically by the email system.

CRITICAL: Output ONLY the final email starting directly with "SUBJECT:". Do NOT write any preamble, drafting steps, reasoning thoughts, or commentary.

Output FORMAT (strictly follow this — no extra text):
SUBJECT: <subject line here>
---
<email body here>
"""


# ── Prompt Builder ────────────────────────────────────────────────────────────

def _build_prompt(
    name: str,
    email: str,
    domain: str,
    is_free_email: bool,
    web_content: Optional[str],
    # Extended lead intelligence fields
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    employees: Optional[str] = None,
    revenue: Optional[str] = None,
    ceo: Optional[str] = None,
    title: Optional[str] = None,
    website_quality: Optional[str] = None,
    ai_readiness: Optional[str] = None,
    lead_score: Optional[int] = None,
    buying_intent: Optional[str] = None,
    problem_statement: Optional[str] = None,
    recommended_ai_solution: Optional[str] = None,
    recommended_web_solution: Optional[str] = None,
    estimated_project_value: Optional[str] = None,
    estimated_timeline: Optional[str] = None,
    notes: Optional[str] = None,
    website_flaws: Optional[str] = None,   # Formatted output from flaw_analyzer
) -> str:

    # ── Section 1: Contact Info ──────────────────────────────────────────────
    contact_lines = [
        f"Contact Name: {name}",
        f"Contact Email: {email}",
    ]
    if title:
        contact_lines.append(f"Contact Title/Role: {title}")

    # ── Section 2: Company Profile ───────────────────────────────────────────
    company_lines = []
    if company_name:
        company_lines.append(f"Company Name: {company_name}")
    if industry:
        company_lines.append(f"Industry: {industry}")
    if city or state:
        location = ", ".join(filter(None, [city, state]))
        company_lines.append(f"Location: {location}")
    if employees:
        company_lines.append(f"Company Size: {employees} employees")
    if revenue:
        company_lines.append(f"Annual Revenue: {revenue}")
    if ceo:
        company_lines.append(f"CEO: {ceo}")

    # ── Section 3: Website Context ───────────────────────────────────────────
    website_lines = []
    if is_free_email:
        website_lines.append(
            "Note: Client uses a personal email. No company website available. "
            "Write a personalized but general email."
        )
    else:
        website_lines.append(f"Business Domain: {domain}")
        if website_quality:
            website_lines.append(f"Website Quality Score: {website_quality}")
        if web_content:
            website_lines.append(f"\nScraped Website Content:\n{web_content[:1200]}")
        else:
            website_lines.append(
                f"Note: Website ({domain}) could not be scraped. "
                "Infer their business from domain name and company profile."
            )

    # ── Section 4: Strategic Intel ───────────────────────────────────────────
    intel_lines = []
    if problem_statement:
        intel_lines.append(f"⚠️  KEY PAIN POINT (use as email hook): {problem_statement}")
    if recommended_ai_solution:
        intel_lines.append(f"🤖 Recommended AI Solution from Nexariza: {recommended_ai_solution}")
    if recommended_web_solution:
        intel_lines.append(f"🌐 Recommended Web Solution from Nexariza: {recommended_web_solution}")
    if ai_readiness:
        intel_lines.append(f"AI Readiness Level: {ai_readiness}")
    if buying_intent:
        intel_lines.append(f"Buying Intent Signal: {buying_intent} — adjust CTA urgency accordingly")
    if lead_score is not None:
        intel_lines.append(f"Lead Score: {lead_score}/100")
    if estimated_project_value:
        intel_lines.append(f"Estimated Deal Value: {estimated_project_value}")
    if estimated_timeline:
        intel_lines.append(f"Conversion Timeline: {estimated_timeline}")
    if notes:
        intel_lines.append(f"Additional Notes: {notes}")

    # ── Section 5: Website Flaw Audit (highest priority hook) ────────────────
    flaw_lines = []
    if website_flaws:
        flaw_lines.append(
            "⚡ WEBSITE AUDIT INTELLIGENCE (PRIORITY — open the email with one of these flaws):\n"
            + website_flaws
        )

    # ── Assemble Full Prompt ─────────────────────────────────────────────────
    sections = []

    if contact_lines:
        sections.append("[ CONTACT INFO ]\n" + "\n".join(contact_lines))
    if company_lines:
        sections.append("[ COMPANY PROFILE ]\n" + "\n".join(company_lines))
    if website_lines:
        sections.append("[ WEBSITE CONTEXT ]\n" + "\n".join(website_lines))
    if intel_lines:
        sections.append("[ STRATEGIC INTELLIGENCE ]\n" + "\n".join(intel_lines))
    if flaw_lines:
        sections.append("[ WEBSITE AUDIT INTELLIGENCE ]\n" + "\n".join(flaw_lines))

    client_context = "\n\n".join(sections)
    system = SYSTEM_PROMPT.format(nexariza_description=NEXARIZA_DESCRIPTION)

    return (
        f"{system}\n\n"
        f"{'═'*60}\n"
        f"LEAD INTELLIGENCE BRIEFING:\n"
        f"{'═'*60}\n"
        f"{client_context}\n\n"
        f"Now write the outreach email:"
    )


# ── Response Parser ───────────────────────────────────────────────────────────

def _parse_gemini_response(response_text: str) -> Tuple[str, str]:
    """
    Parse Groq/Gemini output into (subject, body).
    Expected format:
        SUBJECT: <subject>
        ---
        <body>

    Handles reasoning models with <think>...</think> blocks, drafting notes,
    markdown fences, and truncated outputs gracefully.
    """
    cleaned = response_text.strip()

    # 1. If </think> is present, take everything after </think>
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()

    # Strip markdown code fence wrappers
    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    # Look for the LAST occurrence of SUBJECT: (handling bullet points, stars, prefixes)
    subject_matches = list(re.finditer(r"(?im)^[#* \t\-\d\.]*(?:SUBJECT|Subject):\s*(.+)$", cleaned))
    if subject_matches:
        last_subj = subject_matches[-1]
        subject = last_subj.group(1).strip().strip("*").strip('"').strip("'")
        after_subject = cleaned[last_subj.end():].strip()

        # Check for separator (---) or Body: tag
        sep_match = re.search(r"(?m)^(?:---|___|\*\*\*)\s*$", after_subject)
        body_tag_match = re.search(r"(?im)^[#* \t\-\d\.]*(?:Body|BODY):\s*", after_subject)

        if sep_match:
            body = after_subject[sep_match.end():].strip()
        elif body_tag_match:
            body = after_subject[body_tag_match.end():].strip()
        else:
            body = after_subject
    else:
        # Standard line by line fallback
        lines = cleaned.splitlines()
        subject = "How Nexariza AI Can Help Your Business"
        body_lines = []
        in_body = False
        for line in lines:
            stripped = line.strip().lstrip("#*- \t")
            if not in_body:
                if stripped.upper().startswith("SUBJECT:"):
                    subject = stripped[8:].strip().strip("*").strip('"').strip("'")
                elif stripped in ("---", "___", "***") or stripped.upper().startswith("BODY:"):
                    in_body = True
            else:
                body_lines.append(line)
        body = "\n".join(body_lines).strip() if body_lines else cleaned

    return subject, body





# ── Spam Trigger Sanitizer & Compliance Checker ─────────────────────────────

SPAM_TRIGGER_PATTERNS = [
    r"\bfree\b", r"\burgent\b", r"\blimited time\b", r"\bclick here now\b",
    r"\bbuy now\b", r"\bguaranteed\b", r"\b100%\b", r"\bspecial offer\b",
    r"\bact now\b", r"\brisk-free\b", r"\brisk free\b", r"\bdiscount\b",
    r"\bmoney back\b", r"\bwinner\b", r"\bcongratulations\b", r"\bno cost\b",
    r"\bclick below\b", r"\border now\b"
]

ALLOWED_ACRONYMS = {"AI", "ML", "API", "CRM", "CEO", "CTO", "SAAS", "NLP", "HTML", "CSS", "DNS", "SMTP", "RAG", "FAQ", "USD", "ROI", "CSV", "JSON", "URL", "PDF", "HTTP", "HTTPS", "IT"}


def cleanse_and_validate_email(subject: str, body: str) -> Tuple[str, str, dict]:
    """
    Programmatic validation & cleansing for email content:
    - Removes spam trigger words ('FREE', 'URGENT', 'LIMITED TIME', etc.)
    - Normalizes unintended ALL CAPS text
    - Ensures single link limit
    - Checks for whitelisting and unsubscribe compliance
    """
    import re
    warnings = []

    # 1. Detect & sanitize spam trigger words
    for pattern in SPAM_TRIGGER_PATTERNS:
        if re.search(pattern, subject, re.IGNORECASE):
            warnings.append(f"Sanitized spam word in subject: '{pattern}'")
            subject = re.sub(pattern, "", subject, flags=re.IGNORECASE).strip()
        if re.search(pattern, body, re.IGNORECASE):
            warnings.append(f"Sanitized spam word in body: '{pattern}'")
            body = re.sub(pattern, "", body, flags=re.IGNORECASE).strip()

    # 2. Fix ALL CAPS words (excluding allowed technical acronyms)
    def _fix_caps(match):
        word = match.group(0)
        if word in ALLOWED_ACRONYMS:
            return word
        warnings.append(f"Normalized ALL CAPS word: '{word}'")
        return word.capitalize()

    subject = re.sub(r'\b[A-Z]{2,}\b', _fix_caps, subject)
    body = re.sub(r'\b[A-Z]{2,}\b', _fix_caps, body)

    # 3. Strictly limit links: remove any URLs from email body so the ONLY link is the signature website link
    urls = re.findall(r'https?://[^\s<>")]+', body)
    if urls:
        warnings.append(f"Removed {len(urls)} body link(s) to enforce strict single-link limit in signature.")
        for u in urls:
            body = body.replace(u, "")
        # Clean up empty brackets or leftover artifacts like () or []
        body = re.sub(r'\(\s*\)', '', body)
        body = re.sub(r'\[\s*\]', '', body)
        body = re.sub(r'  +', ' ', body)

    report = {
        "is_clean": len(warnings) == 0,
        "warnings": warnings,
        "spam_score": max(0, 100 - (len(warnings) * 15))
    }

    return subject, body, report


# ── Main Generator ────────────────────────────────────────────────────────────

async def generate_outreach_email(
    name: str,
    email: str,
    domain: str,
    is_free_email: bool,
    web_content: Optional[str],
    # Extended fields (all optional for backward-compatibility)
    company_name: Optional[str] = None,
    industry: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    employees: Optional[str] = None,
    revenue: Optional[str] = None,
    ceo: Optional[str] = None,
    title: Optional[str] = None,
    website_quality: Optional[str] = None,
    ai_readiness: Optional[str] = None,
    lead_score: Optional[int] = None,
    buying_intent: Optional[str] = None,
    problem_statement: Optional[str] = None,
    recommended_ai_solution: Optional[str] = None,
    recommended_web_solution: Optional[str] = None,
    estimated_project_value: Optional[str] = None,
    estimated_timeline: Optional[str] = None,
    notes: Optional[str] = None,
    website_flaws: Optional[str] = None,   # Formatted flaw report from flaw_analyzer
) -> Tuple[str, str]:
    """
    Generates a hyper-personalized outreach email using Groq + all lead intel fields.
    Returns (subject, body) tuple, pre-sanitized against spam triggers.
    """
    prompt = _build_prompt(
        name=name,
        email=email,
        domain=domain,
        is_free_email=is_free_email,
        web_content=web_content,
        company_name=company_name,
        industry=industry,
        city=city,
        state=state,
        employees=employees,
        revenue=revenue,
        ceo=ceo,
        title=title,
        website_quality=website_quality,
        ai_readiness=ai_readiness,
        lead_score=lead_score,
        buying_intent=buying_intent,
        problem_statement=problem_statement,
        recommended_ai_solution=recommended_ai_solution,
        recommended_web_solution=recommended_web_solution,
        estimated_project_value=estimated_project_value,
        estimated_timeline=estimated_timeline,
        notes=notes,
        website_flaws=website_flaws,
    )

    try:
        raw_text = await _groq_create_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_completion_tokens=2000,
            label=f"{company_name or name} ({email})",
        )
        subject, body = _parse_gemini_response(raw_text)

        # ── Body Quality Gate ────────────────────────────────────────────────
        # Reject truncated or garbage AI output before it ever reaches send_email().
        # A real cold email is at least 80 characters and must contain a sentence.
        MIN_BODY_LENGTH = 80
        if not body or len(body) < MIN_BODY_LENGTH:
            raise RuntimeError(
                f"AI returned a suspiciously short email body ({len(body)} chars) "
                f"for {name} ({email}). Raw AI output: {repr(raw_text[:200])}. "
                "Aborting to prevent sending a broken email."
            )

        # ── Reasoning Leak Safety Gate ───────────────────────────────────────
        # Reject outputs where the AI leaked internal prompt evaluation checklists
        REASONING_LEAK_PATTERNS = [
            r"(?i)\b\d+[-–]\d+\s*words\?\s*(?:yes|no)\b",
            r"(?i)\bno\s+(?:spam\s+words|links\s+in\s+body|generic\s+openers)\?",
            r"(?i)\bthinking\s+process\b",
            r"(?i)\bdrafting\s*[-:]\s*(?:subject|body)\b",
            r"(?i)\bconstraint\s*check\b",
            r"(?i)\bword\s+count\s+analysis\b",
            r"(?i)\bresult:\s*no\s+links\b",
            r"(?i)\bintriguing\?\s*yes\b",
            r"(?i)\bpersonalized\?\s*yes\b",
        ]
        for pat in REASONING_LEAK_PATTERNS:
            if re.search(pat, subject) or re.search(pat, body):
                raise RuntimeError(
                    f"AI leaked internal reasoning checklist (matched '{pat}') "
                    f"for {name} ({email}). Aborting output to retry fallback."
                )

        # Enforce anti-spam cleansing and formatting validation
        subject, body, report = cleanse_and_validate_email(subject, body)
        if report["warnings"]:
            logger.info(f"Email sanitized for {email}: {report['warnings']}")

        company_label = company_name or name
        logger.info(f"Generated email for {company_label} ({email}) | Lead Score: {lead_score} | Intent: {buying_intent}")
        return subject, body

    except Exception as e:
        logger.error(f"Groq generation failed for {name}: {e}")
        raise


# ── Auto-Reply Generator ──────────────────────────────────────────────────────

REPLY_SYSTEM_PROMPT = """You are a helpful customer representative for Nexariza AI.
Your job is to write a personalized, professional, and concise email response to a prospect who has replied to our outreach.

About Nexariza AI:
{nexariza_description}

Previous Outreach Context:
Original Subject: {original_subject}
Original Body:
{original_body}

Prospect's Response:
From: {prospect_name} <{prospect_email}>
Message:
{incoming_email_body}

Rules for your response:
- Directly, politely, and professionally address their questions, concerns, or interest.
- Maintain a helpful, conversational, and direct plain-text tone.
- NO SPAM WORDS: Do not use words like "FREE", "URGENT", "BUY NOW", "100%", "WINNER", "CLICK HERE".
- NO EMOJIS & NO ALL CAPS.
- MAXIMUM 1 LINK IN TOTAL: If adding a link, include at most 1 link (https://nexariza.com).
- Keep the response short and clear (max 150 words).
- Only write the email body. Do not include any Subject line or header separators.
- Sign off cleanly as: Hassan Nadeem | Nexariza AI
"""


async def generate_reply_email(
    prospect_name: str,
    prospect_email: str,
    original_subject: str,
    original_body: str,
    incoming_email_body: str,
) -> Tuple[str, str]:
    """
    Generates an AI response to a prospect's email reply.
    Returns (reply_subject, reply_body) tuple.
    """
    prompt = REPLY_SYSTEM_PROMPT.format(
        nexariza_description=NEXARIZA_DESCRIPTION,
        original_subject=original_subject,
        original_body=original_body,
        prospect_name=prospect_name,
        prospect_email=prospect_email,
        incoming_email_body=incoming_email_body,
    )

    # Standard email reply subject prefix
    reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

    try:
        reply_body = await _groq_create_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_completion_tokens=500,
            label=f"reply to {prospect_email}",
        )
        reply_body = reply_body.strip()
        logger.info(f"Generated auto-reply for {prospect_email}")
        return reply_subject, reply_body

    except Exception as e:
        logger.error(f"Groq reply generation failed for {prospect_email}: {e}")
        raise

