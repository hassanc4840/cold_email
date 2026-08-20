"""
email_service.py
----------------
Handles SMTP email delivery via Zoho Mail (or any SSL SMTP server).
All outgoing emails are sent as branded HTML with the Nexariza logo signature.
"""

import os
import smtplib
import ssl
import logging
import asyncio
import socket
import time
from email.message import EmailMessage
from typing import Optional
import dns.asyncresolver
import dns.resolver
import dns.exception
import aiosmtplib
from cachetools import TTLCache
from email_validator import validate_email, EmailNotValidError

ROLE_BASED_PREFIXES = {
    "admin", "info", "sales", "support", "contact", "billing", "hello",
    "marketing", "office", "help", "security", "webmaster", "postmaster"
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "10minutemail.com", "temp-mail.org", "guerrillamail.com",
    "sharklasers.com", "yopmail.com", "trashmail.com", "getnada.com"
}

logger = logging.getLogger(__name__)

# ── Nexariza Brand Assets ─────────────────────────────────────────────────────
NEXARIZA_LOGO_URL   = "https://nexariza.com/Nexariza%203d%20Logo.webp"
NEXARIZA_WEBSITE    = "https://nexariza.com"
NEXARIZA_WHATSAPP   = "https://wa.me/923707348001"
NEXARIZA_EMAIL      = "contact@nexariza.com"
NEXARIZA_PHONE      = "+92-370-7348001"


# ── HTML Email Builder ────────────────────────────────────────────────────────

# Nexariza branded HTML signature — strictly 1 clickable link (www.nexariza.com) for optimal deliverability
_NEXARIZA_HTML_SIGNATURE = """
<table cellpadding="0" cellspacing="0" border="0"
       style="font-family:Arial,Helvetica,sans-serif;margin-top:24px;border-top:2px solid #1a73e8;padding-top:16px;">
  <tr>
    <!-- Logo -->
    <td style="vertical-align:middle;padding-right:18px;">
      <img src="https://nexariza.com/Nexariza%203d%20Logo.webp"
           alt="Nexariza AI" width="72" height="72"
           style="border-radius:50%;border:2px solid #1a73e8;display:block;"
           onerror="this.style.display='none'" />
    </td>
    <!-- Name / Title -->
    <td style="vertical-align:middle;border-right:1px solid #d0d0d0;padding-right:18px;">
      <div style="font-size:17px;font-weight:700;color:#1a73e8;letter-spacing:0.3px;">AHMAD YASIN</div>
      <div style="font-size:13px;color:#444;margin-top:2px;">Founder &amp; CEO &mdash; Nexariza Ai</div>
    </td>
    <!-- Contact details (clean text + single official website link) -->
    <td style="vertical-align:middle;padding-left:18px;font-size:13px;color:#333;line-height:1.9;">
      <div>&#128222;&nbsp;+92 370 7348001</div>
      <div>&#128231;&nbsp;admin@nexariza.com</div>
      <div>&#127760;&nbsp;<a href="https://www.nexariza.com" style="color:#1a73e8;text-decoration:none;font-weight:600;">www.nexariza.com</a></div>
      <div>&#128205;&nbsp;Lahore, Punjab, Pakistan.</div>
    </td>
  </tr>
</table>
<p style="margin-top:16px;font-size:11px;color:#888;border-top:1px solid #e0e0e0;padding-top:10px;">
  This email and any attachments are confidential and intended solely for the recipient.
  If you are not the intended recipient, please notify the sender and delete this message.
</p>
"""

# Sign-off patterns the AI might generate — stripped before appending hardcoded signature
_SIGNOFF_PATTERNS = (
    "best,", "best regards,", "kind regards,", "regards,", "sincerely,",
    "cheers,", "thanks,", "thank you,", "warm regards,",
    "hassan nadeem", "ahmad yasin", "nexariza ai", "nexariza",
    "+92", "admin@nexariza", "www.nexariza", "contact@nexariza",
)


def _strip_ai_signoff(plain_body: str) -> str:
    """Remove any trailing sign-off lines the AI generated so we can append our own."""
    lines = plain_body.splitlines()
    while lines:
        last = lines[-1].strip().lower()
        if not last or any(last.startswith(p) for p in _SIGNOFF_PATTERNS):
            lines.pop()
        else:
            break
    return "\n".join(lines).strip()


def build_html_email(plain_body: str) -> str:
    """
    Wraps a plain-text email body in clean, minimal HTML and appends the
    official Nexariza branded HTML signature (Ahmad Yasin, logo, contact info).
    """
    # Strip any AI-generated sign-off so only the HTML signature appears at the bottom
    clean_body = _strip_ai_signoff(plain_body)
    if not clean_body.rstrip().lower().endswith(("best,", "best", "regards,", "regards", "cheers,", "cheers")):
        clean_body = clean_body.rstrip() + "\n\nBest,"

    html_body = clean_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = "".join(
        f"<p style='margin:0 0 16px 0;font-size:15px;color:#111827;line-height:1.6;'>{line}</p>" if line.strip() else "<br>"
        for line in html_body.splitlines()
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
</head>
<body style="margin:0;padding:20px;font-family:Arial, Helvetica, sans-serif;font-size:15px;color:#111827;background-color:#ffffff;line-height:1.6;">
  <div style="max-width:620px;margin:0;">
    {paragraphs}
    {_NEXARIZA_HTML_SIGNATURE}
  </div>
</body>
</html>"""


# ── SMTP Config ───────────────────────────────────────────────────────────────

def get_smtp_config() -> dict:
    """Load Primary SMTP config (contact@nexariza.com) from environment variables."""
    return {
        "server":   os.getenv("SMTP_SERVER", "smtp.zoho.com"),
        "port":     int(os.getenv("SMTP_PORT", "465")),
        "email":    os.getenv("SENDER_EMAIL", ""),
        "password": os.getenv("SENDER_PASSWORD", ""),
    }


def get_sales_smtp_config() -> dict:
    """Load Sales SMTP config (sales@nexariza.com) from environment variables."""
    return {
        "server":   os.getenv("SALES_SMTP_SERVER", "smtp.zoho.com"),
        "port":     int(os.getenv("SALES_SMTP_PORT", "465")),
        "email":    os.getenv("SALES_SENDER_EMAIL", "sales@nexariza.com"),
        "password": os.getenv("SALES_SENDER_PASSWORD", ""),
    }


# ── Email Sender ──────────────────────────────────────────────────────────────

def analyze_email(email: str) -> dict:
    """
    Analyzes an email address for validity:
    1. Syntax Check
    2. MX Record (Deliverability) Check
    3. Disposable Domain Check
    4. Role-based Check
    Returns a dictionary with status and reason.
    """
    if not email or not isinstance(email, str):
        return {"is_valid": False, "reason": "Empty or invalid format"}
    
    email = email.strip().lower()
    
    try:
        # Check syntax (MX checked asynchronously elsewhere)
        valid = validate_email(email, check_deliverability=False)
        domain = valid.domain
        local_part = valid.local_part
    except EmailNotValidError as e:
        return {"is_valid": False, "reason": str(e)}
        
    # Check for disposable domains
    if domain in DISPOSABLE_DOMAINS:
        return {"is_valid": False, "reason": "Disposable email domain"}
        
    # Check for role-based emails
    if local_part in ROLE_BASED_PREFIXES:
        return {"is_valid": False, "reason": "Role-based generic email"}
        
    return {"is_valid": True, "reason": "Valid"}

_mx_cache = TTLCache(maxsize=1000, ttl=3600)
_a_cache = TTLCache(maxsize=1000, ttl=3600)

async def validate_email_domain(email: str) -> bool:
    """
    Validates if the email domain has valid MX records.
    Returns False if it has no MX records or a Null MX record.
    """
    domain = email.split('@')[-1].lower()
    
    if domain in _mx_cache:
        records = _mx_cache[domain]
        if not records:
            return False
        return records[0] != "" # False if Null MX

    for attempt in range(3):
        try:
            answers = await dns.asyncresolver.resolve(domain, 'MX')
            records = sorted(answers, key=lambda r: r.preference)
            exchanges = [str(r.exchange).rstrip('.') for r in records]
            _mx_cache[domain] = exchanges
            
            for exchange in exchanges:
                if exchange == '': # Null MX
                    return False
            return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            _mx_cache[domain] = []
            return False
        except dns.exception.Timeout:
            if attempt == 2:
                return False
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"DNS lookup failed for {email}: {e}")
            return True
    return False

async def send_email(
    recipient: str,
    subject: str,
    body: str,
    sender_name: str = "Hassan Nadeem | Nexariza AI",
    is_html: bool = False,
    smtp_config: Optional[dict] = None,
    is_important: bool = False,
    attachments: Optional[list] = None,
) -> bool:
    """
    Send a single email via SSL SMTP with full deliverability optimization.
    If is_html=True, body is sent as-is (already HTML).
    If is_html=False (plain text), body is automatically wrapped in the
    branded Nexariza HTML template with logo before sending.
    If is_important=True, flags the message as High Priority/Urgent across
    all major mail clients (Outlook, Apple Mail, Gmail, Thunderbird).
    attachments: List of dicts with keys: 'filename', 'content' (bytes or str),
                 optional 'maintype' (default: 'text'), optional 'subtype' (default: 'html').
    NOTE: is_important should NOT be used for cold emails (it's a spam signal).
    Returns True on success, False on failure.
    """
    # ── Pre-send Email Address Validation ────────────────────────────────────
    # Fast, synchronous check: syntax + disposable domain + role-based prefix.
    # This is a final safety net — raises ValueError before any SMTP connection
    # is attempted, regardless of whether the caller validated upstream.
    address_check = analyze_email(recipient)
    if not address_check["is_valid"]:
        reason = address_check.get("reason", "Invalid address")
        logger.warning(
            f"[send_email] Blocked send to '{recipient}': {reason}"
        )
        raise ValueError(
            f"Cannot send to '{recipient}': {reason}"
        )

    config = smtp_config or get_smtp_config()
    sender_email = config["email"]

    if not sender_email:
        raise ValueError("SENDER_EMAIL is not configured in .env")

    # Plain text fallback matches exact body (no artificial marketing footers)
    plain_fallback = body

    # Always upgrade plain text to minimal clean HTML
    if not is_html:
        html_content = build_html_email(body)
    else:
        html_content = body

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient

    if is_important:
        msg["Importance"] = "High"
        msg["X-Priority"] = "1"
        msg["Priority"] = "urgent"
        msg["X-MSMail-Priority"] = "High"

    # Set plain-text fallback, then attach HTML as preferred alternative
    msg.set_content(plain_fallback)
    msg.add_alternative(html_content, subtype="html")

    # Add attachments if provided
    if attachments:
        for att in attachments:
            fname = att.get("filename", "attachment.html")
            raw_data = att.get("content", "")
            if isinstance(raw_data, str):
                raw_bytes = raw_data.encode("utf-8")
            else:
                raw_bytes = raw_data
            mtype = att.get("maintype", "text")
            stype = att.get("subtype", "html")
            msg.add_attachment(raw_bytes, maintype=mtype, subtype=stype, filename=fname)

    # ── Deliverability Agent: Apply smart headers ─────────────────────────
    # Adds proper Message-ID, Date, Reply-To, MIME-Version headers and
    # removes spam-signal headers (X-Mailer, Precedence, priority headers
    # on cold emails) to maximize inbox placement.
    try:
        from services.deliverability_agent import apply_deliverability_headers
        sender_domain = sender_email.split("@")[-1] if "@" in sender_email else "nexariza.com"
        apply_deliverability_headers(msg, sender_domain=sender_domain)
    except Exception as e:
        logger.warning(f"Deliverability header injection skipped: {e}")

    context = ssl.create_default_context()

    try:
        await aiosmtplib.send(
            msg,
            hostname=config["server"],
            port=config["port"],
            username=sender_email,
            password=config["password"],
            use_tls=True,
            tls_context=context
        )
        logger.info(f"Email sent successfully to {recipient}")

        # ── Deliverability Agent: Track send for warmup + content fingerprint
        try:
            from services.deliverability_agent import record_send, register_sent_content
            record_send()
            register_sent_content(subject, body)
        except Exception as e:
            logger.warning(f"Deliverability tracking skipped: {e}")

        return True

    except aiosmtplib.SMTPAuthenticationError:
        logger.error("SMTP Authentication failed. Check SENDER_EMAIL and SENDER_PASSWORD in .env")
        raise
    except aiosmtplib.SMTPRecipientRefused:
        logger.warning(f"Recipient refused: {recipient}")
        return False
    except Exception as e:
        logger.error(f"Failed to send to {recipient}: {e}")
        raise


# ── SMTP Health Check ─────────────────────────────────────────────────────────

# Cache SMTP health result for 60s to avoid hammering the SMTP server
_smtp_health_cache: dict = {}
_smtp_health_cache_time: float = 0.0
_SMTP_CACHE_TTL = 60.0  # seconds

async def test_smtp_connection() -> dict:
    """Test SMTP connection and return status dict (cached for 60s)."""
    global _smtp_health_cache, _smtp_health_cache_time
    import time as _time
    now = _time.monotonic()
    if _smtp_health_cache and (now - _smtp_health_cache_time) < _SMTP_CACHE_TTL:
        logger.debug("SMTP health: returning cached result")
        return _smtp_health_cache

    config = get_smtp_config()
    context = ssl.create_default_context()
    try:
        smtp = aiosmtplib.SMTP(
            hostname=config["server"], 
            port=config["port"], 
            use_tls=True, 
            tls_context=context
        )
        await smtp.connect()
        await smtp.login(config["email"], config["password"])
        await smtp.quit()
        result = {
            "status": "ok",
            "message": f"Successfully connected and authenticated as {config['email']}"
        }
    except aiosmtplib.SMTPAuthenticationError:
        result = {"status": "error", "message": "Authentication failed. Check credentials in .env"}
    except Exception as e:
        result = {"status": "error", "message": str(e)}

    _smtp_health_cache = result
    _smtp_health_cache_time = now
    return result


# ── Deep Email Verification Engine ────────────────────────────────────────────

async def read_smtp_response(reader) -> tuple[int, str]:
    """Helper to read SMTP response and handle multi-line replies."""
    lines = []
    code = 0
    while True:
        line_bytes = await reader.readline()
        if not line_bytes:
            break
        line = line_bytes.decode('utf-8', errors='ignore').strip()
        lines.append(line)
        if len(line) >= 3:
            try:
                code = int(line[:3])
            except ValueError:
                pass
            if len(line) == 3 or line[3] != '-':
                break
        else:
            break
    return code, "\n".join(lines)


async def _smtp_handshake_port25(
    mx_host: str, email: str, sender_email: str, timeout: float
) -> dict:
    """
    Raw TCP port-25 SMTP handshake (EHLO/HELO → MAIL FROM → RCPT TO).
    Most accurate method — no authentication required — but often blocked
    by cloud providers and consumer ISPs.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mx_host, 25),
            timeout=timeout
        )
    except (asyncio.TimeoutError, ConnectionRefusedError, socket.gaierror, OSError) as e:
        return {"status": "error", "message": f"Port 25 blocked: {str(e)}", "connectable": False, "port": 25}

    try:
        # Read server welcome banner
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 220:
            return {"status": "error", "message": f"Unexpected banner code {code}: {msg}", "connectable": True, "port": 25}

        # Send EHLO
        writer.write(b"EHLO nexariza.com\r\n")
        await writer.drain()
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 250:
            # Fallback to HELO
            writer.write(b"HELO nexariza.com\r\n")
            await writer.drain()
            code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
            if code != 250:
                return {"status": "error", "message": f"EHLO/HELO rejected {code}: {msg}", "connectable": True, "port": 25}

        # Send MAIL FROM
        writer.write(f"MAIL FROM:<{sender_email}>\r\n".encode())
        await writer.drain()
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 250:
            return {"status": "error", "message": f"MAIL FROM rejected {code}: {msg}", "connectable": True, "port": 25}

        # Send RCPT TO
        writer.write(f"RCPT TO:<{email}>\r\n".encode())
        await writer.drain()
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)

        mailbox_exists: Optional[bool] = None
        response_code = code
        if code == 250 or code == 251:
            mailbox_exists = True
        elif 500 <= code < 600:
            mailbox_exists = False
        # 4xx temporary codes → mailbox_exists stays None (unknown)

        # Catch-all detection: send a random address in the same session
        is_catch_all = False
        if mailbox_exists is True:
            domain = email.split('@')[-1]
            random_email = f"nexariza_verify_random_{int(time.time())}@{domain}"
            writer.write(f"RCPT TO:<{random_email}>\r\n".encode())
            await writer.drain()
            code_fake, _ = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
            if code_fake == 250 or code_fake == 251:
                is_catch_all = True

        # Polite close
        writer.write(b"QUIT\r\n")
        await writer.drain()

        return {
            "status": "success",
            "connectable": True,
            "port": 25,
            "mailbox_exists": mailbox_exists,
            "is_catch_all": is_catch_all,
            "response_code": response_code,
            "response_message": msg,
        }
    except Exception as e:
        return {"status": "error", "message": f"Port 25 handshake error: {str(e)}", "connectable": True, "port": 25}
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _smtp_handshake_port587(
    mx_host: str, email: str, sender_email: str, timeout: float
) -> dict:
    """
    STARTTLS port-587 SMTP handshake — fallback when port 25 is blocked.

    Uses aiosmtplib to negotiate STARTTLS and then issues EHLO → MAIL FROM
    → RCPT TO without completing authentication (we only need the RCPT TO
    accept/reject decision, not a full authenticated session).

    Reliability: slightly lower than port 25 because servers may require AUTH
    before accepting RCPT TO on port 587, but many will still tell us whether
    the mailbox exists before that point.
    """
    import ssl as _ssl
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mx_host, 587),
            timeout=timeout
        )
    except (asyncio.TimeoutError, ConnectionRefusedError, socket.gaierror, OSError) as e:
        return {"status": "error", "message": f"Port 587 blocked: {str(e)}", "connectable": False, "port": 587}

    try:
        # Read banner
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 220:
            return {"status": "error", "message": f"Port 587 banner error {code}: {msg}", "connectable": True, "port": 587}

        # EHLO
        writer.write(b"EHLO nexariza.com\r\n")
        await writer.drain()
        code, ehlo_msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 250:
            return {"status": "error", "message": f"Port 587 EHLO failed {code}: {ehlo_msg}", "connectable": True, "port": 587}

        # STARTTLS upgrade (only if server advertises it)
        if "STARTTLS" in ehlo_msg.upper():
            writer.write(b"STARTTLS\r\n")
            await writer.drain()
            code, tls_msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
            if code == 220:
                # Upgrade the connection to TLS
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                transport = writer.transport
                loop = asyncio.get_event_loop()
                tls_transport = await loop.start_tls(
                    transport, None, ctx, server_side=False, server_hostname=mx_host
                )
                # Rebuild reader/writer on the TLS transport
                protocol = transport.get_protocol()
                tls_transport.set_protocol(protocol)
                writer = asyncio.StreamWriter(tls_transport, protocol, reader, loop)
                # Re-EHLO after TLS upgrade
                writer.write(b"EHLO nexariza.com\r\n")
                await writer.drain()
                code, _ = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)

        # MAIL FROM (unauthenticated — some servers allow it, some require AUTH first)
        writer.write(f"MAIL FROM:<{sender_email}>\r\n".encode())
        await writer.drain()
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 250:
            # Server requires AUTH before MAIL FROM — we can't go further,
            # but the connection itself proved the MX is reachable.
            writer.write(b"QUIT\r\n")
            await writer.drain()
            return {
                "status": "error",
                "message": f"Port 587 requires AUTH before MAIL FROM ({code}) — SMTP reachable but mailbox check inconclusive",
                "connectable": True,
                "port": 587,
            }

        # RCPT TO
        writer.write(f"RCPT TO:<{email}>\r\n".encode())
        await writer.drain()
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)

        mailbox_exists: Optional[bool] = None
        response_code = code
        if code == 250 or code == 251:
            mailbox_exists = True
        elif 500 <= code < 600:
            mailbox_exists = False

        # Catch-all detection
        is_catch_all = False
        if mailbox_exists is True:
            domain = email.split('@')[-1]
            random_email = f"nexariza_verify_rnd_{int(time.time())}@{domain}"
            writer.write(f"RCPT TO:<{random_email}>\r\n".encode())
            await writer.drain()
            code_fake, _ = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
            if code_fake == 250 or code_fake == 251:
                is_catch_all = True

        writer.write(b"QUIT\r\n")
        await writer.drain()

        return {
            "status": "success",
            "connectable": True,
            "port": 587,
            "mailbox_exists": mailbox_exists,
            "is_catch_all": is_catch_all,
            "response_code": response_code,
            "response_message": msg,
        }
    except Exception as e:
        return {"status": "error", "message": f"Port 587 handshake error: {str(e)}", "connectable": True, "port": 587}
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def check_mx_smtp(
    mx_host: str,
    email: str,
    sender_email: str,
    timeout: float = 5.0,
) -> dict:
    """
    SMTP mailbox ping with automatic port fallback (medium reliability).

    Strategy:
      1. Try port 25 (raw TCP, no auth) — highest accuracy, often blocked on
         cloud/ISP networks.
      2. If port 25 is not connectable, fall back to port 587 (STARTTLS) —
         slightly lower accuracy because some servers demand AUTH before RCPT TO,
         but confirms reachability and often still reveals invalid mailboxes.

    The result dict always includes a ``port`` key (25 or 587) indicating
    which port produced the definitive answer.
    """
    # ── Attempt 1: port 25 ───────────────────────────────────────────────────
    result25 = await _smtp_handshake_port25(mx_host, email, sender_email, timeout)
    if result25["connectable"]:
        # Port 25 was reachable — trust its verdict regardless of success/error
        return result25

    # ── Attempt 2: port 587 (STARTTLS fallback) ──────────────────────────────
    logger.debug(
        f"[SMTP] Port 25 blocked for {mx_host} — retrying on port 587 (STARTTLS)"
    )
    result587 = await _smtp_handshake_port587(mx_host, email, sender_email, timeout)
    return result587

async def get_mx_records(domain: str) -> list[str]:
    """Resolves domain MX records, sorted by priority."""
    domain = domain.lower()
    if domain in _mx_cache:
        return _mx_cache[domain]
        
    for attempt in range(3):
        try:
            answers = await dns.asyncresolver.resolve(domain, 'MX')
            records = sorted(answers, key=lambda r: r.preference)
            exchanges = [str(r.exchange).rstrip('.') for r in records]
            _mx_cache[domain] = exchanges
            return exchanges
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            _mx_cache[domain] = []
            return []
        except dns.exception.Timeout:
            if attempt == 2:
                return []
            await asyncio.sleep(1)
        except Exception:
            return []
    return []

async def get_a_records(domain: str) -> list[str]:
    """Resolves A records for a domain (fallback for mail server)."""
    domain = domain.lower()
    if domain in _a_cache:
        return _a_cache[domain]
        
    for attempt in range(3):
        try:
            answers = await dns.asyncresolver.resolve(domain, 'A')
            addresses = [str(r.address) for r in answers]
            _a_cache[domain] = addresses
            return addresses
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            _a_cache[domain] = []
            return []
        except dns.exception.Timeout:
            if attempt == 2:
                return []
            await asyncio.sleep(1)
        except Exception:
            return []
    return []

async def verify_email_deep(email: str, sender_email: Optional[str] = None) -> dict:
    """
    Performs multi-stage deep email verification:
    1. Syntax Check (email_validator)
    2. Disposable domain check
    3. Role-based email prefix check
    4. DNS MX record check (and A record fallback)
    5. SMTP port 25 handshake ping & catch-all test
    """
    if not email or not isinstance(email, str):
        return {
            "email": email,
            "is_valid": False,
            "status": "undeliverable",
            "reason": "Empty or invalid format",
            "syntax_valid": False,
            "dns_valid": False,
            "mx_records": [],
            "smtp_checked": False,
            "mailbox_exists": False,
            "is_catch_all": False,
            "is_disposable": False,
            "is_role_based": False,
            "is_free": False
        }
        
    email = email.strip()
    
    # 1. Syntax Check
    try:
        valid = validate_email(email, check_deliverability=False)
        domain = valid.domain.lower()
        local_part = valid.local_part.lower()
        syntax_valid = True
    except EmailNotValidError as e:
        return {
            "email": email,
            "is_valid": False,
            "status": "undeliverable",
            "reason": f"Syntax error: {str(e)}",
            "syntax_valid": False,
            "dns_valid": False,
            "mx_records": [],
            "smtp_checked": False,
            "mailbox_exists": False,
            "is_catch_all": False,
            "is_disposable": False,
            "is_role_based": False,
            "is_free": False
        }
        
    # Check flags
    is_disposable = domain in DISPOSABLE_DOMAINS
    is_role_based = local_part in ROLE_BASED_PREFIXES
    
    FREE_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com"}
    is_free = domain in FREE_DOMAINS
    
    # 2. DNS Check
    mx_records = await get_mx_records(domain)
    dns_valid = len(mx_records) > 0
    
    mail_servers = list(mx_records)
    if not mail_servers:
        # A record fallback
        a_records = await get_a_records(domain)
        if a_records:
            mail_servers = [domain]
            dns_valid = True
            
    if not dns_valid:
        return {
            "email": email,
            "is_valid": False,
            "status": "undeliverable",
            "reason": "No MX or A records found for domain",
            "syntax_valid": True,
            "dns_valid": False,
            "mx_records": [],
            "smtp_checked": False,
            "mailbox_exists": False,
            "is_catch_all": False,
            "is_disposable": is_disposable,
            "is_role_based": is_role_based,
            "is_free": is_free
        }
        
    # Null MX
    if len(mx_records) == 1 and mx_records[0] == "":
        return {
            "email": email,
            "is_valid": False,
            "status": "undeliverable",
            "reason": "Null MX record (domain explicitly does not accept mail)",
            "syntax_valid": True,
            "dns_valid": False,
            "mx_records": [],
            "smtp_checked": False,
            "mailbox_exists": False,
            "is_catch_all": False,
            "is_disposable": is_disposable,
            "is_role_based": is_role_based,
            "is_free": is_free
        }

    # 3. SMTP Handshake Check (port 25 with port 587 STARTTLS fallback)
    if not sender_email:
        sender_email = get_smtp_config().get("email") or "verify@nexariza.com"

    smtp_checked = False
    mailbox_exists = None
    is_catch_all = False
    smtp_error = None
    smtp_port_used: Optional[int] = None
    smtp_method = "none"  # "port25" | "port587_starttls" | "none"

    smtp_result = None
    for mx_host in mail_servers:
        if not mx_host:
            continue
        smtp_result = await check_mx_smtp(mx_host, email, sender_email)
        if smtp_result["connectable"]:
            smtp_checked = True
            smtp_port_used = smtp_result.get("port")
            smtp_method = "port25" if smtp_port_used == 25 else "port587_starttls"
            if smtp_result["status"] == "success":
                mailbox_exists = smtp_result["mailbox_exists"]
                is_catch_all = smtp_result["is_catch_all"]
            else:
                smtp_error = smtp_result["message"]
            break
        else:
            # Neither port was connectable — accumulate error and try next MX
            smtp_error = smtp_result["message"]

    # Calculate overall deliverability status
    status = "unknown"
    reason = "DNS valid, but SMTP connection failed"
    is_valid = True

    if smtp_checked:
        if mailbox_exists is True:
            if is_catch_all:
                status = "catch_all"
                reason = (
                    f"Catch-all domain — accepts all addresses (verified via "
                    f"{'port 25' if smtp_port_used == 25 else 'port 587 STARTTLS'})"
                )
                is_valid = True
            else:
                status = "deliverable"
                reason = (
                    f"Mailbox confirmed deliverable (verified via "
                    f"{'port 25' if smtp_port_used == 25 else 'port 587 STARTTLS'})"
                )
                is_valid = True
        elif mailbox_exists is False:
            status = "undeliverable"
            reason = (
                f"Mailbox rejected by recipient server "
                f"(code {smtp_result.get('response_code', '5xx')} via "
                f"{'port 25' if smtp_port_used == 25 else 'port 587 STARTTLS'}): "
                f"{smtp_result.get('response_message', 'no mailbox found')}"
            )
            is_valid = False
        else:
            # 4xx temporary / AUTH-required — treat as unknown (safe fallback)
            status = "unknown"
            reason = (
                f"Inconclusive SMTP response via port {smtp_port_used}: "
                f"{smtp_result.get('response_message') or smtp_error or 'temporary error'}"
            )
            is_valid = True
    else:
        status = "unknown"
        reason = (
            f"SMTP ping skipped — both port 25 and port 587 unreachable: "
            f"{smtp_error or 'connection refused'}"
        )
        is_valid = True  # Graceful fallback — DNS was valid
        
    # Enforce disposable blocking
    if is_valid and is_disposable:
        status = "undeliverable"
        reason = "Blocked: Disposable email domain"
        is_valid = False

    return {
        "email": email,
        "is_valid": is_valid,
        "status": status,
        "reason": reason,
        "syntax_valid": syntax_valid,
        "dns_valid": dns_valid,
        "mx_records": mail_servers,
        "smtp_checked": smtp_checked,
        "mailbox_exists": mailbox_exists if mailbox_exists is not None else False,
        "is_catch_all": is_catch_all,
        "is_disposable": is_disposable,
        "is_role_based": is_role_based,
        "is_free": is_free,
        # ── SMTP ping metadata (medium-reliability check) ────────────────
        "smtp_port_used": smtp_port_used,        # 25 | 587 | None
        "smtp_method": smtp_method,              # "port25" | "port587_starttls" | "none"
    }
