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

GEMINI_MODEL = "gemini-2.0-flash"


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
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        ),
    )
    return response.text


async def _groq_create_with_fallback(
    messages: list,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.8,
    max_completion_tokens: int = 600,
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

    for idx, client in enumerate(groq_clients):
        key_label = "PRIMARY" if idx == 0 else f"FALLBACK-{idx}"
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
            )
            if idx > 0:
                logger.info(
                    f"[GROQ {key_label}] Succeeded for '{label}' after earlier key failure."
                )
            return response.choices[0].message.content

        except Exception as e:
            last_error = e
            logger.warning(
                f"[GROQ {key_label}] Failed for '{label}': {type(e).__name__}: {e}"
            )
            if idx < len(groq_clients) - 1:
                logger.info(
                    f"[GROQ] Retrying with next Groq key ({idx + 2}/{len(groq_clients)})..."
                )

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
GOLDEN RULES FOR THE EMAIL:
═══════════════════════════════════════════════════════
1. START WITH THE PAIN — Open by directly acknowledging the client's specific problem_statement.
   Do NOT start with "I hope this email finds you well" or generic openers.
2. PITCH THE SOLUTION — Reference the specific recommended_ai_solution and/or recommended_web_solution
   that Nexariza offers for their exact pain point.
3. TAILOR TO THEIR INDUSTRY & SIZE — A 10-person retail startup gets a different tone than a 
   500-person enterprise SaaS company. Adjust complexity, urgency, and ROI framing accordingly.
4. MATCH BUYING INTENT ENERGY:
   - High intent → Confident, direct CTA: "Let's schedule a call this week"
   - Medium intent → Soft CTA: "Would you be open to a quick 15-minute discovery call?"
   - Low intent → Educational, nurturing tone: "Happy to share how other [industry] companies solved this"
5. USE THEIR TITLE — Technical titles (CTO, VP Engineering) get technical language.
   Executive titles (CEO, COO) get ROI and business impact language.
6. MENTION CITY/REGION if it adds local relevance or builds rapport.
7. BE CONCISE — Max 150 words in the body. No buzzwords. No excessive flattery.
8. END with a soft call-to-action appropriate to their buying intent.
9. SIGN OFF AS: Hassan Nadeem, Nexariza AI

Output FORMAT (strictly follow this — no extra commentary):
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
    Parse Groq output into (subject, body).
    Expected format:
        SUBJECT: <subject>
        ---
        <body>
    """
    lines = response_text.strip().splitlines()
    subject = "How Nexariza AI Can Help Your Business"
    body_lines = []
    in_body = False

    for line in lines:
        if line.upper().startswith("SUBJECT:"):
            subject = line[8:].strip()
        elif line.strip() == "---":
            in_body = True
        elif in_body:
            body_lines.append(line)

    # Fallback: if no separator found, treat everything after subject as body
    if not body_lines and not in_body:
        body_lines = [l for l in lines if not l.upper().startswith("SUBJECT:")]

    body = "\n".join(body_lines).strip()
    return subject, body


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
) -> Tuple[str, str]:
    """
    Generates a hyper-personalized outreach email using Groq + all lead intel fields.
    Returns (subject, body) tuple.
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
    )

    try:
        raw_text = await _groq_create_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_completion_tokens=600,
            label=f"{company_name or name} ({email})",
        )
        subject, body = _parse_gemini_response(raw_text)
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
- Maintain a helpful, conversational, and direct tone (avoid corporate buzzwords).
- Keep the response short and clear (max 150 words).
- Only write the email body. Do not include any Subject line or header separators.
- Sign off as: Hassan Nadeem, Nexariza AI
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

