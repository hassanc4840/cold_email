import os
import imaplib
import email
from email.header import decode_header
import asyncio
import logging
import re
from typing import Tuple, Optional

from services.email_service import send_email, get_smtp_config
from services.gemini_service import generate_reply_email
import services.history_service as history_service

logger = logging.getLogger(__name__)

# State management
_active_task: Optional[asyncio.Task] = None
_loop_interval = 30  # seconds


def get_imap_config() -> dict:
    """Load IMAP settings, fallback to SMTP-derived domain if missing."""
    smtp_config = get_smtp_config()
    smtp_server = smtp_config.get("server", "smtp.zoho.com")
    
    # Try parsing smtp host to derive imap host (e.g. smtp.zoho.com -> imap.zoho.com)
    default_imap_server = smtp_server.replace("smtp.", "imap.") if "smtp." in smtp_server else "imap.zoho.com"
    
    return {
        "server": os.getenv("IMAP_SERVER", default_imap_server),
        "port": int(os.getenv("IMAP_PORT", "993")),
        "email": smtp_config.get("email", ""),
        "password": smtp_config.get("password", ""),
    }


def clean_header(header_val: str) -> str:
    """Decode email header fields safely."""
    if not header_val:
        return ""
    decoded_parts = decode_header(header_val)
    header_text = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                header_text.append(part.decode(encoding or "utf-8", errors="replace"))
            except Exception:
                header_text.append(part.decode("utf-8", errors="replace"))
        else:
            header_text.append(str(part))
    return "".join(header_text)


def parse_sender_email(from_header: str) -> Tuple[str, str]:
    """Parse From header into display name and email address."""
    name, addr = email.utils.parseaddr(from_header)
    return name, addr.strip().lower()


def get_email_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message, walking parts if multipart."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    return payload.decode(errors="replace")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            return payload.decode(errors="replace")
        except Exception:
            pass
    return ""


_BOUNCE_ADDR_PATTERNS = [
    # RFC 3464 DSN: "Final-Recipient: rfc822; user@domain.com"
    re.compile(r"Final-Recipient\s*:\s*rfc822\s*;\s*([^\s\r\n]+)", re.IGNORECASE),
    # Google: "Your message wasn't delivered to user@domain.com"
    re.compile(r"wasn't delivered to\s+([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})", re.IGNORECASE),
    # Generic "delivery failed to user@domain.com"
    re.compile(r"delivery[^\n]*?to\s+<?([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>?", re.IGNORECASE),
    # "failed to deliver ... <user@domain.com>"
    re.compile(r"<([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})>"),
]

_BOUNCE_REASON_PATTERNS = [
    # RFC 3464 DSN: "Diagnostic-Code: smtp; 550 ..."
    re.compile(r"Diagnostic-Code\s*:.*?(\d{3}[^\r\n]+)", re.IGNORECASE | re.DOTALL),
    # Status code
    re.compile(r"Status\s*:\s*(\d\.\d\.\d[^\r\n]*)", re.IGNORECASE),
    # Plain English reason (Google style)
    re.compile(r"(address couldn't be found[^\.\n]*|user doesn't exist[^\.\n]*|no such user[^\.\n]*|mailbox not found[^\.\n]*|account.*?doesn't exist[^\.\n]*)", re.IGNORECASE),
]


def _extract_bounced_address(body: str, subject: str) -> str:
    """
    Parse a bounce notification body (and subject) to find the failed recipient
    email address. Returns empty string if not found.
    """
    search_text = f"{subject}\n{body}"
    for pattern in _BOUNCE_ADDR_PATTERNS:
        m = pattern.search(search_text)
        if m:
            addr = m.group(1).strip().strip("<>").lower()
            # Basic sanity check
            if "@" in addr and "." in addr.split("@")[-1]:
                return addr
    return ""


def _extract_bounce_reason(body: str, subject: str) -> str:
    """
    Parse a bounce notification body to find a human-readable failure reason.
    Defaults to 'Delivery failure' if nothing specific is found.
    """
    search_text = f"{subject}\n{body}"
    for pattern in _BOUNCE_REASON_PATTERNS:
        m = pattern.search(search_text)
        if m:
            return m.group(1).strip()[:200]
    # Fallback: use subject line
    if subject:
        return subject[:150]
    return "Delivery failure"


async def check_inbox_and_reply() -> dict:
    """
    Connect to IMAP, scan UNSEEN emails, detect replies, generate responses,
    send replies, mark messages as read, and return logs.
    """
    config = get_imap_config()
    if not config["email"] or not config["password"]:
        logger.warning("IMAP configuration incomplete (missing credentials)")
        return {"status": "error", "message": "Email credentials missing"}

    logger.info(f"Connecting to IMAP server: {config['server']}:{config['port']}...")
    loop = asyncio.get_event_loop()
    
    # Run synchronous network connection and search operations in an executor
    def _imap_operations():
        processed_count = 0
        replied_count = 0
        errors = []

        try:
            mail = imaplib.IMAP4_SSL(config["server"], config["port"])
            mail.login(config["email"], config["password"])
            mail.select("INBOX")
            
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                mail.close()
                mail.logout()
                return 0, 0, []

            message_ids = messages[0].split()
            logger.info(f"Found {len(message_ids)} unread email(s) in inbox.")

            for num in message_ids:
                # Fetch message headers and body
                status, data = mail.fetch(num, "(RFC822)")
                if status != "OK":
                    continue
                
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Extract meta-data
                msg_id = msg.get("Message-ID", "")
                subject = clean_header(msg.get("Subject", "No Subject"))
                from_header = clean_header(msg.get("From", ""))
                display_name, sender_email = parse_sender_email(from_header)
                
                # Mark as seen so we don't process it again in the next loop
                mail.store(num, "+FLAGS", "\\Seen")
                processed_count += 1

                # ── Bounce detection: mailer-daemon delivery failure ──────────
                sender_lower = sender_email.lower()
                is_bounce = (
                    "mailer-daemon" in sender_lower
                    or "postmaster" in sender_lower
                    or "delivery" in sender_lower
                )
                if is_bounce:
                    body_content = get_email_body(msg)
                    # Try to extract the failed recipient from common bounce patterns
                    failed_addr = _extract_bounced_address(body_content, subject)
                    if failed_addr:
                        from services.history_service import register_bounce
                        # Pull a reason from the subject or body
                        reason = _extract_bounce_reason(body_content, subject)
                        register_bounce(email=failed_addr, reason=reason)
                        logger.warning(
                            f"[Bounce] Auto-detected hard bounce for {failed_addr}: {reason}"
                        )
                    continue  # Don't try to auto-reply to mailer-daemon

                # Check if we should reply

                if not sender_email or sender_email == config["email"].lower():
                    # Skip empty sender or emails from ourselves
                    continue
                
                if history_service.is_known_prospect(sender_email):
                    if not history_service.is_reply_processed(msg_id):
                        body_content = get_email_body(msg)
                        prospect_details = history_service.get_prospect_details(sender_email)
                        
                        prospect_name = prospect_details.get("name") or display_name or "there"
                        orig_subject = prospect_details.get("subject") or "Outreach"
                        orig_body = prospect_details.get("body") or ""

                        logger.info(f"Processing replica/reply from lead: {sender_email}")
                        
                        # Generate the AI reply in async context outside executor,
                        # but we need to execute the send/log within here, or run them async.
                        # To keep it safe, let's run the generation.
                        # Wait! Since we are inside the sync executor thread, we cannot directly await.
                        # So we fetch the data we need, then run generation & delivery asynchronously in the main loop!
                        # We will return list of tasks to execute.
                        yield_info = {
                            "email": sender_email,
                            "name": prospect_name,
                            "orig_subject": orig_subject,
                            "orig_body": orig_body,
                            "incoming_subject": subject,
                            "incoming_body": body_content,
                            "msg_id": msg_id
                        }
                        try:
                            mail.close()
                            mail.logout()
                        except Exception:
                            pass
                        return "reply_needed", yield_info, None, processed_count, replied_count, errors
                        
            mail.close()
            mail.logout()
            return "done", None, None, processed_count, replied_count, errors
        except Exception as e:
            logger.error(f"IMAP operation error: {e}")
            return "error", str(e), None, 0, 0, [str(e)]

    # We will loop in async, running IMAP scanning step by step
    processed = 0
    replied = 0
    errors = []
    
    while True:
        action, info, mail_conn, p, r, errs = await loop.run_in_executor(None, _imap_operations)
        processed += p
        replied += r
        errors.extend(errs)
        
        if action == "error":
            return {"status": "error", "message": info, "processed": processed, "replied": replied}
        
        if action == "done" or action == 0:
            break
            
        if action == "reply_needed":
            # Generate reply
            try:
                reply_subject, reply_body = await generate_reply_email(
                    prospect_name=info["name"],
                    prospect_email=info["email"],
                    original_subject=info["orig_subject"],
                    original_body=info["orig_body"],
                    incoming_email_body=info["incoming_body"]
                )
                
                # Send email via SMTP
                send_email(
                    recipient=info["email"],
                    subject=reply_subject,
                    body=reply_body
                )
                
                # Mark as processed in database
                history_service.mark_reply_processed(info["msg_id"])
                history_service.add_auto_reply(
                    email_addr=info["email"],
                    incoming_subject=info["incoming_subject"],
                    incoming_snippet=info["incoming_body"],
                    reply_subject=reply_subject,
                    reply_body=reply_body
                )
                replied += 1
            except Exception as ex:
                logger.error(f"Failed to auto-reply to {info['email']}: {ex}")
                errors.append(f"Auto-reply failed to {info['email']}: {str(ex)}")
                
    return {
        "status": "ok",
        "processed": processed,
        "replied": replied,
        "errors": errors
    }


async def _run_loop():
    """Background task loop to check inbox periodically."""
    logger.info("Starting AI Auto-Responder background task...")
    while True:
        try:
            await check_inbox_and_reply()
        except Exception as e:
            logger.error(f"Error in background responder loop: {e}")
        await asyncio.sleep(_loop_interval)


def start_responder():
    """Start the background auto-responder task."""
    global _active_task
    if _active_task is not None and not _active_task.done():
        logger.info("Auto-Responder is already running.")
        return False
        
    _active_task = asyncio.create_task(_run_loop())
    logger.info("Auto-Responder background task started successfully.")
    return True


def stop_responder():
    """Stop the background auto-responder task."""
    global _active_task
    if _active_task is None or _active_task.done():
        logger.info("Auto-Responder is not running.")
        return False
        
    _active_task.cancel()
    _active_task = None
    logger.info("Auto-Responder background task stopped.")
    return True


def is_responder_active() -> bool:
    """Return whether the auto-responder background task is running."""
    global _active_task
    return _active_task is not None and not _active_task.done()
