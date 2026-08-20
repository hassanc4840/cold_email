"""
sales_campaign.py
-----------------
Nexariza Sales Outreach Script -- sales@nexariza.com

Reads prospects from sent_history.csv (already emailed via contact@nexariza.com),
generates a FRESH brand-new email (not a follow-up), sends it from sales@nexariza.com,
then moves the record from sent_history.csv to sale_sent_history.csv.

Usage:
    python sales_campaign.py

Requirements:
    - .env must have SALES_SENDER_EMAIL and SALES_SENDER_PASSWORD set
    - sent_history.csv must exist with columns: Email,Name,Subject,Body,Sent At
"""

import os
import csv
import sys
import asyncio
import logging
import random
import re
import ssl
import pathlib
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import aiosmtplib
import dns.asyncresolver
import dns.resolver
import dns.exception
from email_validator import validate_email, EmailNotValidError
from dotenv import load_dotenv
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

# Bootstrap
load_dotenv(pathlib.Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("sales_campaign")

# Config
SENT_HISTORY_CSV   = "sent_history.csv"
SALE_SENT_CSV      = "sale_sent_history.csv"

SALES_SMTP_SERVER  = os.getenv("SALES_SMTP_SERVER",  "smtp.zoho.com")
SALES_SMTP_PORT    = int(os.getenv("SALES_SMTP_PORT", "465"))
SALES_SENDER_EMAIL = os.getenv("SALES_SENDER_EMAIL", "sales@nexariza.com")
SALES_SENDER_PASS  = os.getenv("SALES_SENDER_PASSWORD", "")

FREE_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "aol.com", "live.com", "protonmail.com",
    "mail.com", "ymail.com",
}

# Nexariza description for the sales angle
SALES_NEXARIZA_DESCRIPTION = """
Nexariza AI is a production-grade AI development and full-stack software company founded in 2024,
headquartered in Lahore, Pakistan. We build intelligent systems that genuinely transform how
businesses operate -- not demos, but real deployed revenue-generating solutions.

Core Services:
1. Custom AI & ML Development (custom models, NLP, Computer Vision, Generative AI pipelines,
   AI Agents, RAG systems, workflow automation)
2. Full-Stack Web Development (React, Next.js, FastAPI, Node.js, SaaS platforms)
3. Workflow & Process Automation (CRM integrations, data pipelines, automated systems)

Differentiators: Production-ready deliverables, fast turnaround (2-6 weeks),
transparent pricing, milestone-based delivery.
Founder: Ahmad Yasin | +92-370-7348001 | https://nexariza.com
"""

SALES_SYSTEM_PROMPT = """You are a senior sales representative for Nexariza AI, a production-grade AI
development and full-stack software company based in Lahore, Pakistan.

Write a SHORT, deeply personalized, professional cold outreach email.

About Nexariza AI:
{nexariza_description}

GOLDEN RULES (follow strictly):
1. SUBJECT: 3-7 words, personalized, intriguing. E.g. "Quick idea for [Company]" or "Automating [specific process]?"
2. OPENING: "Hi [Name]," then immediately something specific about their industry/company from the domain. NO generic openers.
3. BODY: 100-150 words, conversational plain-text. Name 1 specific pain point for their industry, what Nexariza would do.
4. CLOSING: ONE low-friction CTA: "Would a quick 15-minute call make sense?" or "Should I share an example from a similar company?"
5. SIGN-OFF: Two lines only:
   Best,
   Hassan Nadeem
6. NEVER use: FREE, URGENT, GUARANTEED, ACT NOW, LIMITED TIME, BUY NOW, CLICK HERE, 100%, DISCOUNT, SPECIAL OFFER
7. NO ALL CAPS, NO emojis, max 1 link (https://nexariza.com if needed), no fake urgency
8. FRESH ANGLE: This is the FIRST time reaching out -- completely new angle, totally fresh

Output FORMAT (exactly this, no extra commentary):
SUBJECT: <subject line>
---
<email body>
"""

# Spam word lists (mirrors deliverability_agent.py)
SPAM_TRIGGERS = {
    "high": [
        "free", "urgent", "act now", "limited time", "click here",
        "buy now", "guaranteed", "no cost", "risk-free", "winner",
        "congratulations", "100%", "special offer", "discount",
        "money back", "cash bonus", "earn money", "make money",
        "exclusive deal", "clearance", "bargain", "last chance",
        "prize", "save big", "claim your",
    ],
    "medium": [
        "as seen on", "call now", "dear friend", "for instant access",
        "great offer", "not spam", "please read", "satisfaction guaranteed",
        "this isnt spam", "bulk rate", "increase revenue", "mass email",
        "open immediately", "opt in", "potential earnings",
    ],
    "low": [
        "amazing", "cancel anytime", "confidential", "fast cash",
        "hidden", "investment", "lose weight", "luxury", "miracle",
        "obligation", "profits", "promise", "refund", "trial",
        "unlimited", "vacation", "visit our website",
    ],
}
SEVERITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}


# ── Email Address Validator ────────────────────────────────────────────────────

ROLE_BASED_PREFIXES = {
    "admin", "info", "sales", "support", "contact", "billing", "hello",
    "marketing", "office", "help", "security", "webmaster", "postmaster"
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "10minutemail.com", "temp-mail.org", "guerrillamail.com",
    "sharklasers.com", "yopmail.com", "trashmail.com", "getnada.com"
}

# Simple TTL-like cache for MX results (keyed by domain -> bool, cleared per run)
_mx_valid_cache: dict[str, bool] = {}


async def validate_email_address(email: str) -> tuple[bool, str]:
    """
    Validate an email address before sending. Three-stage check:
    1. Syntax validation  (email-validator library)
    2. Disposable domain  (known throwaway providers)
    3. Role-based prefix  (generic aliases unlikely to be decision-makers)
    4. DNS MX record      (domain can actually receive mail)

    Returns (is_valid: bool, reason: str).
    """
    if not email or not isinstance(email, str):
        return False, "Empty or non-string address"

    email = email.strip()

    # 1. Syntax check
    try:
        validated = validate_email(email, check_deliverability=False)
        domain     = validated.domain.lower()
        local_part = validated.local_part.lower()
    except EmailNotValidError as exc:
        return False, f"Syntax error: {exc}"

    # 2. Disposable domain
    if domain in DISPOSABLE_DOMAINS:
        return False, f"Disposable email domain: {domain}"

    # 3. Role-based prefix
    if local_part in ROLE_BASED_PREFIXES:
        return False, f"Role-based generic prefix: {local_part}"

    # 4. DNS MX check (cached per campaign run)
    if domain in _mx_valid_cache:
        if not _mx_valid_cache[domain]:
            return False, f"No MX records for domain: {domain}"
    else:
        has_mx = False
        for attempt in range(3):
            try:
                answers = await dns.asyncresolver.resolve(domain, "MX")
                records = sorted(answers, key=lambda r: r.preference)
                exchanges = [str(r.exchange).rstrip(".") for r in records]
                # Null MX (RFC 7505) — domain explicitly refuses mail
                if exchanges and exchanges[0] == "":
                    _mx_valid_cache[domain] = False
                    return False, f"Null MX record — domain does not accept email: {domain}"
                has_mx = len(exchanges) > 0
                break
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                    dns.resolver.NoNameservers):
                has_mx = False
                break
            except dns.exception.Timeout:
                if attempt == 2:
                    # DNS timed out — give benefit of the doubt
                    logger.warning(f"[Validator] DNS timeout for {domain}, assuming valid")
                    has_mx = True
                    break
                await asyncio.sleep(1)
            except Exception as exc:
                logger.warning(f"[Validator] DNS lookup error for {domain}: {exc}")
                has_mx = True  # don't block on unexpected DNS errors
                break

        _mx_valid_cache[domain] = has_mx
        if not has_mx:
            return False, f"No MX records for domain: {domain}"

    return True, "Valid"


# ── AI Email Generation using unified services ───────────────────────────────
async def generate_sales_email(name: str, email: str, original_subject: str) -> Tuple[str, str]:
    """
    Generates a deeply personalized sales outreach email using the exact same
    pipeline as contact@nexariza.com:
    1. Scrapes the prospect's website (httpx + PixelRAG screenshot fallback)
    2. Runs website flaw analysis to detect actionable pain points
    3. Prompts the Groq/Gemini pool (1000 token limit to prevent cutoffs)
    4. Sanitizes spam words, normalizes ALL CAPS, and verifies body length >= 80 chars
    """
    from services.scraper_service import get_client_web_context
    from services.flaw_analyzer import format_flaws_for_prompt
    from services.gemini_service import generate_outreach_email

    # 1. Scrape web context + PixelRAG fallback
    try:
        web_ctx = await get_client_web_context(email=email)
    except Exception as e:
        logger.warning(f"[Sales] Web scrape failed for {email}: {e}")
        web_ctx = {
            "domain": email.split("@")[-1] if "@" in email else "",
            "is_free_email": True,
            "website_url": None,
            "web_content": None,
            "flaw_report": None,
        }

    # 2. Extract flaw report
    flaw_report = web_ctx.get("flaw_report")
    flaw_str = format_flaws_for_prompt(flaw_report) if flaw_report else None

    # 3. Build problem statement with prior subject avoidance
    problem_statement = (
        f"Fresh outreach from sales team (sales@nexariza.com). "
        f"Do NOT repeat this prior subject: '{original_subject}'. "
        "Pitch a fresh, high-value AI automation or software angle."
    )

    # 4. Generate hyper-personalized email via Groq/Gemini pool
    subject, body = await generate_outreach_email(
        name=name,
        email=email,
        domain=web_ctx.get("domain", ""),
        is_free_email=web_ctx.get("is_free_email", False),
        web_content=web_ctx.get("web_content"),
        problem_statement=problem_statement,
        website_flaws=flaw_str,
    )

    return subject, body


# ── SMTP Sender via sales@nexariza.com using unified email_service ─────────────
async def send_sales_email(recipient: str, subject: str, body: str) -> bool:
    """
    Sends email via sales@nexariza.com using email_service.py with:
    - Clean branded HTML signature (no duplicate text)
    - Deliverability headers (smart Message-ID, Date, clean headers)
    - Email warmup tracking & anti-spam compliance
    """
    from services.email_service import send_email, get_sales_smtp_config

    sales_config = get_sales_smtp_config()
    if not sales_config.get("password"):
        raise ValueError("SALES_SENDER_PASSWORD is not configured in .env")

    return await send_email(
        recipient=recipient,
        subject=subject,
        body=body,
        sender_name="Hassan Nadeem | Nexariza AI",
        smtp_config=sales_config,
    )



# CSV Helpers
def load_sent_history() -> List[dict]:
    if not os.path.exists(SENT_HISTORY_CSV):
        return []
    rows = []
    with open(SENT_HISTORY_CSV, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Email", "").strip():
                rows.append(dict(row))
    return rows


def remove_from_sent_history(emails_to_remove: set) -> int:
    if not os.path.exists(SENT_HISTORY_CSV):
        return 0
    kept = []
    removed = 0
    lower_set = {e.lower() for e in emails_to_remove}
    with open(SENT_HISTORY_CSV, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or ["Email", "Name", "Subject", "Body", "Sent At"]
        for row in reader:
            if row.get("Email", "").strip().lower() in lower_set:
                removed += 1
            else:
                kept.append(row)
    with open(SENT_HISTORY_CSV, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    return removed


def append_to_sale_sent_history(
    email: str, name: str, original_subject: str,
    sales_subject: str, sales_body: str, sent_at: str,
) -> None:
    fieldnames = ["Email", "Name", "Original Subject",
                  "Sales Subject", "Sales Body", "Sales Sent At"]
    file_exists = os.path.isfile(SALE_SENT_CSV)
    with open(SALE_SENT_CSV, mode="a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "Email":            email,
            "Name":             name,
            "Original Subject": original_subject,
            "Sales Subject":    sales_subject,
            "Sales Body":       sales_body,
            "Sales Sent At":    sent_at,
        })


# Spam Score Check (mirrors deliverability_agent.py)
def check_spam_score(subject: str, body: str) -> dict:
    combined = f"{subject} {body}".lower()
    score = 0
    found = []
    for severity, words in SPAM_TRIGGERS.items():
        w = SEVERITY_WEIGHTS[severity]
        for word in words:
            if re.search(r"\b" + re.escape(word) + r"\b", combined):
                score += w
                found.append(f"{word} ({severity})")

    words_list = f"{subject} {body}".split()
    caps = [w for w in words_list if w.isupper() and len(w) > 2 and w.isalpha()]
    caps_ratio = len(caps) / max(len(words_list), 1)
    if caps_ratio > 0.1:
        score += 15
    elif caps_ratio > 0.05:
        score += 8

    links = re.findall(r"https?://\S+|www\.\S+", combined)
    if len(links) > 3:
        score += 20
    elif len(links) > 1:
        score += 8

    excl = f"{subject} {body}".count("!")
    if excl > 3:
        score += 10
    elif excl > 1:
        score += 4

    score = min(100, score)
    if score <= 10:
        rating = "excellent"
    elif score <= 25:
        rating = "good"
    elif score <= 45:
        rating = "warning"
    else:
        rating = "dangerous"

    return {"score": score, "rating": rating, "triggers": found}


# Human-like delay (mirrors deliverability_agent.py)
_last_delay: float = 0.0

def get_human_delay(base_min: float = 45.0, base_max: float = 120.0) -> float:
    global _last_delay
    base = random.gauss((base_min + base_max) / 2, (base_max - base_min) / 4)
    base = max(base_min, min(base_max, base))
    jitter = base * random.uniform(-0.15, 0.15)
    delay = base + jitter
    if random.random() < 0.10:
        delay = random.uniform(90, 180)
    while abs(delay - _last_delay) < 5.0:
        delay += random.uniform(3, 15)
    _last_delay = delay
    return round(delay, 1)


# Main Campaign
async def run_sales_campaign():
    print()
    print("=" * 62)
    print("   Nexariza Sales Campaign  --  sales@nexariza.com")
    print("=" * 62)

    if not SALES_SENDER_PASS:
        print("\n[ERROR] SALES_SENDER_PASSWORD is not set in .env")
        sys.exit(1)

    prospects = load_sent_history()
    if not prospects:
        print(f"\n[ERROR] No prospects found in '{SENT_HISTORY_CSV}'")
        sys.exit(1)

    print(f"\n  Prospects available in {SENT_HISTORY_CSV}: {len(prospects)}")

    # Ask count
    while True:
        try:
            raw = input(f"\n  How many people should I email today? (1-200): ").strip()
            count = int(raw)
            if 1 <= count <= 200:
                count = min(count, len(prospects))
                break
            print("  Enter a number between 1 and 200.")
        except ValueError:
            print("  Invalid. Enter a whole number.")

    targets = prospects[:count]
    print(f"\n  Starting: {count} email(s) from {SALES_SENDER_EMAIL}")
    print("  Delays: 45-120s humanized Gaussian jitter between sends")
    print("-" * 62)

    sent_ok: List[str] = []
    failed:  List[str] = []
    skipped: List[str] = []

    for i, prospect in enumerate(targets):
        email    = prospect.get("Email", "").strip()
        name     = prospect.get("Name", "").strip()
        orig_sub = prospect.get("Subject", "").strip()

        if not email:
            skipped.append(f"row_{i+1}")
            continue

        print(f"\n  [{i+1}/{count}] {name or email}  <{email}>")

        # Step 0: Email address validation (syntax + disposable + role-based + MX)
        print("    -> Validating email address...", end=" ", flush=True)
        is_valid, reason = await validate_email_address(email)
        if not is_valid:
            print(f"INVALID — {reason}")
            logger.warning(f"[Validator] Skipping and removing {email} from sent_history: {reason}")
            remove_from_sent_history({email})
            skipped.append(email)
            continue
        print("OK")

        # Step 1: AI generation
        try:
            print("    -> Generating fresh email via AI...", end=" ", flush=True)
            subject, body = await generate_sales_email(
                name=name, email=email, original_subject=orig_sub
            )
            print("Done.")
            print(f"    Subject: {subject[:70]}")
        except Exception as e:
            print("FAILED")
            logger.error(f"AI generation failed for {email}: {e}")
            failed.append(email)
            continue

        # Step 2: Deliverability check
        spam = check_spam_score(subject, body)
        rating_label = spam["rating"].upper()
        print(f"    Spam score: {spam['score']}/100  [{rating_label}]", end="")
        if spam["rating"] == "dangerous":
            print("  <- BLOCKED (too spammy, skipping)")
            skipped.append(email)
            continue
        elif spam["rating"] == "warning":
            print("  <- Warning (borderline, sending anyway)")
        else:
            print()

        # Step 3: Send
        try:
            print("    -> Sending...", end=" ", flush=True)
            await send_sales_email(recipient=email, subject=subject, body=body)
            print("Sent!")

            sent_at = datetime.now(timezone.utc).isoformat()
            sent_ok.append(email)

            # Move record: sent_history -> sale_sent_history
            remove_from_sent_history({email})
            append_to_sale_sent_history(
                email=email,
                name=name,
                original_subject=orig_sub,
                sales_subject=subject,
                sales_body=body,
                sent_at=sent_at,
            )
            logger.info(f"Moved {email}: sent_history.csv -> sale_sent_history.csv")

        except Exception as e:
            print("FAILED")
            logger.error(f"SMTP failed for {email}: {e}")
            failed.append(email)
            continue

        # Step 4: Human-like delay before next send
        if i < len(targets) - 1:
            delay = get_human_delay(45.0, 120.0)
            print(f"    Next send in {delay}s ", end="", flush=True)
            elapsed = 0.0
            while elapsed < delay:
                await asyncio.sleep(1.0)
                elapsed += 1.0
                if int(elapsed) % 15 == 0:
                    print(".", end="", flush=True)
            print()

    # Summary
    print()
    print("=" * 62)
    print("  Campaign Complete")
    print("-" * 62)
    print(f"  Sent:         {len(sent_ok)}")
    print(f"  Failed:       {len(failed)}   (stay in sent_history.csv)")
    print(f"  Skipped:      {len(skipped)}")
    print(f"  Saved to:     {SALE_SENT_CSV}")
    remaining = len(prospects) - len(sent_ok)
    print(f"  Remaining in sent_history: {remaining}")
    print("=" * 62)
    if failed:
        print("\n  Failed (still in sent_history):")
        for e in failed:
            print(f"    - {e}")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(run_sales_campaign())
    except KeyboardInterrupt:
        print("\n\n  [Cancelled] Stopped by user. Partial results saved.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)
