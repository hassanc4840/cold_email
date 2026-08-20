import os
import json
import csv
import logging
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

HISTORY_FILE = "sent_history.json"
HISTORY_CSV_FILE = "sent_history.csv"
BOUNCE_CSV_FILE = "bounced_emails.csv"
_lock = Lock()


_history_cache = None
_history_mtime = 0.0


def _load_history() -> dict:
    """Load history from the JSON file with mtime caching. Defaults if file does not exist or is corrupted."""
    global _history_cache, _history_mtime
    default_history = {
        "sent_emails": {},
        "processed_replies": [],
        "auto_replies": [],
        "bounced_emails": {}   # email → {name, reason, bounced_at}
    }
    if not os.path.exists(HISTORY_FILE):
        _history_cache = default_history
        _history_mtime = 0.0
        return _history_cache

    try:
        mtime = os.path.getmtime(HISTORY_FILE)
        if _history_cache is not None and mtime == _history_mtime:
            return _history_cache

        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure required keys exist
            for key in default_history:
                if key not in data:
                    data[key] = default_history[key]
            _history_cache = data
            _history_mtime = mtime
            return data
    except Exception as e:
        logger.error(f"Error reading history file {HISTORY_FILE}: {e}")
        if _history_cache is not None:
            return _history_cache
        return default_history


def _save_history(data: dict) -> None:
    """Save history dict to the JSON file and update cache."""
    global _history_cache, _history_mtime
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _history_cache = data
        _history_mtime = os.path.getmtime(HISTORY_FILE) if os.path.exists(HISTORY_FILE) else 0.0
    except Exception as e:
        logger.error(f"Error writing to history file {HISTORY_FILE}: {e}")


def register_sent_email(email: str, name: str, subject: str, body: str) -> None:
    """Record an email that has been sent as part of outreach."""
    email_clean = email.strip().lower()
    sent_at = datetime.utcnow().isoformat() + "Z"
    with _lock:
        history = _load_history()
        history["sent_emails"][email_clean] = {
            "name": name,
            "subject": subject,
            "body": body,
            "sent_at": sent_at
        }
        _save_history(history)
        
        # Also write to CSV
        file_exists = os.path.isfile(HISTORY_CSV_FILE)
        try:
            with open(HISTORY_CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Email", "Name", "Subject", "Body", "Sent At"])
                writer.writerow([email_clean, name, subject, body, sent_at])
        except Exception as e:
            logger.error(f"Error writing to history csv file {HISTORY_CSV_FILE}: {e}")
            
    logger.info(f"Registered outreach email sent to: {email_clean}")


def is_known_prospect(email: str) -> bool:
    """Check if the email belongs to a registered prospect (sent or bounced)."""
    email_clean = email.strip().lower()
    with _lock:
        history = _load_history()
        return (
            email_clean in history["sent_emails"]
            or email_clean in history.get("bounced_emails", {})
        )


def get_prospect_details(email: str) -> Optional[dict]:
    """Retrieve details for a registered prospect."""
    email_clean = email.strip().lower()
    with _lock:
        history = _load_history()
        return history["sent_emails"].get(email_clean)


def get_all_sent_emails() -> dict:
    """Retrieve all sent emails from history."""
    with _lock:
        history = _load_history()
        return history.get("sent_emails", {})


# ── Bounce Tracking ───────────────────────────────────────────────────────────

def register_bounce(email: str, name: str = "", reason: str = "Address not found") -> None:
    """
    Record a hard-bounce for an email address so future campaigns skip it.
    Also appends to bounced_emails.csv for reporting.
    """
    email_clean = email.strip().lower()
    bounced_at = datetime.utcnow().isoformat() + "Z"
    with _lock:
        history = _load_history()
        history.setdefault("bounced_emails", {})[email_clean] = {
            "name": name,
            "reason": reason,
            "bounced_at": bounced_at,
        }
        _save_history(history)

        # CSV append
        file_exists = os.path.isfile(BOUNCE_CSV_FILE)
        try:
            with open(BOUNCE_CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Email", "Name", "Reason", "Bounced At"])
                writer.writerow([email_clean, name, reason, bounced_at])
        except Exception as e:
            logger.error(f"Error writing to bounce csv {BOUNCE_CSV_FILE}: {e}")

    logger.warning(f"[Bounce] Registered hard bounce for: {email_clean} — {reason}")


def is_bounced(email: str) -> bool:
    """Return True if this address previously hard-bounced."""
    email_clean = email.strip().lower()
    with _lock:
        history = _load_history()
        return email_clean in history.get("bounced_emails", {})


def get_all_bounced_emails() -> dict:
    """Return the full bounce dictionary {email: {name, reason, bounced_at}}."""
    with _lock:
        history = _load_history()
        return history.get("bounced_emails", {})


def remove_bounce(email: str) -> bool:
    """
    Remove an email from the bounce list (e.g. after manual verification).
    Returns True if the entry existed and was removed.
    """
    email_clean = email.strip().lower()
    with _lock:
        history = _load_history()
        bounced = history.get("bounced_emails", {})
        if email_clean in bounced:
            del bounced[email_clean]
            history["bounced_emails"] = bounced
            _save_history(history)
            logger.info(f"[Bounce] Removed {email_clean} from bounce list.")
            return True
    return False


# ── Reply Tracking ────────────────────────────────────────────────────────────

def is_reply_processed(message_id: str) -> bool:
    """Check if we have already processed and replied to a specific incoming Message-ID."""
    if not message_id:
        return False
    with _lock:
        history = _load_history()
        return message_id in history["processed_replies"]


def mark_reply_processed(message_id: str) -> None:
    """Mark a specific incoming Message-ID as processed to prevent duplicate replies."""
    if not message_id:
        return
    with _lock:
        history = _load_history()
        if message_id not in history["processed_replies"]:
            history["processed_replies"].append(message_id)
            _save_history(history)


def add_auto_reply(
    email_addr: str,
    incoming_subject: str,
    incoming_snippet: str,
    reply_subject: str,
    reply_body: str
) -> None:
    """Log an AI auto-reply that was sent."""
    email_clean = email_addr.strip().lower()
    with _lock:
        history = _load_history()
        history["auto_replies"].append({
            "recipient": email_clean,
            "incoming_subject": incoming_subject,
            "incoming_snippet": incoming_snippet[:200],  # Keep snippet short
            "reply_subject": reply_subject,
            "reply_body": reply_body,
            "sent_at": datetime.utcnow().isoformat() + "Z"
        })
        _save_history(history)
    logger.info(f"Logged AI auto-reply sent to: {email_clean}")


def get_auto_replies() -> List[dict]:
    """Retrieve all auto-replies sent so far."""
    with _lock:
        history = _load_history()
        return history.get("auto_replies", [])



_history_cache = None
_history_mtime = 0.0


def _load_history() -> dict:
    """Load history from the JSON file with mtime caching. Defaults if file does not exist or is corrupted."""
    global _history_cache, _history_mtime
    default_history = {
        "sent_emails": {},
        "processed_replies": [],
        "auto_replies": []
    }
    if not os.path.exists(HISTORY_FILE):
        _history_cache = default_history
        _history_mtime = 0.0
        return _history_cache

    try:
        mtime = os.path.getmtime(HISTORY_FILE)
        if _history_cache is not None and mtime == _history_mtime:
            return _history_cache

        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure required keys exist
            for key in default_history:
                if key not in data:
                    data[key] = default_history[key]
            _history_cache = data
            _history_mtime = mtime
            return data
    except Exception as e:
        logger.error(f"Error reading history file {HISTORY_FILE}: {e}")
        if _history_cache is not None:
            return _history_cache
        return default_history


def _save_history(data: dict) -> None:
    """Save history dict to the JSON file and update cache."""
    global _history_cache, _history_mtime
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _history_cache = data
        _history_mtime = os.path.getmtime(HISTORY_FILE) if os.path.exists(HISTORY_FILE) else 0.0
    except Exception as e:
        logger.error(f"Error writing to history file {HISTORY_FILE}: {e}")


def register_sent_email(email: str, name: str, subject: str, body: str) -> None:
    """Record an email that has been sent as part of outreach."""
    email_clean = email.strip().lower()
    sent_at = datetime.utcnow().isoformat() + "Z"
    with _lock:
        history = _load_history()
        history["sent_emails"][email_clean] = {
            "name": name,
            "subject": subject,
            "body": body,
            "sent_at": sent_at
        }
        _save_history(history)
        
        # Also write to CSV
        file_exists = os.path.isfile(HISTORY_CSV_FILE)
        try:
            with open(HISTORY_CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Email", "Name", "Subject", "Body", "Sent At"])
                writer.writerow([email_clean, name, subject, body, sent_at])
        except Exception as e:
            logger.error(f"Error writing to history csv file {HISTORY_CSV_FILE}: {e}")
            
    logger.info(f"Registered outreach email sent to: {email_clean}")


def is_known_prospect(email: str) -> bool:
    """Check if the email belongs to a registered prospect."""
    email_clean = email.strip().lower()
    with _lock:
        history = _load_history()
        return email_clean in history["sent_emails"]


def get_prospect_details(email: str) -> Optional[dict]:
    """Retrieve details for a registered prospect."""
    email_clean = email.strip().lower()
    with _lock:
        history = _load_history()
        return history["sent_emails"].get(email_clean)


def get_all_sent_emails() -> dict:
    """Retrieve all sent emails from history."""
    with _lock:
        history = _load_history()
        return history.get("sent_emails", {})

def is_reply_processed(message_id: str) -> bool:
    """Check if we have already processed and replied to a specific incoming Message-ID."""
    if not message_id:
        return False
    with _lock:
        history = _load_history()
        return message_id in history["processed_replies"]


def mark_reply_processed(message_id: str) -> None:
    """Mark a specific incoming Message-ID as processed to prevent duplicate replies."""
    if not message_id:
        return
    with _lock:
        history = _load_history()
        if message_id not in history["processed_replies"]:
            history["processed_replies"].append(message_id)
            _save_history(history)


def add_auto_reply(
    email_addr: str,
    incoming_subject: str,
    incoming_snippet: str,
    reply_subject: str,
    reply_body: str
) -> None:
    """Log an AI auto-reply that was sent."""
    email_clean = email_addr.strip().lower()
    with _lock:
        history = _load_history()
        history["auto_replies"].append({
            "recipient": email_clean,
            "incoming_subject": incoming_subject,
            "incoming_snippet": incoming_snippet[:200],  # Keep snippet short
            "reply_subject": reply_subject,
            "reply_body": reply_body,
            "sent_at": datetime.utcnow().isoformat() + "Z"
        })
        _save_history(history)
    logger.info(f"Logged AI auto-reply sent to: {email_clean}")


def get_auto_replies() -> List[dict]:
    """Retrieve all auto-replies sent so far."""
    with _lock:
        history = _load_history()
        return history.get("auto_replies", [])
