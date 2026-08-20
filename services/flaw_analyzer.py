"""
flaw_analyzer.py
----------------
AI-powered website audit engine for Nexariza outreach.

Given scraped website content, uses Groq/Gemini to identify 3-5 specific,
actionable operational flaws that Nexariza AI can solve — turning generic
cold emails into laser-targeted, personalized pitches.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


# ── Flaw Report Dataclass ─────────────────────────────────────────────────────

@dataclass
class WebsiteFlawReport:
    url: str
    flaws: List[str] = field(default_factory=list)        # 3-5 specific detected flaws
    summary: str = ""                                       # 1-sentence hook for the email opener
    automation_gaps: List[str] = field(default_factory=list)  # Specific automation opportunities
    urgency_level: str = "Medium"                           # High / Medium / Low


# ── Rule-Based Pre-Scan (fast, no API call needed) ────────────────────────────

MANUAL_PROCESS_KEYWORDS = [
    "fill out", "fill in", "call us to", "fax us", "send us an email",
    "contact us by phone", "call for a quote", "call to schedule",
    "please call", "reach us by", "phone only", "no online booking",
]

OUTDATED_KEYWORDS = [
    "copyright 2018", "copyright 2019", "copyright 2020",
    "© 2018", "© 2019", "© 2020",
    "last updated 2019", "last updated 2020",
]

NO_AUTOMATION_SIGNALS = [
    "we will get back to you", "we will contact you shortly",
    "someone will reach out", "within 24-48 hours", "within 2-3 business days",
    "response time", "please allow", "kindly allow",
]


def _rule_based_scan(content_lower: str, html_raw: str = "") -> List[str]:
    """
    Quick keyword/pattern scan to detect obvious flaws before the AI call.
    Returns a list of detected flaw strings.
    """
    detected = []

    # Manual process signals
    for kw in MANUAL_PROCESS_KEYWORDS:
        if kw in content_lower:
            detected.append(f"Manual intake process detected ('{kw}') — no automation in place")
            break

    # Outdated site
    for kw in OUTDATED_KEYWORDS:
        if kw in content_lower:
            detected.append("Outdated website — copyright/date suggests site hasn't been refreshed in years")
            break

    # Slow response time
    for kw in NO_AUTOMATION_SIGNALS:
        if kw in content_lower:
            detected.append("No instant response system — site promises 24-48hr follow-up, losing hot leads")
            break

    # No live chat detected
    chat_signals = ["livechat", "live chat", "intercom", "drift", "tawk", "crisp", "freshchat", "zendesk chat"]
    if html_raw and not any(s in html_raw.lower() for s in chat_signals):
        detected.append("No live chat or AI chatbot found — visitors have no instant support option")

    # Phone-only contact
    if "tel:" in html_raw.lower() and "mailto:" not in html_raw.lower():
        detected.append("Phone-only contact detected — no email CTA, limiting lead capture")

    # No pricing page signals
    pricing_signals = ["pricing", "price", "plans", "packages", "subscription", "cost"]
    if not any(s in content_lower for s in pricing_signals):
        detected.append("No pricing information visible — potential buyers can't self-qualify, increasing sales friction")

    # Form present but no mention of CRM/automation
    form_present = "form" in html_raw.lower() or "contact" in content_lower
    crm_signals = ["crm", "hubspot", "salesforce", "pipedrive", "zoho crm", "mailchimp", "klaviyo", "active campaign"]
    if form_present and not any(s in content_lower for s in crm_signals):
        detected.append("Contact form detected but no CRM or marketing automation integration visible — leads likely managed manually")

    return detected[:4]  # Cap at 4 to leave room for AI-detected flaws


# ── AI Flaw Audit Prompt ──────────────────────────────────────────────────────

FLAW_AUDIT_SYSTEM_PROMPT = """You are a senior business operations analyst at Nexariza AI.
Your job is to audit a company's website and identify REAL, SPECIFIC operational and technological flaws
that Nexariza AI could solve with automation, AI agents, or modern web development.

Focus on:
- Manual processes that should be automated (data entry, follow-ups, scheduling, invoicing)
- Missing automation tools (no chatbot, no CRM integration, no auto-responders)
- Poor lead capture (no live chat, no instant booking, no self-serve pricing)
- Outdated tech stack signals (old site, no modern integrations, no analytics visible)
- Workflow bottlenecks (slow response times, phone-only contact, no client portal)
- Missing AI opportunities (no personalization, no recommendation engine, no predictive tools)

Output FORMAT (strictly):
FLAW 1: <specific flaw in 1 sentence>
FLAW 2: <specific flaw in 1 sentence>
FLAW 3: <specific flaw in 1 sentence>
HOOK: <1 punchy sentence that could open a cold email — reference the company name if known>
URGENCY: <High|Medium|Low>
GAPS: <comma-separated list of automation/AI gaps, max 4>

Rules:
- Be SPECIFIC, not generic. Bad: "poor website". Good: "Contact form routes to email inbox manually — no CRM or auto-responder detected"
- Only report what you can actually observe from the content provided
- Never fabricate flaws you cannot infer from the content
- Max 3 flaws. Quality > quantity.
"""


# ── Main Analyzer ─────────────────────────────────────────────────────────────

async def analyze_website_flaws(
    url: str,
    web_content: str,
    html_raw: str = "",
    company_name: Optional[str] = None,
) -> WebsiteFlawReport:
    """
    Runs a two-stage flaw detection:
    1. Fast rule-based scan (keyword patterns)
    2. AI-powered deep analysis via Groq/Gemini

    Returns a WebsiteFlawReport with specific flaws and an email hook.
    """
    # Import here to avoid circular imports
    from services.gemini_service import _groq_create_with_fallback

    report = WebsiteFlawReport(url=url)
    content_lower = web_content.lower()

    # ── Stage 1: Rule-based pre-scan ─────────────────────────────────────────
    rule_flaws = _rule_based_scan(content_lower, html_raw)
    logger.info(f"[FlawAnalyzer] Rule-based scan found {len(rule_flaws)} signals for {url}")

    # ── Stage 2: AI deep audit ────────────────────────────────────────────────
    company_label = f" (company: {company_name})" if company_name else ""
    prompt = (
        f"{FLAW_AUDIT_SYSTEM_PROMPT}\n\n"
        f"Website URL: {url}{company_label}\n\n"
        f"Scraped Website Content:\n{web_content[:2000]}\n\n"
        f"Now audit this website and identify flaws:"
    )

    try:
        raw = await _groq_create_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,          # Lower temp = more factual, less hallucination
            max_completion_tokens=400,
            label=f"flaw-audit:{url}",
        )
        report = _parse_flaw_response(raw, url, rule_flaws)
        logger.info(
            f"[FlawAnalyzer] AI audit complete for {url} | "
            f"{len(report.flaws)} flaws | urgency={report.urgency_level}"
        )

    except Exception as e:
        # Graceful fallback — use rule-based results only
        logger.warning(f"[FlawAnalyzer] AI audit failed for {url}: {e}. Using rule-based results only.")
        report.flaws = rule_flaws if rule_flaws else ["Website could benefit from modern automation tools"]
        report.summary = _generate_fallback_hook(rule_flaws, company_name, url)
        report.urgency_level = "Medium"

    return report


# ── Response Parser ───────────────────────────────────────────────────────────

def _parse_flaw_response(raw: str, url: str, rule_flaws: List[str]) -> WebsiteFlawReport:
    """Parse the structured AI flaw audit response."""
    report = WebsiteFlawReport(url=url)
    lines = raw.strip().splitlines()

    ai_flaws = []
    hook = ""
    urgency = "Medium"
    gaps = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        upper = stripped.upper()

        if upper.startswith("FLAW"):
            # Extract "FLAW N: <text>"
            match = re.match(r"FLAW\s*\d*\s*:\s*(.+)", stripped, re.IGNORECASE)
            if match:
                ai_flaws.append(match.group(1).strip())

        elif upper.startswith("HOOK:"):
            hook = stripped[5:].strip()

        elif upper.startswith("URGENCY:"):
            raw_urgency = stripped[8:].strip().capitalize()
            if raw_urgency in ("High", "Medium", "Low"):
                urgency = raw_urgency

        elif upper.startswith("GAPS:"):
            gaps_raw = stripped[5:].strip()
            gaps = [g.strip() for g in gaps_raw.split(",") if g.strip()][:4]

    # Merge AI flaws + unique rule-based flaws (avoid duplicates)
    all_flaws = ai_flaws[:]
    for rf in rule_flaws:
        if not any(rf[:30].lower() in af.lower() for af in all_flaws):
            all_flaws.append(rf)

    report.flaws = all_flaws[:5]  # Cap at 5 total
    report.summary = hook or _generate_fallback_hook(all_flaws, None, url)
    report.urgency_level = urgency
    report.automation_gaps = gaps

    return report


def _generate_fallback_hook(flaws: List[str], company_name: Optional[str], url: str) -> str:
    """Generate a hook sentence when AI parsing fails."""
    company = company_name or url.replace("https://", "").replace("http://", "").split("/")[0]
    if flaws:
        # Use the first flaw as the hook base
        return f"I noticed {company} may be leaving efficiency gains on the table — {flaws[0].lower()}"
    return f"I was looking at {company}'s operations and spotted a few areas where automation could make a meaningful difference."


# ── Convenience: Format Flaws for Email Prompt ────────────────────────────────

def format_flaws_for_prompt(report: WebsiteFlawReport) -> str:
    """
    Returns a formatted string of the flaw report ready to be injected
    into the Gemini/Groq email generation prompt.
    """
    if not report or not report.flaws:
        return ""

    lines = [
        f"[AUDIT] {report.url}",
        f"Urgency Level: {report.urgency_level}",
        "",
        "Detected Operational Flaws:",
    ]
    for i, flaw in enumerate(report.flaws, 1):
        lines.append(f"  {i}. {flaw}")

    if report.automation_gaps:
        lines.append("")
        lines.append(f"Automation Gaps: {', '.join(report.automation_gaps)}")

    if report.summary:
        lines.append("")
        lines.append(f"[HOOK] Suggested Email Hook: {report.summary}")

    return "\n".join(lines)
