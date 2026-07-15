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
NEXARIZA_LINKEDIN   = "https://www.linkedin.com/company/nexariza/"
NEXARIZA_EMAIL      = "contact@nexariza.com"
NEXARIZA_PHONE      = "+92-370-7348001"


# ── HTML Email Builder ────────────────────────────────────────────────────────

def build_html_email(plain_body: str) -> str:
    """
    Wraps a plain-text email body in a fully branded Nexariza HTML email.
    - Converts newlines to <br> for HTML rendering
    - Appends a professional signature with the Nexariza logo
    Returns the complete HTML string.
    """
    # Convert plain text body to HTML paragraphs
    html_body = plain_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = "".join(
        f"<p>{line}</p>" if line.strip() else "<br>"
        for line in html_body.splitlines()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nexariza AI</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f6f9;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="620" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:12px;
                      box-shadow:0 4px 24px rgba(0,0,0,0.08);
                      overflow:hidden;max-width:620px;">

          <!-- ── Header bar ── -->
          <tr>
            <td style="background:linear-gradient(135deg,#0a1628 0%,#0d2b5e 100%);
                        padding:28px 40px;text-align:center;">
              <a href="{NEXARIZA_WEBSITE}" target="_blank" style="text-decoration:none;">
                <img src="{NEXARIZA_LOGO_URL}"
                     alt="Nexariza AI"
                     width="72" height="72"
                     style="border-radius:50%;border:2px solid rgba(255,255,255,0.15);
                            display:block;margin:0 auto 10px auto;" />
                <span style="color:#ffffff;font-size:22px;font-weight:700;
                              letter-spacing:1px;display:block;">NEXARIZA AI</span>
                <span style="color:#5b9bd5;font-size:12px;
                              letter-spacing:2px;text-transform:uppercase;">
                  Intelligent Automation &bull; Limitless Growth
                </span>
              </a>
            </td>
          </tr>

          <!-- ── Email body ── -->
          <tr>
            <td style="padding:36px 40px 24px 40px;color:#1a1a2e;font-size:15px;
                        line-height:1.75;border-bottom:1px solid #eef0f4;">
              {paragraphs}
            </td>
          </tr>

          <!-- ── Signature ── -->
          <tr>
            <td style="padding:24px 40px 20px 40px;">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <!-- Logo thumbnail -->
                  <td style="padding-right:16px;vertical-align:middle;">
                    <img src="{NEXARIZA_LOGO_URL}"
                         alt="Nexariza"
                         width="52" height="52"
                         style="border-radius:50%;display:block;" />
                  </td>
                  <!-- Name & title -->
                  <td style="vertical-align:middle;border-left:3px solid #1a6ed8;padding-left:14px;">
                    <p style="margin:0;font-size:15px;font-weight:700;color:#0d2b5e;">
                      Hassan Nadeem
                    </p>
                    <p style="margin:2px 0 6px 0;font-size:12px;color:#5b9bd5;
                               text-transform:uppercase;letter-spacing:0.8px;">
                      AI Solutions Specialist &bull; Nexariza AI
                    </p>
                    <p style="margin:0;font-size:12px;color:#555;">
                      <a href="mailto:{NEXARIZA_EMAIL}"
                         style="color:#1a6ed8;text-decoration:none;">{NEXARIZA_EMAIL}</a>
                      &nbsp;|&nbsp;
                      <a href="tel:{NEXARIZA_PHONE}"
                         style="color:#555;text-decoration:none;">{NEXARIZA_PHONE}</a>
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── CTA buttons ── -->
          <tr>
            <td style="padding:0 40px 28px 40px;">
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding-right:10px;">
                    <a href="{NEXARIZA_WEBSITE}" target="_blank"
                       style="display:inline-block;background:linear-gradient(135deg,#1a6ed8,#0d2b5e);
                              color:#ffffff;font-size:12px;font-weight:600;
                              padding:9px 20px;border-radius:6px;text-decoration:none;
                              letter-spacing:0.5px;">
                      Visit Website
                    </a>
                  </td>
                  <td>
                    <a href="{NEXARIZA_LINKEDIN}" target="_blank"
                       style="display:inline-block;background:#0077b5;
                              color:#ffffff;font-size:12px;font-weight:600;
                              padding:9px 20px;border-radius:6px;text-decoration:none;
                              letter-spacing:0.5px;">
                      LinkedIn
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── Footer ── -->
          <tr>
            <td style="background:#f8f9fc;padding:14px 40px;
                        border-top:1px solid #eef0f4;text-align:center;">
              <p style="margin:0;font-size:11px;color:#aaa;line-height:1.5;">
                &copy; 2024 Nexariza AI &bull; Lahore, Pakistan &bull;
                <a href="{NEXARIZA_WEBSITE}" style="color:#1a6ed8;text-decoration:none;">
                  nexariza.com
                </a>
                <br>
                You are receiving this email because you match our ideal client profile.
                To unsubscribe, reply with "Unsubscribe".
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ── SMTP Config ───────────────────────────────────────────────────────────────

def get_smtp_config() -> dict:
    """Load SMTP config from environment variables."""
    return {
        "server":   os.getenv("SMTP_SERVER", "smtp.zoho.com"),
        "port":     int(os.getenv("SMTP_PORT", "465")),
        "email":    os.getenv("SENDER_EMAIL", ""),
        "password": os.getenv("SENDER_PASSWORD", ""),
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
) -> bool:
    """
    Send a single email via SSL SMTP.
    If is_html=True, body is sent as-is (already HTML).
    If is_html=False (plain text), body is automatically wrapped in the
    branded Nexariza HTML template with logo before sending.
    Returns True on success, False on failure.
    """
    config = smtp_config or get_smtp_config()
    sender_email = config["email"]

    if not sender_email:
        raise ValueError("SENDER_EMAIL is not configured in .env")

    # Always upgrade plain text to branded HTML
    if not is_html:
        html_content = build_html_email(body)
        plain_fallback = body
    else:
        html_content = body
        plain_fallback = "Please enable HTML to view this email."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient

    # Set plain-text fallback, then attach HTML as preferred alternative
    msg.set_content(plain_fallback)
    msg.add_alternative(html_content, subtype="html")

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

async def test_smtp_connection() -> dict:
    """Test SMTP connection and return status dict."""
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
        return {
            "status": "ok",
            "message": f"Successfully connected and authenticated as {config['email']}"
        }
    except aiosmtplib.SMTPAuthenticationError:
        return {"status": "error", "message": "Authentication failed. Check credentials in .env"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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

async def check_mx_smtp(mx_host: str, email: str, sender_email: str, timeout: float = 5.0) -> dict:
    """Connects to a single MX server on port 25 and checks if mailbox exists."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mx_host, 25),
            timeout=timeout
        )
    except (asyncio.TimeoutError, ConnectionRefusedError, socket.gaierror, OSError) as e:
        return {"status": "error", "message": f"Connection failed: {str(e)}", "connectable": False}

    try:
        # Read server welcome banner
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 220:
            return {"status": "error", "message": f"Unexpected banner code {code}: {msg}", "connectable": True}
        
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
                return {"status": "error", "message": f"HELO failed {code}: {msg}", "connectable": True}
        
        # Send MAIL FROM
        writer.write(f"MAIL FROM:<{sender_email}>\r\n".encode())
        await writer.drain()
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        if code != 250:
            return {"status": "error", "message": f"MAIL FROM failed {code}: {msg}", "connectable": True}
        
        # Send RCPT TO
        writer.write(f"RCPT TO:<{email}>\r\n".encode())
        await writer.drain()
        code, msg = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
        
        mailbox_exists = False
        response_code = code
        
        if code == 250 or code == 251:
            mailbox_exists = True
        elif code >= 500 and code < 600:
            mailbox_exists = False
        else:
            # 4xx or other temporary codes
            mailbox_exists = None
            
        # Catch-all check: if recipient accepted, try a randomly generated address in the same session
        is_catch_all = False
        if mailbox_exists is True:
            domain = email.split('@')[-1]
            random_email = f"nexariza_verify_random_{int(time.time())}@{domain}"
            writer.write(f"RCPT TO:<{random_email}>\r\n".encode())
            await writer.drain()
            code_fake, _ = await asyncio.wait_for(read_smtp_response(reader), timeout=timeout)
            if code_fake == 250 or code_fake == 251:
                is_catch_all = True
                
        # Send QUIT
        writer.write(b"QUIT\r\n")
        await writer.drain()
        
        return {
            "status": "success",
            "connectable": True,
            "mailbox_exists": mailbox_exists,
            "is_catch_all": is_catch_all,
            "response_code": response_code,
            "response_message": msg
        }
    except Exception as e:
        return {"status": "error", "message": f"SMTP handshake failed: {str(e)}", "connectable": True}
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

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

    # 3. SMTP Handshake Check
    if not sender_email:
        sender_email = get_smtp_config().get("email") or "verify@nexariza.com"
        
    smtp_checked = False
    mailbox_exists = None
    is_catch_all = False
    smtp_error = None
    
    smtp_result = None
    for mx_host in mail_servers:
        if not mx_host:
            continue
        smtp_result = await check_mx_smtp(mx_host, email, sender_email)
        if smtp_result["connectable"]:
            smtp_checked = True
            if smtp_result["status"] == "success":
                mailbox_exists = smtp_result["mailbox_exists"]
                is_catch_all = smtp_result["is_catch_all"]
            else:
                smtp_error = smtp_result["message"]
            break
        else:
            smtp_error = smtp_result["message"]
            
    # Calculate overall deliverability status
    status = "unknown"
    reason = "DNS valid, but SMTP connection failed"
    is_valid = True
    
    if smtp_checked:
        if mailbox_exists is True:
            if is_catch_all:
                status = "catch_all"
                reason = "Catch-all domain (accepts all email addresses)"
                is_valid = True
            else:
                status = "deliverable"
                reason = "Mailbox exists and is deliverable"
                is_valid = True
        elif mailbox_exists is False:
            status = "undeliverable"
            reason = f"Recipient server rejected mailbox: {smtp_result.get('response_message', 'No mailbox found')}"
            is_valid = False
        else:
            status = "unknown"
            reason = f"Inconclusive SMTP response: {smtp_result.get('response_message', 'Error')}"
            is_valid = True
    else:
        status = "unknown"
        reason = f"SMTP check skipped (Port 25 blocked?): {smtp_error or 'Connection failed'}"
        is_valid = True # Graceful fallback
        
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
        "is_free": is_free
    }
