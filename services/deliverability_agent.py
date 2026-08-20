"""
deliverability_agent.py
-----------------------
Inbox Deliverability Agent for Nexariza AI Outreach.

Ensures cold emails land in the recipient's PRIMARY INBOX (not spam) by:
1. Pre-send spam score analysis (subject + body scanning)
2. Smart email header injection (Message-ID, Date, Reply-To)
3. Domain warmup tracking with graduated daily limits
4. Human-like randomized send delays
5. Content fingerprint variation via AI rewriting
6. Live DNS health checks (SPF, DKIM, DMARC)
"""

import os
import re
import json
import random
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Optional, Tuple, List, Dict
from threading import Lock

import dns.asyncresolver
import dns.resolver
import dns.exception

logger = logging.getLogger(__name__)

# ── File Paths ────────────────────────────────────────────────────────────────
WARMUP_FILE = "warmup_tracker.json"
_warmup_lock = Lock()

# ── Warmup Schedule ──────────────────────────────────────────────────────────
# Graduated sending limits to build domain reputation
WARMUP_SCHEDULE = {
    # (start_day, end_day): daily_limit
    (1, 7):    10,   # Week 1: Max 10 emails/day
    (8, 14):   25,   # Week 2: Max 25 emails/day
    (15, 21):  50,   # Week 3: Max 50 emails/day
    (22, 30):  80,   # Week 4: Max 80 emails/day
    (31, 999): 150,  # Week 5+: Full volume
}


# ── Spam Trigger Words ───────────────────────────────────────────────────────
# Words and phrases that trigger spam filters across Gmail, Outlook, Yahoo
SPAM_TRIGGER_WORDS = {
    # High severity (3 points each)
    "high": [
        "free", "urgent", "act now", "limited time", "click here",
        "buy now", "guaranteed", "no cost", "risk-free", "winner",
        "congratulations", "100%", "special offer", "discount",
        "money back", "cash bonus", "earn money", "make money",
        "double your", "million dollars", "credit card", "no obligation",
        "lowest price", "best price", "order now", "apply now",
        "exclusive deal", "incredible deal", "once in a lifetime",
        "time limited", "clearance", "bargain", "bonus",
        "cheap", "compare rates", "do it today", "don't miss out",
        "for free", "get it now", "give it away", "last chance",
        "new customers only", "prize", "save big", "while supplies last",
        "you have been selected", "you're a winner", "claim your",
        "no strings attached", "obligation free",
    ],
    # Medium severity (2 points each)
    "medium": [
        "as seen on", "call now", "click below", "dear friend",
        "for instant access", "great offer", "info you requested",
        "not spam", "please read", "satisfaction guaranteed",
        "this isn't spam", "what are you waiting for",
        "why pay more", "you won't believe", "accept credit cards",
        "billing address", "bulk rate", "increase revenue",
        "mass email", "open immediately", "opt in", "performance",
        "potential earnings", "pure profit", "removes wrinkles",
        "reverses aging", "risk free", "stop paying", "weight loss",
        "meet singles", "online degree", "casino", "viagra",
    ],
    # Low severity (1 point each)
    "low": [
        "amazing", "cancel anytime", "check or money order",
        "confidential", "cures", "diagnostics", "fast cash",
        "for just", "hidden", "human growth", "investment",
        "lose weight", "luxury", "miracle", "multi-level marketing",
        "natural", "nigerian", "obligation", "passwords",
        "pennies", "profits", "promise", "pure",
        "refinance", "refund", "request", "requires initial investment",
        "reverses", "sample", "serious", "success",
        "supplies", "trial", "unlimited", "unsolicited",
        "vacation", "valium", "visit our website", "voluntary",
    ],
}

# Weights per severity
SEVERITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}

# Spam score thresholds
SCORE_THRESHOLDS = {
    "excellent": (0, 10),    # 0-10: Excellent — send immediately
    "good": (11, 25),        # 11-25: Good — safe to send
    "warning": (26, 45),     # 26-45: Warning — consider rewording
    "dangerous": (46, 100),  # 46+: Dangerous — will likely hit spam
}


# ── 1. SPAM SCORE ANALYSIS ──────────────────────────────────────────────────

def check_deliverability_score(subject: str, body: str) -> dict:
    """
    Analyze subject + body for spam triggers and return a deliverability score.
    
    Returns:
        {
            "score": int (0-100, lower is better),
            "rating": str ("excellent" | "good" | "warning" | "dangerous"),
            "warnings": list[str],
            "details": {
                "spam_words_found": list[str],
                "caps_ratio": float,
                "link_count": int,
                "exclamation_count": int,
                "has_unsubscribe": bool,
                "subject_length": int,
            }
        }
    """
    warnings = []
    penalty_points = 0
    spam_words_found = []
    
    combined_text = f"{subject} {body}".lower()
    combined_original = f"{subject} {body}"
    
    # ── Check spam trigger words ──────────────────────────────────────────
    for severity, words in SPAM_TRIGGER_WORDS.items():
        weight = SEVERITY_WEIGHTS[severity]
        for word in words:
            # Use word boundary matching to avoid false positives
            pattern = r'\b' + re.escape(word) + r'\b'
            matches = re.findall(pattern, combined_text)
            if matches:
                penalty_points += weight * len(matches)
                spam_words_found.append(f"{word} ({severity}, x{len(matches)})")
    
    if spam_words_found:
        warnings.append(f"Found {len(spam_words_found)} spam trigger word(s)")
    
    # ── Check ALL CAPS words (more than 2 characters) ─────────────────────
    words_in_text = combined_original.split()
    caps_words = [w for w in words_in_text if w.isupper() and len(w) > 2 and w.isalpha()]
    caps_ratio = len(caps_words) / max(len(words_in_text), 1)
    
    if caps_ratio > 0.1:
        penalty_points += 15
        warnings.append(f"Too many ALL CAPS words ({len(caps_words)} found, {caps_ratio:.0%} ratio)")
    elif caps_ratio > 0.05:
        penalty_points += 8
        warnings.append(f"Some ALL CAPS words detected ({len(caps_words)} found)")
    
    # ── Check link count ──────────────────────────────────────────────────
    link_pattern = r'https?://[^\s<>\"\')\]]+|www\.[^\s<>\"\')\]]+'
    links = re.findall(link_pattern, combined_text)
    link_count = len(links)
    
    if link_count > 3:
        penalty_points += 20
        warnings.append(f"Too many links ({link_count}). Keep to 1-2 max for cold emails.")
    elif link_count > 1:
        penalty_points += 8
        warnings.append(f"Multiple links ({link_count}). 1 link is ideal for cold emails.")
    
    # ── Check exclamation marks ───────────────────────────────────────────
    exclamation_count = combined_original.count("!")
    if exclamation_count > 3:
        penalty_points += 10
        warnings.append(f"Too many exclamation marks ({exclamation_count})")
    elif exclamation_count > 1:
        penalty_points += 4
        warnings.append(f"Multiple exclamation marks ({exclamation_count})")
    
    # ── Check subject line ────────────────────────────────────────────────
    subject_length = len(subject)
    if subject_length > 70:
        penalty_points += 5
        warnings.append(f"Subject line too long ({subject_length} chars). Keep under 60.")
    elif subject_length < 10:
        penalty_points += 5
        warnings.append(f"Subject line too short ({subject_length} chars). Aim for 20-50.")
    
    # Subject with all caps
    if subject.isupper():
        penalty_points += 15
        warnings.append("Subject line is ALL CAPS — major spam signal")
    
    # Subject starts with "Re:" or "Fwd:" (fake reply/forward)
    if re.match(r'^(Re:|Fwd:|FW:)\s', subject) and link_count > 0:
        penalty_points += 10
        warnings.append("Subject mimics a reply/forward with links — spam signal")
    
    # ── Check for unsubscribe link (Promotions tab trigger) ───────────────
    has_unsubscribe = "unsubscribe" in combined_text
    if has_unsubscribe:
        penalty_points += 10
        warnings.append("Body contains 'unsubscribe' — will trigger Gmail Promotions tab")
    
    # ── Check emoji usage (subtle penalty) ────────────────────────────────
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U0001f926-\U0001f937"
        "\U00010000-\U0010ffff"
        "]+", 
        flags=re.UNICODE
    )
    emojis = emoji_pattern.findall(combined_original)
    if len(emojis) > 2:
        penalty_points += 8
        warnings.append(f"Too many emojis ({len(emojis)}). Cold emails should use 0-1.")
    
    # ── Calculate final score (cap at 100) ────────────────────────────────
    score = min(100, penalty_points)
    
    # Determine rating
    rating = "excellent"
    for label, (low, high) in SCORE_THRESHOLDS.items():
        if low <= score <= high:
            rating = label
            break
    
    if not warnings:
        warnings.append("Clean — no spam triggers detected")
    
    return {
        "score": score,
        "rating": rating,
        "warnings": warnings,
        "details": {
            "spam_words_found": spam_words_found,
            "caps_ratio": round(caps_ratio, 3),
            "link_count": link_count,
            "exclamation_count": exclamation_count,
            "has_unsubscribe": has_unsubscribe,
            "subject_length": subject_length,
        }
    }


# ── 2. SMART EMAIL HEADERS ──────────────────────────────────────────────────

def apply_deliverability_headers(msg: EmailMessage, sender_domain: str = "nexariza.com") -> EmailMessage:
    """
    Add/fix deliverability-critical email headers.
    
    These headers make the email look like it was sent from a legitimate 
    email client (Outlook, Gmail, Apple Mail) rather than an automated script.
    """
    # Unique Message-ID using the sender's domain (critical for threading + trust)
    if "Message-ID" not in msg:
        msg["Message-ID"] = make_msgid(domain=sender_domain)
    
    # RFC 2822 Date header (some spam filters penalize missing/wrong dates)
    if "Date" not in msg:
        msg["Date"] = formatdate(localtime=True)
    
    # MIME-Version (should always be present)
    if "MIME-Version" not in msg:
        msg["MIME-Version"] = "1.0"
    
    # Reply-To matching From (alignment = trust signal)
    from_addr = msg.get("From", "")
    if "Reply-To" not in msg and from_addr:
        # Extract just the email address from "Name <email>" format
        import email.utils
        _, email_addr = email.utils.parseaddr(from_addr)
        if email_addr:
            msg["Reply-To"] = email_addr
    
    # Remove headers that mark email as automated/bulk (spam signals!)
    for bad_header in ["X-Mailer", "X-Auto-Response-Suppress", "Precedence"]:
        if bad_header in msg:
            del msg[bad_header]
    
    # Remove priority headers for cold emails (looks aggressive/spammy)
    # Only keep these for transactional/internal emails
    for priority_header in ["X-Priority", "Importance", "Priority", "X-MSMail-Priority"]:
        if priority_header in msg:
            del msg[priority_header]
    
    return msg


# ── 3. DOMAIN WARMUP TRACKING ───────────────────────────────────────────────

def _load_warmup() -> dict:
    """Load warmup tracker from JSON file."""
    default = {
        "start_date": None,
        "daily_sends": {},  # {"2026-07-24": 5, ...}
    }
    if not os.path.exists(WARMUP_FILE):
        return default
    try:
        with open(WARMUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for key in default:
                if key not in data:
                    data[key] = default[key]
            return data
    except Exception as e:
        logger.error(f"Error reading warmup file: {e}")
        return default


def _save_warmup(data: dict) -> None:
    """Save warmup tracker to JSON file."""
    try:
        with open(WARMUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing warmup file: {e}")


def get_warmup_status() -> dict:
    """
    Get current warmup status.
    
    Returns:
        {
            "warmup_day": int,
            "daily_limit": int,
            "sent_today": int,
            "remaining": int,
            "start_date": str,
            "phase": str ("week1" | "week2" | "week3" | "week4" | "full_volume"),
            "is_warmed_up": bool,
        }
    """
    with _warmup_lock:
        data = _load_warmup()
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Initialize start date if first time
    if not data["start_date"]:
        data["start_date"] = today
        with _warmup_lock:
            _save_warmup(data)
    
    # Calculate warmup day
    start = datetime.strptime(data["start_date"], "%Y-%m-%d")
    now = datetime.strptime(today, "%Y-%m-%d")
    warmup_day = (now - start).days + 1  # Day 1, 2, 3, ...
    
    # Find daily limit from schedule
    daily_limit = 150  # Default to max
    phase = "full_volume"
    for (start_day, end_day), limit in WARMUP_SCHEDULE.items():
        if start_day <= warmup_day <= end_day:
            daily_limit = limit
            if end_day <= 7:
                phase = "week1"
            elif end_day <= 14:
                phase = "week2"
            elif end_day <= 21:
                phase = "week3"
            elif end_day <= 30:
                phase = "week4"
            else:
                phase = "full_volume"
            break
    
    sent_today = data["daily_sends"].get(today, 0)
    remaining = max(0, daily_limit - sent_today)
    
    return {
        "warmup_day": warmup_day,
        "daily_limit": daily_limit,
        "sent_today": sent_today,
        "remaining": remaining,
        "start_date": data["start_date"],
        "phase": phase,
        "is_warmed_up": warmup_day > 30,
    }


def record_send() -> bool:
    """
    Record a sent email for warmup tracking.
    Returns True if under daily limit, False if limit exceeded (should block send).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    with _warmup_lock:
        data = _load_warmup()
        
        # Initialize start date if first time
        if not data["start_date"]:
            data["start_date"] = today
        
        sent_today = data["daily_sends"].get(today, 0)
        
        # Check warmup day and limit
        start = datetime.strptime(data["start_date"], "%Y-%m-%d")
        now = datetime.strptime(today, "%Y-%m-%d")
        warmup_day = (now - start).days + 1
        
        daily_limit = 150
        for (start_day, end_day), limit in WARMUP_SCHEDULE.items():
            if start_day <= warmup_day <= end_day:
                daily_limit = limit
                break
        
        if sent_today >= daily_limit:
            logger.warning(
                f"Warmup limit reached! Day {warmup_day}: {sent_today}/{daily_limit} sent. "
                f"Blocking further sends today."
            )
            return False
        
        data["daily_sends"][today] = sent_today + 1
        
        # Clean up old entries (keep last 60 days)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
        data["daily_sends"] = {
            k: v for k, v in data["daily_sends"].items() if k >= cutoff
        }
        
        _save_warmup(data)
        return True


def reset_warmup() -> dict:
    """Reset warmup tracker (starts fresh from today)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = {
        "start_date": today,
        "daily_sends": {},
    }
    with _warmup_lock:
        _save_warmup(data)
    logger.info("Warmup tracker reset. Starting fresh from today.")
    return get_warmup_status()


# ── 4. HUMAN-LIKE SEND DELAYS ───────────────────────────────────────────────

# Track last delay to avoid repetition
_last_delay: float = 0.0

def get_human_delay(base_min: float = 45.0, base_max: float = 120.0) -> float:
    """
    Generate a randomized, human-like delay between email sends.
    
    - Base range: 45-120 seconds (configurable)
    - Adds +/-15% jitter
    - Never returns the same delay twice in a row
    - Occasionally adds a longer "reading" pause (simulates human checking inbox)
    
    Returns: delay in seconds
    """
    global _last_delay
    
    # Base delay with gaussian distribution (clusters around the middle)
    base = random.gauss((base_min + base_max) / 2, (base_max - base_min) / 4)
    base = max(base_min, min(base_max, base))  # Clamp to range
    
    # Add +/-15% jitter
    jitter = base * random.uniform(-0.15, 0.15)
    delay = base + jitter
    
    # 10% chance of a longer "thinking" pause (90-180 seconds)
    if random.random() < 0.10:
        delay = random.uniform(90, 180)
    
    # Avoid identical consecutive delays
    while abs(delay - _last_delay) < 5.0:
        delay += random.uniform(3, 15)
    
    _last_delay = delay
    return round(delay, 1)


# ── 5. CONTENT FINGERPRINT CHECK ────────────────────────────────────────────

# In-memory cache of recent email content hashes (last 100)
_recent_content_hashes: List[str] = []
_MAX_HASH_HISTORY = 100

def _compute_content_hash(text: str) -> str:
    """Compute a normalized content hash to detect near-identical emails."""
    # Normalize: lowercase, remove extra whitespace, remove punctuation
    normalized = re.sub(r'[^\w\s]', '', text.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def check_content_uniqueness(subject: str, body: str) -> dict:
    """
    Check if this email content is too similar to recently sent emails.
    
    Returns:
        {
            "is_unique": bool,
            "similarity_warning": str or None,
            "hash": str,
        }
    """
    content = f"{subject}\n{body}"
    content_hash = _compute_content_hash(content)
    
    if content_hash in _recent_content_hashes:
        return {
            "is_unique": False,
            "similarity_warning": (
                "This email has identical or near-identical content to a recently sent email. "
                "Spam filters detect bulk identical content. Consider rewording."
            ),
            "hash": content_hash,
        }
    
    return {
        "is_unique": True,
        "similarity_warning": None,
        "hash": content_hash,
    }


def register_sent_content(subject: str, body: str) -> None:
    """Register sent content hash in the recent history."""
    global _recent_content_hashes
    content = f"{subject}\n{body}"
    content_hash = _compute_content_hash(content)
    
    _recent_content_hashes.append(content_hash)
    
    # Keep only last N hashes
    if len(_recent_content_hashes) > _MAX_HASH_HISTORY:
        _recent_content_hashes = _recent_content_hashes[-_MAX_HASH_HISTORY:]


# ── 6. DNS DOMAIN HEALTH CHECK ──────────────────────────────────────────────

async def check_domain_health(domain: str = "nexariza.com") -> dict:
    """
    Perform live DNS checks for SPF, DKIM, and DMARC records.
    
    Returns:
        {
            "domain": str,
            "overall_score": int (0-100),
            "overall_rating": str,
            "spf": {"status": str, "record": str, "issues": list[str]},
            "dkim": {"status": str, "record": str, "issues": list[str]},
            "dmarc": {"status": str, "record": str, "issues": list[str]},
            "mx": {"status": str, "records": list[str]},
        }
    """
    results = {
        "domain": domain,
        "overall_score": 0,
        "overall_rating": "poor",
        "spf": {"status": "missing", "record": None, "issues": []},
        "dkim": {"status": "missing", "record": None, "issues": []},
        "dmarc": {"status": "missing", "record": None, "issues": []},
        "mx": {"status": "missing", "records": []},
    }
    
    score = 0
    
    # ── MX Records ────────────────────────────────────────────────────────
    try:
        answers = await dns.asyncresolver.resolve(domain, "MX")
        mx_records = [str(r.exchange).rstrip(".") for r in sorted(answers, key=lambda r: r.preference)]
        results["mx"]["status"] = "pass"
        results["mx"]["records"] = mx_records
        score += 20
    except Exception:
        results["mx"]["status"] = "fail"
        results["mx"]["records"] = []
    
    # ── SPF Record ────────────────────────────────────────────────────────
    try:
        answers = await dns.asyncresolver.resolve(domain, "TXT")
        for rdata in answers:
            txt = str(rdata).strip('"')
            if txt.startswith("v=spf1"):
                results["spf"]["record"] = txt
                results["spf"]["status"] = "pass"
                score += 20
                
                # Check for softfail vs hardfail
                if "~all" in txt:
                    results["spf"]["issues"].append(
                        "Using ~all (softfail). Change to -all (hardfail) for stronger protection."
                    )
                    score -= 5
                elif "+all" in txt:
                    results["spf"]["issues"].append(
                        "CRITICAL: Using +all allows ANYONE to send from your domain!"
                    )
                    score -= 15
                elif "?all" in txt:
                    results["spf"]["issues"].append(
                        "Using ?all (neutral). Change to -all (hardfail) for stronger protection."
                    )
                    score -= 10
                break
    except Exception:
        results["spf"]["issues"].append("No SPF record found. Add one to authorize your mail server.")
    
    # ── DKIM Record ───────────────────────────────────────────────────────
    # Try common DKIM selectors for Zoho
    dkim_selectors = ["zmail._domainkey", "zoho._domainkey", "default._domainkey", "google._domainkey"]
    dkim_found = False
    
    for selector in dkim_selectors:
        try:
            dkim_domain = f"{selector}.{domain}"
            answers = await dns.asyncresolver.resolve(dkim_domain, "TXT")
            for rdata in answers:
                txt = str(rdata).strip('"')
                if "DKIM1" in txt or "k=rsa" in txt:
                    results["dkim"]["record"] = f"{selector}: {txt[:80]}..."
                    results["dkim"]["status"] = "pass"
                    score += 30
                    dkim_found = True
                    break
        except Exception:
            continue
        if dkim_found:
            break
    
    if not dkim_found:
        results["dkim"]["issues"].append(
            "No DKIM record found. Enable DKIM in your email provider's admin panel."
        )
    
    # ── DMARC Record ──────────────────────────────────────────────────────
    try:
        dmarc_domain = f"_dmarc.{domain}"
        answers = await dns.asyncresolver.resolve(dmarc_domain, "TXT")
        for rdata in answers:
            txt = str(rdata).strip('"')
            if txt.startswith("v=DMARC1"):
                results["dmarc"]["record"] = txt
                results["dmarc"]["status"] = "pass"
                score += 30
                
                # Check policy
                if "p=none" in txt:
                    results["dmarc"]["issues"].append(
                        "DMARC policy is 'none' (monitoring only). "
                        "Consider upgrading to 'quarantine' or 'reject' after verifying DKIM."
                    )
                    score -= 5
                
                # Check if DKIM is missing but DMARC is reject
                if not dkim_found and "p=reject" in txt:
                    results["dmarc"]["issues"].append(
                        "WARNING: DMARC set to 'reject' but DKIM is missing. "
                        "Emails may be rejected by strict receivers!"
                    )
                    score -= 15
                break
    except Exception:
        results["dmarc"]["issues"].append(
            "No DMARC record found. Add one to protect your domain from spoofing."
        )
    
    # ── Overall Rating ────────────────────────────────────────────────────
    score = max(0, min(100, score))
    results["overall_score"] = score
    
    if score >= 85:
        results["overall_rating"] = "excellent"
    elif score >= 65:
        results["overall_rating"] = "good"
    elif score >= 40:
        results["overall_rating"] = "fair"
    else:
        results["overall_rating"] = "poor"
    
    return results


# ── 7. PRE-SEND GATE (combines all checks) ──────────────────────────────────

def pre_send_check(subject: str, body: str) -> dict:
    """
    Run all deliverability checks before sending an email.
    Returns a go/no-go decision with reasons.
    
    Returns:
        {
            "can_send": bool,
            "block_reasons": list[str],
            "warnings": list[str],
            "deliverability_score": dict,
            "warmup_status": dict,
            "content_unique": bool,
        }
    """
    block_reasons = []
    warnings = []
    
    # 1. Deliverability score
    score_result = check_deliverability_score(subject, body)
    if score_result["rating"] == "dangerous":
        block_reasons.append(
            f"Deliverability score too low: {score_result['score']}/100 ({score_result['rating']}). "
            f"Rewrite the email to remove spam triggers."
        )
    elif score_result["rating"] == "warning":
        warnings.append(
            f"Deliverability score is borderline: {score_result['score']}/100. "
            f"Consider rewording to improve inbox placement."
        )
    
    # 2. Warmup limit
    warmup = get_warmup_status()
    if warmup["remaining"] <= 0:
        block_reasons.append(
            f"Daily warmup limit reached ({warmup['sent_today']}/{warmup['daily_limit']}). "
            f"Warmup day {warmup['warmup_day']}, phase: {warmup['phase']}. "
            f"Try again tomorrow."
        )
    elif warmup["remaining"] <= 3:
        warnings.append(
            f"Almost at daily warmup limit: {warmup['sent_today']}/{warmup['daily_limit']} sent. "
            f"Only {warmup['remaining']} remaining today."
        )
    
    # 3. Content uniqueness
    uniqueness = check_content_uniqueness(subject, body)
    if not uniqueness["is_unique"]:
        warnings.append(uniqueness["similarity_warning"])
    
    can_send = len(block_reasons) == 0
    
    return {
        "can_send": can_send,
        "block_reasons": block_reasons,
        "warnings": warnings,
        "deliverability_score": score_result,
        "warmup_status": warmup,
        "content_unique": uniqueness["is_unique"],
    }
