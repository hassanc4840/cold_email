"""
services/session_service.py
----------------------------
Persists "last campaign session" metadata so the agent can remember:
  - Which Google Sheet was used
  - How many emails were sent
  - When the campaign ran
  - What mode was used (live / dry_run)

Data is stored in `last_session.json` in the project root.
"""

import os
import json
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_FILE = "last_session.json"
_lock = Lock()


def save_session(
    sheet_url: str,
    sent_count: int,
    total_leads: int,
    skipped_count: int,
    mode: str,
) -> None:
    """
    Persist session metadata after a campaign run.

    Args:
        sheet_url:     The Google Sheets URL used for this campaign.
        sent_count:    Number of emails actually sent (or previewed in dry_run).
        total_leads:   Total leads pulled from the sheet.
        skipped_count: Leads skipped (already emailed or invalid).
        mode:          Campaign mode ('live' or 'dry_run').
    """
    session = {
        "sheet_url": sheet_url,
        "sent_count": sent_count,
        "total_leads": total_leads,
        "skipped_count": skipped_count,
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)
            logger.info(
                f"[Session] Saved session: sent={sent_count}, total={total_leads}, "
                f"sheet={sheet_url[:60]}..."
            )
        except Exception as e:
            logger.error(f"[Session] Failed to save session: {e}")


def load_session() -> Optional[dict]:
    """
    Load the last campaign session from disk.

    Returns:
        A dict with session metadata, or None if no previous session exists.
    """
    with _lock:
        if not os.path.exists(SESSION_FILE):
            return None
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"[Session] Loaded last session from {SESSION_FILE}")
            return data
        except Exception as e:
            logger.error(f"[Session] Failed to load session: {e}")
            return None


def clear_session() -> None:
    """Remove the saved session file (e.g. for testing or reset)."""
    with _lock:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
            logger.info("[Session] Session file cleared.")
