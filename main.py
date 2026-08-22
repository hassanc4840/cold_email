"""
main.py
-------
Nexariza AI-Powered Outreach System
FastAPI backend with Gemini AI for personalized cold email campaigns.

Run with:
    uvicorn main:app --reload

Interactive docs:
    http://127.0.0.1:8000/docs
"""

import os
import csv
import asyncio
import logging
import time
from typing import Optional, List

import io
import shutil
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

from models.schemas import (
    CampaignMode,
    CampaignRequest,
    CampaignResponse,
    ClientResult,
    SingleClientRequest,
    AnalyzeClientResponse,
    ClientInput,
    BatchCampaignRequest,
    EmailVerificationRequest,
    EmailVerificationResponse,
    CampaignStatusResponse,
    SpamCheckRequest,
    SpamCheckResponse,
    InternInput,
    InternshipConfigRequest,
    InternshipSingleRequest,
    InternshipBatchRequest,
    InternshipResult,
)
from services.scraper_service import get_client_web_context
from services.gemini_service import generate_outreach_email, cleanse_and_validate_email
from services.email_service import (
    send_email,
    test_smtp_connection,
    get_smtp_config,
    validate_email_domain,
    analyze_email,
    verify_email_deep,
)

# ── Bootstrap ────────────────────────────────────────────────────────────────
import pathlib
load_dotenv(pathlib.Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nexariza AI Outreach API",
    description=(
        "Automated cold email campaigns powered by Gemini AI. "
        "Scrapes client websites, generates personalized pitches, and sends via SMTP."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server start time for uptime tracking
_server_start_time = time.time()

# In-memory store for last campaign stats
_last_campaign: Optional[CampaignResponse] = None

# Global campaign execution state
_campaign_state = {
    "status": "idle",  # "idle" | "running" | "completed" | "cancelled" | "failed"
    "mode": None,
    "total": 0,
    "processed": 0,
    "sent": 0,
    "failed": 0,
    "skipped": 0,
    "results": [],
    "current_lead": None
}
_cancel_campaign_flag = False


# ── Helper Functions ──────────────────────────────────────────────────────────

async def process_single_client(
    client: ClientInput,
    mode: CampaignMode,
    smtp_config: Optional[dict] = None,
) -> ClientResult:
    """
    Full pipeline for one client:
    1. Scrape website
    2. Generate hyper-personalized email with Groq (using all lead intel fields)
    3. Send (or simulate) via SMTP
    """
    name = client.name.strip()
    email = client.email.strip()
    website = client.website

    result = ClientResult(
        name=name,
        email=email,
        company_name=client.company_name,
        industry=client.industry,
        lead_score=client.lead_score,
        priority=client.priority,
        buying_intent=client.buying_intent,
        status="pending",
    )

    # ── Bounce Guard (hard-bounce blocklist) ─────────────────────────────────
    try:
        from services.history_service import is_bounced
        if is_bounced(email):
            result.status = "skipped"
            result.error = "Skipped: address previously hard-bounced (delivery failure)"
            logger.info(f"Skipping {email}: hard-bounce on record.")
            return result
    except Exception as e_hist:
        logger.warning(f"Bounce check failed for {email}, proceeding anyway: {e_hist}")

    # ── Duplicate / History Check ─────────────────────────────────────────────
    try:
        from services.history_service import is_known_prospect
        if is_known_prospect(email):
            result.status = "skipped"
            result.error = "Already contacted: found in sent history"
            logger.info(f"Skipping {email}: already contacted (duplicate check).")
            return result
    except Exception as e_hist:
        logger.warning(f"History check failed for {email}, proceeding anyway: {e_hist}")

    # ── Domain MX Validation ──────────────────────────────────────────────────
    is_valid_domain = await validate_email_domain(email)
    if not is_valid_domain:
        result.status = "skipped"
        result.error = "Invalid domain: Null MX or no MX records found"
        logger.warning(f"Skipping {email}: Invalid domain (Null MX or missing MX records).")
        return result

    # Step 1: Scrape web context + run flaw analysis
    try:
        web_ctx = await get_client_web_context(email, website)
        result.website_scraped = web_ctx.get("website_url")
    except Exception as e:
        logger.warning(f"Scraping failed for {email}: {e}")
        web_ctx = {
            "domain": email.split("@")[-1],
            "is_free_email": True,
            "website_url": None,
            "web_content": None,
            "html_raw": None,
            "flaw_report": None,
        }

    # Format flaw report for prompt injection (if available)
    flaw_report = web_ctx.get("flaw_report")
    website_flaws_str = None
    if flaw_report:
        from services.flaw_analyzer import format_flaws_for_prompt
        website_flaws_str = format_flaws_for_prompt(flaw_report)
        logger.info(
            f"[Campaign] Flaw data ready for {name}: "
            f"{len(flaw_report.flaws)} flaws | urgency={flaw_report.urgency_level}"
        )

    # Step 2: Generate hyper-personalized email via Groq (all CSV intel injected)
    try:
        subject, body = await generate_outreach_email(
            name=name,
            email=email,
            domain=web_ctx.get("domain", ""),
            is_free_email=web_ctx.get("is_free_email", True),
            web_content=web_ctx.get("web_content"),
            # ── Extended lead intelligence ──────────────────────────────────
            company_name=client.company_name,
            industry=client.industry,
            city=client.city,
            state=client.state,
            employees=client.employees,
            revenue=client.revenue,
            ceo=client.ceo,
            title=client.title,
            website_quality=client.website_quality,
            ai_readiness=client.ai_readiness,
            lead_score=client.lead_score,
            buying_intent=client.buying_intent,
            problem_statement=client.problem_statement,
            recommended_ai_solution=client.recommended_ai_solution,
            recommended_web_solution=client.recommended_web_solution,
            estimated_project_value=client.estimated_project_value,
            estimated_timeline=client.estimated_timeline,
            notes=client.notes,
            # ── AI-detected website flaws (personalization hook) ────────────
            website_flaws=website_flaws_str,
        )
        result.email_subject = subject
        result.email_body = body
    except Exception as e:
        result.status = "failed"
        result.error = f"Gemini generation failed: {str(e)}"
        logger.error(f"Groq failed for {name} ({email}): {e}")
        return result

    # Step 2.5: Deliverability pre-send gate (live mode only)
    if mode == CampaignMode.live:
        try:
            from services.deliverability_agent import pre_send_check
            gate = pre_send_check(subject, body)
            if not gate["can_send"]:
                result.status = "skipped"
                result.error = f"Blocked by deliverability agent: {'; '.join(gate['block_reasons'])}"
                logger.warning(f"[Deliverability] Blocked send to {email}: {gate['block_reasons']}")
                return result
            if gate["warnings"]:
                logger.info(f"[Deliverability] Warnings for {email}: {gate['warnings']}")
        except Exception as e_gate:
            logger.warning(f"Deliverability pre-send check skipped: {e_gate}")

    # Step 3: Send or simulate
    if mode == CampaignMode.dry_run:
        result.status = "previewed"
        logger.info(
            f"[DRY RUN] Would send to {name} ({email}) | "
            f"Subject: {subject} | Score: {client.lead_score} | Priority: {client.priority}"
        )
    else:
        try:
            await send_email(
                recipient=email,
                subject=subject,
                body=body,
                smtp_config=smtp_config,
            )
            result.status = "sent"
            # Register sent email for auto-reply tracking
            try:
                from services.history_service import register_sent_email
                register_sent_email(email=email, name=name, subject=subject, body=body)
            except Exception as e_hist:
                logger.error(f"Failed to register sent email in history: {e_hist}")
        except Exception as e:
            result.status = "failed"
            result.error = str(e)

    return result


def _csv_get(row: dict, *keys: str, default=None):
    """Case-insensitive and normalization-friendly CSV column getter — tries multiple key variants."""
    import re
    def normalize(s):
        return re.sub(r'[^a-z0-9]', '', str(s).lower()) if s else ""
        
    normalized_row = {normalize(k): v for k, v in row.items() if k is not None}
    for key in keys:
        val = row.get(key) or row.get(key.lower()) or row.get(key.upper()) or row.get(key.title())
        if val and str(val).strip():
            return str(val).strip()
            
        norm_key = normalize(key)
        val = normalized_row.get(norm_key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def _parse_lead_score(val) -> Optional[int]:
    """Safely parse lead score to int."""
    try:
        return int(float(str(val).strip())) if val else None
    except (ValueError, TypeError):
        return None


PRIORITY_ORDER = {"high": 0, "medium": 1, "med": 1, "low": 2}


def sort_and_filter_clients(
    clients: List[ClientInput],
    sort_by_score: bool = True,
    min_lead_score: Optional[int] = None,
    priority_filter: Optional[str] = None,
) -> List[ClientInput]:
    """
    1. Filter: remove leads below min_lead_score (if set).
    2. Filter: keep only specified priority level (if set).
    3. Sort: High priority first, then by lead_score descending.
    Ensures hottest leads always get sent first.
    """
    filtered = clients

    # Filter by minimum lead score
    if min_lead_score is not None:
        before = len(filtered)
        filtered = [
            c for c in filtered
            if c.lead_score is None or c.lead_score >= min_lead_score
        ]
        logger.info(f"Lead score filter (>={min_lead_score}): {before} → {len(filtered)} leads")

    # Filter by priority level
    if priority_filter:
        pf_lower = priority_filter.strip().lower()
        before = len(filtered)
        filtered = [
            c for c in filtered
            if (c.priority or "").strip().lower() == pf_lower
        ]
        logger.info(f"Priority filter ('{priority_filter}'): {before} → {len(filtered)} leads")

    # Sort: priority first (High → Medium → Low), then lead_score descending
    if sort_by_score:
        filtered.sort(
            key=lambda c: (
                PRIORITY_ORDER.get((c.priority or "low").strip().lower(), 2),  # priority rank
                -(c.lead_score or 0),                                           # score desc
            )
        )
        logger.info(
            f"Campaign sorted: {len(filtered)} leads ordered by Priority → Lead Score desc"
        )

    return filtered


async def run_campaign_background_task(mode: CampaignMode, clients: List[ClientInput], delay_seconds: int):
    global _campaign_state, _cancel_campaign_flag, _last_campaign
    
    _campaign_state["status"] = "running"
    _campaign_state["mode"] = mode
    _campaign_state["total"] = len(clients)
    _campaign_state["processed"] = 0
    _campaign_state["sent"] = 0
    _campaign_state["failed"] = 0
    _campaign_state["skipped"] = 0
    _campaign_state["results"] = []
    _cancel_campaign_flag = False
    
    smtp_config = get_smtp_config() if mode == CampaignMode.live else None
    
    logger.info(f"Starting background campaign task. Mode: {mode.value}, leads: {len(clients)}")
    
    for i, client in enumerate(clients):
        if _cancel_campaign_flag:
            logger.info("Campaign was cancelled by the user.")
            _campaign_state["status"] = "cancelled"
            return

        # ── Deliverability Agent: Check warmup daily limit (live mode only) ──
        if mode == CampaignMode.live:
            try:
                from services.deliverability_agent import get_warmup_status
                warmup = get_warmup_status()
                if warmup["remaining"] <= 0:
                    logger.warning(
                        f"[Deliverability] Warmup daily limit reached "
                        f"({warmup['sent_today']}/{warmup['daily_limit']}). "
                        f"Day {warmup['warmup_day']}, phase: {warmup['phase']}. "
                        f"Stopping campaign — resume tomorrow."
                    )
                    _campaign_state["status"] = "completed"
                    break
            except Exception as e:
                logger.warning(f"Warmup check skipped: {e}")
            
        _campaign_state["current_lead"] = f"{client.name} ({client.email})"
        
        try:
            result = await process_single_client(
                client=client,
                mode=mode,
                smtp_config=smtp_config,
            )
            _campaign_state["results"].append(result)
            _campaign_state["processed"] += 1
            
            if result.status == "sent":
                _campaign_state["sent"] += 1
            elif result.status == "previewed":
                _campaign_state["sent"] += 1
            elif result.status == "skipped":
                _campaign_state["skipped"] += 1
            else:
                _campaign_state["failed"] += 1
                
        except Exception as e:
            logger.error(f"Error processing client {client.email}: {e}")
            _campaign_state["failed"] += 1
            _campaign_state["results"].append(ClientResult(
                name=client.name,
                email=client.email,
                status="failed",
                error=str(e)
            ))
            
        # Anti-spam delay between real sends (not last email)
        if (
            i < len(clients) - 1
            and not _cancel_campaign_flag
        ):
            if mode == CampaignMode.live:
                # ── Deliverability Agent: Use randomized human-like delays ────
                # Instead of fixed delay_seconds, use gaussian-distributed delays
                # with jitter to mimic human sending patterns (45-120s range).
                try:
                    from services.deliverability_agent import get_human_delay
                    actual_delay = get_human_delay(
                        base_min=max(45.0, delay_seconds * 0.75),
                        base_max=max(120.0, delay_seconds * 2.0)
                    )
                    logger.info(f"[Deliverability] Next send in {actual_delay}s (human-like delay)")
                except Exception:
                    actual_delay = delay_seconds
            else:
                # In dry_run, enforce a smaller delay (e.g., 2 seconds) to avoid API rate limits
                actual_delay = 2.0
            
            # Check for cancel flag during sleep
            sleep_step = 1.0
            elapsed = 0.0
            while elapsed < actual_delay:
                if _cancel_campaign_flag:
                    break
                await asyncio.sleep(sleep_step)
                elapsed += sleep_step
                
    if _cancel_campaign_flag:
        _campaign_state["status"] = "cancelled"
    else:
        _campaign_state["status"] = "completed"
        
    _campaign_state["current_lead"] = None
    
    # Store in _last_campaign for compatibility
    _last_campaign = CampaignResponse(
        mode=_campaign_state["mode"],
        total=_campaign_state["total"],
        sent=_campaign_state["sent"],
        failed=_campaign_state["failed"],
        skipped=_campaign_state["skipped"],
        results=_campaign_state["results"]
    )
    
    logger.info(f"Background campaign finished. Status: {_campaign_state['status']}")


def _extract_client_from_row(row: dict) -> Optional[ClientInput]:
    """Extract a ClientInput from a CSV row dictionary with fast normalization."""
    import re
    # Pre-map clean keys once for this row
    norm_map = {}
    for k, v in row.items():
        if k is not None and v is not None:
            val_str = str(v).strip()
            if val_str:
                k_clean = re.sub(r'[^a-z0-9]', '', str(k).lower())
                norm_map[k_clean] = val_str
                norm_map[str(k).strip()] = val_str

    def get_val(*keys, default=None):
        for key in keys:
            if key in norm_map:
                return norm_map[key]
            k_clean = re.sub(r'[^a-z0-9]', '', str(key).lower())
            if k_clean in norm_map:
                return norm_map[k_clean]
        return default

    # Core Contact
    first = get_val("Full name", "First Name", "first name", "firstname")
    last  = get_val("last name", "Last Name", "lastname", "surname")
    if first and last:
        name = f"{first} {last}".strip()
    else:
        name = first or last or get_val(
            "Decision Maker", "Decision Maker Name",
            "Primary Contact", "name", "Full Name", "Contact Name"
        ) or ""

    email = get_val(
        "Email",
        "email",
        "Direct Email",
        "Corporate Email",
        "Business Email",
        "Verified Email",
        "Email Address",
        "Contact Email",
        "company email",
    ) or ""

    if not email.strip():
        return None

    website = get_val("website", "Website", "Website URL", "web")

    # Address / Location
    city  = get_val("City", "Headquarters City", "HQ City")
    state = get_val("State", "HQ State")
    hq    = get_val("address", "Headquarters", "HQ", "Address")
    if hq and not city:
        parts = hq.split(",")
        city = parts[0].strip()
        if len(parts) > 1 and not state:
            state = parts[1].strip()

    return ClientInput(
        name=name,
        email=email,
        website=website,
        company_name=get_val("Company", "Company Name", "company", "Organization", "Business Name", "Account Name"),
        industry=get_val("Industry", "sector", "Vertical", "Category"),
        city=city,
        state=state,
        employees=get_val("employees", "Employee Size", "Employees", "Team Size", "headcount", "Company Size", "Staff"),
        revenue=get_val("Revenue", "Estimated Revenue", "Annual Revenue", "Estimated Annual Revenue"),
        ceo=get_val("CEO", "Chief Executive Officer", "Founder", "Owner", "President"),
        title=get_val("Position", "function", "Function", "Title", "Job Title", "Decision Maker Position", "Role", "Designation"),
        phone=get_val("Phone", "Direct Phone", "Business Phone", "Phone Number", "Telephone", "Mobile", "Contact Number"),
        linkedin=get_val("Linked In", "LinkedIn", "LinkedIn Profile", "Decision Maker LinkedIn", "LinkedIn URL", "Person LinkedIn"),
        website_quality=get_val("Technology Stack", "Website Technology", "Website Quality", "Tech Stack"),
        ai_readiness=get_val("AI Readiness", "AI Adoption"),
        lead_score=_parse_lead_score(
            get_val("Priority Score (1-100)", "Lead Score", "Score", "Rating", "Priority Score")
        ),
        buying_intent=get_val("Buying Intent", "Intent", "Interest Level"),
        problem_statement=get_val("Problem Statement", "Current Problems", "Problems", "Pain Point", "Challenges"),
        recommended_ai_solution=get_val("Recommended AI Solution", "AI Opportunity", "AI Solution"),
        recommended_web_solution=get_val("Recommended Web Solution", "Website Opportunity", "Web Solution"),
        estimated_project_value=get_val("Estimated Project Value", "Project Value", "Value", "Expected ROI", "Deal Size"),
        estimated_timeline=get_val("Estimated Timeline", "Timeline", "Target Date"),
        priority=get_val("Priority", "Buying Intent", "Tier"),
        notes=get_val("Notes", "Reason for Qualification", "comments", "Billed Hr", "Billed Hrs", "Verified/Not", "Status"),
    )


def parse_clients_from_csv_text(csv_text: str) -> List[ClientInput]:
    """Parse CSV text directly from memory into ClientInput objects."""
    import io
    clients = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        client = _extract_client_from_row(row)
        if client:
            clients.append(client)
    return clients


def read_clients_from_csv(csv_path: str) -> List[ClientInput]:
    """Read CSV file and return a list of fully-populated ClientInput objects."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    clients = []
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            client = _extract_client_from_row(row)
            if client:
                clients.append(client)

    logger.info(f"CSV loaded: {len(clients)} valid leads from '{csv_path}'")
    return clients


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, tags=["Info"])
async def root():
    """Nexariza API landing page with quick links."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Nexariza AI Outreach API</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            :root {
                --primary: #89b4fa;
                --secondary: #a6e3a1;
                --accent: #f38ba8;
                --bg: #11111b;
                --card-bg: rgba(49, 50, 68, 0.6);
                --text-main: #cdd6f4;
                --text-sub: #a6adc8;
            }
            body { 
                font-family: 'Inter', sans-serif; 
                background: linear-gradient(135deg, #1e1e2e 0%, #11111b 100%); 
                color: var(--text-main); 
                display: flex; justify-content: center; align-items: center; 
                min-height: 100vh; margin: 0; overflow: hidden;
            }
            /* Animated background blobs */
            .blob {
                position: absolute; border-radius: 50%; filter: blur(80px); z-index: 0; animation: float 10s infinite alternate;
            }
            .blob1 { width: 300px; height: 300px; background: rgba(137, 180, 250, 0.2); top: -100px; left: -100px; }
            .blob2 { width: 400px; height: 400px; background: rgba(166, 227, 161, 0.15); bottom: -150px; right: -100px; animation-delay: -5s; }
            
            .card { 
                background: var(--card-bg); 
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 24px; padding: 56px 48px; max-width: 650px; 
                box-shadow: 0 24px 48px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1); 
                text-align: center; position: relative; z-index: 1;
                transform: translateY(0); transition: transform 0.3s ease, box-shadow 0.3s ease;
            }
            .card:hover { transform: translateY(-5px); box-shadow: 0 32px 64px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255, 255, 255, 0.1); }
            
            .badge { 
                display: inline-block; background: linear-gradient(90deg, #f9e2af, #fab387); 
                color: #11111b; padding: 6px 16px; border-radius: 99px; font-size: 0.85rem; 
                font-weight: 800; letter-spacing: 0.5px; margin-bottom: 24px; text-transform: uppercase;
                box-shadow: 0 4px 12px rgba(249, 226, 175, 0.3);
            }
            h1 { 
                background: linear-gradient(90deg, var(--primary), #cba6f7);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                font-size: 2.75rem; margin: 0 0 16px 0; font-weight: 800; letter-spacing: -1px;
            }
            p { color: var(--text-sub); margin-bottom: 40px; font-size: 1.1rem; line-height: 1.6; }
            
            .links { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }
            a { 
                position: relative; overflow: hidden;
                background: rgba(255, 255, 255, 0.05); color: var(--text-main); 
                padding: 14px 28px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1);
                text-decoration: none; font-weight: 600; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); 
                display: flex; align-items: center; gap: 8px;
            }
            a:hover { 
                background: rgba(255, 255, 255, 0.1); 
                transform: translateY(-2px); border-color: rgba(255, 255, 255, 0.2);
            }
            a::before {
                content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
                transition: left 0.5s ease;
            }
            a:hover::before { left: 100%; }
            
            a.primary { background: linear-gradient(135deg, var(--primary), #74c7ec); color: #11111b; border: none; box-shadow: 0 8px 16px rgba(137, 180, 250, 0.3); }
            a.primary:hover { box-shadow: 0 12px 24px rgba(137, 180, 250, 0.4); }
            a.secondary { background: linear-gradient(135deg, var(--secondary), #8bd5ca); color: #11111b; border: none; box-shadow: 0 8px 16px rgba(166, 227, 161, 0.3); }
            a.secondary:hover { box-shadow: 0 12px 24px rgba(166, 227, 161, 0.4); }
            a.danger { background: linear-gradient(135deg, var(--accent), #eba0ac); color: #11111b; border: none; box-shadow: 0 8px 16px rgba(243, 139, 168, 0.3); }
            a.danger:hover { box-shadow: 0 12px 24px rgba(243, 139, 168, 0.4); }

            @keyframes float {
                0% { transform: translate(0, 0) scale(1); }
                100% { transform: translate(30px, 50px) scale(1.1); }
            }
        </style>
    </head>
    <body>
        <div class="blob blob1"></div>
        <div class="blob blob2"></div>
        <div class="card">
            <div class="badge">v2.0.0 — AI Powered</div>
            <h1>🚀 Nexariza Outreach API</h1>
            <p>Gemini AI analyzes your clients and crafts personalized pitch emails automatically. Scale your outreach with state-of-the-art intelligence.</p>
            <div class="links">
                <a href="/docs" class="primary">📖 Swagger Docs</a>
                <a href="/redoc" class="secondary">📚 ReDoc</a>
                <a href="/health" class="danger">❤️ Health</a>
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/health", tags=["Info"])
async def health_check(check_smtp: bool = False):
    """
    Health check endpoint for Render/UptimeRobot and monitoring.
    Returns status, server uptime, and timestamp.
    Pass ?check_smtp=true to also test the SMTP server connection.
    """
    uptime_seconds = int(time.time() - _server_start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    response = {
        "status": "ok",
        "api": "online",
        "uptime": uptime_str,
        "uptime_seconds": uptime_seconds,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "gemini_key_set": bool(os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")),
    }

    if check_smtp:
        try:
            smtp = await asyncio.wait_for(test_smtp_connection(), timeout=5.0)
        except asyncio.TimeoutError:
            smtp = {"status": "error", "message": "SMTP check timed out after 5s"}
        except Exception as e:
            smtp = {"status": "error", "message": str(e)}
        response["smtp"] = smtp

    return response


@app.get("/ping", tags=["Info"])
async def ping():
    """Ultra-lightweight ping route specifically for UptimeRobot / Keep-Alive monitors."""
    return {
        "status": "pong",
        "uptime_seconds": int(time.time() - _server_start_time),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


@app.post("/client/analyze", response_model=AnalyzeClientResponse, tags=["Analysis"])
async def analyze_client(request: SingleClientRequest):
    """
    Analyze a single client:
    - Scrapes their website (or infers from email domain)
    - Generates a personalized email using Gemini
    - Optionally sends it (based on mode)
    """
    result = await process_single_client(
        client=request.client,
        mode=request.mode,
        smtp_config=get_smtp_config() if request.mode == CampaignMode.live else None,
    )

    if result.status == "failed" and result.error and "Gemini" in result.error:
        raise HTTPException(status_code=502, detail=result.error)

    return AnalyzeClientResponse(
        client=request.client,
        website_content_preview=result.website_scraped,
        generated_subject=result.email_subject or "",
        generated_body=result.email_body or "",
        status=result.status,
    )


@app.post("/campaign/upload", tags=["Campaign"])
async def upload_campaign_csv(file: UploadFile = File(...)):
    """
    Upload a new CSV file to replace the current clients.csv.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    
    file_path = "clients.csv"
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Validate the newly uploaded file
        clients = read_clients_from_csv(file_path)
        return {"message": f"Successfully uploaded {file.filename}", "total_leads": len(clients)}
    except Exception as e:
        logger.error(f"Failed to upload and parse CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")


@app.post("/campaign/validate-csv", tags=["Campaign"])
async def validate_campaign_csv(file: UploadFile = File(...)):
    """
    Upload a CSV file and validate its email addresses.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    
    try:
        content = await file.read()
        # Decode content to text
        text = content.decode('utf-8-sig', errors='replace')
        f = io.StringIO(text)
        reader = csv.DictReader(f)
        
        # Try to find the email column
        fieldnames = reader.fieldnames or []
        email_col = None
        
        # Look for likely email columns
        for col in ["Verified Email", "Email", "Email Address", "Primary Contact Email"]:
            if col in fieldnames:
                email_col = col
                break
        
        # Fallback: case insensitive search
        if not email_col:
            for col in fieldnames:
                if "email" in col.lower():
                    email_col = col
                    break
                    
        if not email_col:
            raise HTTPException(status_code=400, detail="Could not find an email column in the CSV.")

        # Complete the validate-csv endpoint - process and return results
        results = []
        valid_count = 0
        invalid_count = 0

        rows = list(reader)
        semaphore = asyncio.Semaphore(10) # Safe limit for DNS/SMTP socket pool

        async def process_row(row):
            email = row.get(email_col, "").strip()
            if not email:
                return None

            async with semaphore:
                analysis = await verify_email_deep(email)

            return {
                "email": email,
                "is_valid": analysis["is_valid"],
                "reason": analysis["reason"],
                "original_row": row
            }

        tasks = [process_row(row) for row in rows]
        processed = await asyncio.gather(*tasks)

        for res in processed:
            if not res:
                continue
            results.append(res)

        return {
            "message": f"Validation completed",
            "total_processed": len(results),
            "valid_count": sum(1 for r in results if r["is_valid"]),
            "invalid_count": sum(1 for r in results if not r["is_valid"]),
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to validate CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")

@app.post("/campaign/run", response_model=CampaignStatusResponse, tags=["Campaign"])
async def run_campaign(request: CampaignRequest, background_tasks: BackgroundTasks):
    """
    Run the full AI campaign in background.
    """
    global _campaign_state
    if _campaign_state["status"] == "running":
        raise HTTPException(status_code=400, detail="A campaign is already running.")
        
    csv_path = request.csv_path or "clients.csv"
    try:
        raw_clients = read_clients_from_csv(csv_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    if not raw_clients:
        raise HTTPException(status_code=400, detail="No valid clients found in CSV.")
        
    clients = sort_and_filter_clients(
        raw_clients,
        sort_by_score=request.sort_by_score,
        min_lead_score=request.min_lead_score,
        priority_filter=request.priority_filter,
    )
    
    if not clients:
        raise HTTPException(status_code=400, detail="No clients remain after filters.")
        
    background_tasks.add_task(
        run_campaign_background_task,
        mode=request.mode,
        clients=clients,
        delay_seconds=request.delay_seconds
    )
    
    return CampaignStatusResponse(
        status="running",
        mode=request.mode,
        total=len(clients)
    )


@app.post("/campaign/run_batch", response_model=CampaignStatusResponse, tags=["Campaign"])
async def run_batch_campaign(request: BatchCampaignRequest, background_tasks: BackgroundTasks):
    """
    Run a batch campaign from list of clients in background.
    """
    global _campaign_state
    if _campaign_state["status"] == "running":
        raise HTTPException(status_code=400, detail="A campaign is already running.")
        
    if not request.clients:
        raise HTTPException(status_code=400, detail="No clients provided.")
        
    clients = sort_and_filter_clients(
        request.clients,
        sort_by_score=request.sort_by_score,
        min_lead_score=request.min_lead_score,
        priority_filter=request.priority_filter,
    )
    
    if not clients:
        raise HTTPException(status_code=400, detail="No clients remain after filters.")
        
    background_tasks.add_task(
        run_campaign_background_task,
        mode=request.mode,
        clients=clients,
        delay_seconds=request.delay_seconds
    )
    
    return CampaignStatusResponse(
        status="running",
        mode=request.mode,
        total=len(clients)
    )


@app.get("/campaign/status", response_model=CampaignStatusResponse, tags=["Campaign"])
async def campaign_status():
    """Returns the results of the active or last campaign run."""
    global _campaign_state
    return _campaign_state


@app.post("/campaign/cancel", tags=["Campaign"])
async def cancel_campaign():
    """Cancels the currently running outreach campaign."""
    global _cancel_campaign_flag, _campaign_state
    if _campaign_state["status"] == "running":
        _cancel_campaign_flag = True
        return {"message": "Cancellation request sent."}
    return {"message": "No campaign is currently running."}


@app.post("/email/verify", response_model=EmailVerificationResponse, tags=["Validation"])
async def verify_email_address_endpoint(request: EmailVerificationRequest):
    """Verify a single email address deliverability with deep checks."""
    result = await verify_email_deep(request.email)
    return result

# ── AI Auto-Responder Lifespans & Endpoints ────────────────────────────────────

# @app.on_event("startup")  # IMAP auto-responder disabled
# async def startup_event():
#     try:
#         from services.incoming_email_service import start_responder
#         start_responder()
#         logger.info("Auto-Responder background service started on API startup.")
#     except Exception as e:
#         logger.error(f"Failed to start auto-responder on startup: {e}")


# @app.on_event("shutdown")  # IMAP auto-responder disabled
# async def shutdown_event():
#     try:
#         from services.incoming_email_service import stop_responder
#         stop_responder()
#         logger.info("Auto-Responder background service stopped on API shutdown.")
#     except Exception as e:
#         logger.error(f"Failed to stop auto-responder on shutdown: {e}")


@app.get("/responder/status", tags=["Responder"])
async def responder_status():
    """Get status of the AI Auto-Responder and total replies sent."""
    try:
        from services.incoming_email_service import is_responder_active
        from services.history_service import get_auto_replies
        active = is_responder_active()
        replies = get_auto_replies()
        return {
            "active": active,
            "status": "active" if active else "inactive",
            "history_count": len(replies)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/responder/toggle", tags=["Responder"])
async def responder_toggle():
    """Toggle the background auto-responder service on/off."""
    try:
        from services.incoming_email_service import is_responder_active, start_responder, stop_responder
        active = is_responder_active()
        if active:
            stop_responder()
            new_state = False
        else:
            start_responder()
            new_state = True
        return {
            "active": new_state,
            "status": "active" if new_state else "inactive"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/responder/check", tags=["Responder"])
async def responder_check():
    """Force an immediate manual check/reply check on the inbox."""
    try:
        from services.incoming_email_service import check_inbox_and_reply
        result = await check_inbox_and_reply()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/responder/history", tags=["Responder"])
async def responder_history():
    """Retrieve all auto-replies sent by the agent."""
    try:
        from services.history_service import get_auto_replies
        return get_auto_replies()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Legal Unsubscribe & Anti-Spam Compliance Endpoints ───────────────────────

@app.get("/unsubscribe", response_class=HTMLResponse, tags=["Compliance"])
@app.post("/unsubscribe", response_class=HTMLResponse, tags=["Compliance"])
async def unsubscribe_page(email: Optional[str] = Query(None)):
    """
    Standard legal unsubscribe destination page required for email compliance.
    """
    email_text = f" for <strong>{email}</strong>" if email else ""
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Unsubscribed — Nexariza AI</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f3f4f6; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
            .card {{ background: #ffffff; padding: 40px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); max-width: 480px; width: 100%; text-align: center; }}
            h1 {{ color: #111827; font-size: 24px; margin-bottom: 12px; }}
            p {{ color: #4b5563; font-size: 15px; line-height: 1.5; margin-bottom: 24px; }}
            .badge {{ display: inline-block; background-color: #ecfdf5; color: #047857; padding: 6px 14px; border-radius: 9999px; font-weight: 600; font-size: 14px; margin-bottom: 16px; }}
            a {{ color: #2563eb; text-decoration: none; font-weight: 500; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="badge">✓ Preference Updated</div>
            <h1>You have been unsubscribed</h1>
            <p>Your email address{email_text} has been successfully removed from Nexariza AI outreach communications. You will not receive further outreach emails from us.</p>
            <p><a href="https://nexariza.com">Return to Nexariza AI Homepage</a></p>
        </div>
    </body>
    </html>
    """)


@app.post("/email/check-spam-score", response_model=SpamCheckResponse, tags=["Validation"])
async def check_email_spam_score(request: SpamCheckRequest):
    """
    Check an email subject and body for spam trigger words, ALL CAPS words, and link limits.
    Returns warnings, spam score, and sanitized content.
    """
    subject, body, report = cleanse_and_validate_email(request.subject, request.body)
    return SpamCheckResponse(
        is_clean=report["is_clean"],
        warnings=report["warnings"],
        spam_score=report["spam_score"],
        cleaned_subject=subject,
        cleaned_body=body
    )


# ── Deliverability Agent Endpoints ───────────────────────────────────────────

@app.post("/deliverability/score", tags=["Deliverability"])
async def deliverability_score(request: SpamCheckRequest):
    """
    Analyze an email's subject + body for deliverability.
    Returns a spam score (0-100, lower = better), rating, warnings,
    and detailed breakdown of issues found.
    """
    try:
        from services.deliverability_agent import check_deliverability_score
        result = check_deliverability_score(request.subject, request.body)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/deliverability/warmup-status", tags=["Deliverability"])
async def warmup_status():
    """
    Get current domain warmup status.
    Shows warmup day, daily send limit, emails sent today, remaining quota,
    and current warmup phase (week1-4 or full_volume).
    """
    try:
        from services.deliverability_agent import get_warmup_status
        return get_warmup_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/deliverability/warmup-reset", tags=["Deliverability"])
async def warmup_reset():
    """
    Reset the domain warmup tracker. Restarts the warmup schedule from Day 1.
    Use with caution — only reset if you've changed SMTP providers or domains.
    """
    try:
        from services.deliverability_agent import reset_warmup
        return reset_warmup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/deliverability/domain-health", tags=["Deliverability"])
async def domain_health(domain: str = Query(default="nexariza.com")):
    """
    Live DNS health check for SPF, DKIM, DMARC, and MX records.
    Returns per-record status, issues found, and an overall score (0-100).
    """
    try:
        from services.deliverability_agent import check_domain_health
        result = await check_domain_health(domain)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/deliverability/pre-send-check", tags=["Deliverability"])
async def pre_send_check_endpoint(request: SpamCheckRequest):
    """
    Full pre-send gate: combines deliverability score, warmup limit check,
    and content uniqueness verification.
    Returns a go/no-go decision with block reasons and warnings.
    """
    try:
        from services.deliverability_agent import pre_send_check
        result = pre_send_check(request.subject, request.body)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Internship Offer Letter & ID Card Endpoints ────────────────────────────────

@app.post("/internship/upload-csv", tags=["Internship"])
async def upload_interns_csv(file: UploadFile = File(...)):
    """
    Upload and parse an intern CSV file.
    Returns parsed intern list and count.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")
    
    try:
        contents = await file.read()
        csv_text = contents.decode("utf-8-sig")
        from services.internship_service import parse_interns_csv
        interns = parse_interns_csv(csv_text)
        return {"filename": file.filename, "total_interns": len(interns), "interns": interns}
    except Exception as e:
        logger.error(f"Error parsing intern CSV: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse CSV file: {str(e)}")


@app.post("/internship/preview", tags=["Internship"])
async def preview_intern_offer(request: InternshipSingleRequest):
    """
    Generate an HTML preview of the Offer Letter & Intern ID Card.
    """
    try:
        from services.internship_service import (
            build_full_offer_email_html,
            build_job_response_email_html,
            is_job_application,
            build_intern_card_html,
            build_downloadable_card_file
        )
        intern_dict = request.intern.dict()
        config_dict = request.config.dict() if request.config else {}

        role = intern_dict.get("role", "")
        if is_job_application(role):
            email_html = build_job_response_email_html(intern_dict, config_dict)
            subject = f"Application Status & Internship Opportunities — {request.intern.name} | {config_dict.get('company_name', 'Nexariza AI Technologies')}"
            app_type = "job_response"
        else:
            email_html = build_full_offer_email_html(intern_dict, config_dict)
            subject = f"🎓 Internship Offer Letter — {request.intern.name} | {config_dict.get('company_name', 'Nexariza AI Technologies')}"
            app_type = "internship_offer"

        card_html = build_intern_card_html(intern_dict, config_dict)
        card_file_html = build_downloadable_card_file(intern_dict, config_dict)

        return {
            "subject": subject,
            "email_html": email_html,
            "application_type": app_type,
            "card_html": card_html,
            "card_file_html": card_file_html,
            "intern": intern_dict,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/internship/send-single", response_model=InternshipResult, tags=["Internship"])
async def send_single_intern_offer(request: InternshipSingleRequest):
    """
    Send or dry-run a single internship offer letter and ID card email.
    """
    try:
        from services.internship_service import process_single_intern
        intern_dict = request.intern.dict()
        config_dict = request.config.dict() if request.config else {}

        res = await process_single_intern(
            intern=intern_dict,
            config=config_dict,
            mode=request.mode
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/internship/run-batch", tags=["Internship"])
async def run_internship_batch_endpoint(request: InternshipBatchRequest, background_tasks: BackgroundTasks):
    """
    Launch background batch dispatch for sending internship offer letters & cards.
    """
    try:
        from services.internship_service import get_internship_state, run_internship_batch
        state = get_internship_state()
        if state["status"] == "running":
            raise HTTPException(status_code=400, detail="An internship campaign is already running.")

        interns_dict = [i.dict() for i in request.interns]
        config_dict = request.config.dict() if request.config else {}

        background_tasks.add_task(
            run_internship_batch,
            interns=interns_dict,
            config=config_dict,
            mode=request.mode,
            delay_seconds=request.delay_seconds
        )

        return {
            "status": "started",
            "mode": request.mode,
            "total_interns": len(request.interns),
            "message": f"Internship offer campaign started in background ({request.mode.value} mode)."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/internship/status", tags=["Internship"])
async def get_internship_status():
    """
    Get live progress status of ongoing or last completed internship campaign.
    """
    try:
        from services.internship_service import get_internship_state
        return get_internship_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/internship/cancel", tags=["Internship"])
async def cancel_internship_status():
    """
    Cancel an active background internship campaign.
    """
    try:
        from services.internship_service import cancel_internship_campaign
        cancel_internship_campaign()
        return {"status": "cancelling", "message": "Cancellation request sent."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# ── Sales Campaign State ──────────────────────────────────────────────────────
_sales_state = {
    "status": "idle",   # "idle" | "running" | "completed" | "cancelled" | "failed"
    "total": 0,
    "sent": 0,
    "failed": 0,
    "skipped": 0,
    "current_lead": None,
    "log": [],          # live log lines
    "prospects_available": 0,
}
_sales_cancel_flag = False


@app.get("/sales/status", tags=["Sales Campaign"])
async def get_sales_status():
    """Get current status of the sales@nexariza.com campaign."""
    global _sales_state

    # Count available prospects in sent_history.csv
    sent_hist = "sent_history.csv"
    count = 0
    if os.path.exists(sent_hist):
        with open(sent_hist, "r", encoding="utf-8") as f:
            count = max(0, sum(1 for row in csv.DictReader(f) if row.get("Email", "").strip()))
    _sales_state["prospects_available"] = count
    return _sales_state


@app.post("/sales/run", tags=["Sales Campaign"])
async def run_sales_campaign(
    background_tasks: BackgroundTasks,
    count: int = Query(..., ge=1, le=200, description="How many prospects to email (1-200)"),
):
    """
    Start the sales@nexariza.com campaign in the background.
    Reads `count` prospects from sent_history.csv, generates fresh AI emails,
    sends via sales@nexariza.com, then moves records to sale_sent_history.csv.
    """
    global _sales_state, _sales_cancel_flag

    if _sales_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Sales campaign is already running.")

    sent_hist = "sent_history.csv"
    if not os.path.exists(sent_hist):
        raise HTTPException(status_code=404, detail="sent_history.csv not found.")

    from services.email_service import analyze_email

    prospects = []
    invalid_emails = set()
    with open(sent_hist, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            email = row.get("Email", "").strip()
            if email:
                val = analyze_email(email)
                if val["is_valid"]:
                    prospects.append(dict(row))
                else:
                    invalid_emails.add(email)

    # Prune unsendable/role-based emails from sent_history.csv so they don't block the queue
    if invalid_emails:
        logger.info(f"[Sales] Pruning {len(invalid_emails)} unsendable/role-based email(s) from sent_history.csv")
        try:
            with open(sent_hist, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                fn = reader.fieldnames or ["Email", "Name", "Subject", "Body", "Sent At"]
                kept = [r for r in reader if r.get("Email", "").strip() not in invalid_emails]
            with open(sent_hist, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fn)
                writer.writeheader()
                writer.writerows(kept)
        except Exception as e_prune:
            logger.warning(f"[Sales] Failed to prune unsendable emails: {e_prune}")

    if not prospects:
        raise HTTPException(status_code=400, detail="No valid prospects in sent_history.csv.")

    targets = prospects[:min(count, len(prospects))]

    # Reset state
    _sales_state.update({
        "status": "running",
        "total": len(targets),
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "current_lead": None,
        "log": [f"Campaign started: {len(targets)} prospects queued from sent_history.csv"],
    })
    _sales_cancel_flag = False

    background_tasks.add_task(_run_sales_background, targets)

    return {
        "status": "started",
        "total": len(targets),
        "message": f"Sales campaign started for {len(targets)} prospects."
    }


async def _run_sales_background(targets: list):
    """Background worker for the sales campaign."""
    global _sales_state, _sales_cancel_flag

    import sys
    sys.path.insert(0, os.path.dirname(__file__))

    # Inline the sales email generation logic
    import random, ssl, re
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid
    import aiosmtplib

    SALES_SMTP_SERVER  = os.getenv("SALES_SMTP_SERVER",  "smtp.zoho.com")
    SALES_SMTP_PORT    = int(os.getenv("SALES_SMTP_PORT", "465"))
    SALES_SENDER_EMAIL = os.getenv("SALES_SENDER_EMAIL", "sales@nexariza.com")
    SALES_SENDER_PASS  = os.getenv("SALES_SENDER_PASSWORD", "")

    SALE_SENT_CSV   = "sale_sent_history.csv"
    SENT_HIST_CSV   = "sent_history.csv"

    FREE_DOMAINS = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "icloud.com", "aol.com", "live.com", "protonmail.com",
    }

    SALES_PROMPT_SYSTEM = """You are a senior sales representative for Nexariza AI.
Write a SHORT, deeply personalized cold outreach email from sales@nexariza.com.
Nexariza AI builds custom AI systems, ML models, full-stack web apps, and workflow automation.

RULES:
- Subject: 3-7 words, personalized, intriguing
- Opening: "Hi [Name]," then something specific about their business/domain — NO generic openers
- Body: 100-150 words, conversational, plain-text, 1 specific industry pain point + what Nexariza would do
- Closing: ONE soft CTA ("Would a quick 15-minute call make sense?")
- End the body with ONLY "Best," on its own line — do NOT include any name, signature, or contact info after it (the signature is added automatically)
- NEVER use: FREE, URGENT, GUARANTEED, ACT NOW, BUY NOW, CLICK HERE, 100%, DISCOUNT
- NO ALL CAPS, no emojis, max 1 link
- FRESH ANGLE: This is first-time outreach — completely new, not a follow-up

Output FORMAT:
SUBJECT: <subject>
---
<body>"""

    def _log(msg: str):
        logger.info(f"[Sales] {msg}")
        _sales_state["log"].append(msg)
        if len(_sales_state["log"]) > 200:
            _sales_state["log"] = _sales_state["log"][-200:]

    async def _gen_email(name, email, orig_sub):
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

        # 3. Problem statement with prior subject avoidance
        problem_statement = (
            f"Fresh outreach from sales team (sales@nexariza.com). "
            f"Do NOT repeat this prior subject: '{orig_sub}'. "
            "Pitch a fresh, high-value AI automation or software angle."
        )

        # 4. Generate hyper-personalized email via Groq/Gemini pool (1000 token limit)
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

    async def _send(recipient, subject, body):
        from services.email_service import send_email, get_sales_smtp_config

        sales_config = get_sales_smtp_config()
        if not sales_config.get("password"):
            raise ValueError("SALES_SENDER_PASSWORD is not configured in .env")

        await send_email(
            recipient=recipient,
            subject=subject,
            body=body,
            sender_name="Hassan Nadeem | Nexariza AI",
            smtp_config=sales_config,
        )


    def _remove_from_sent(email_addr):
        if not os.path.exists(SENT_HIST_CSV):
            return
        kept = []
        with open(SENT_HIST_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fn = reader.fieldnames or ["Email", "Name", "Subject", "Body", "Sent At"]
            for row in reader:
                if row.get("Email", "").strip().lower() != email_addr.lower():
                    kept.append(row)
        with open(SENT_HIST_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            writer.writeheader()
            writer.writerows(kept)

    def _append_sale_sent(email_addr, name, orig_sub, sales_sub, sales_body, sent_at):
        fn = ["Email", "Name", "Original Subject", "Sales Subject", "Sales Body", "Sales Sent At"]
        exists = os.path.isfile(SALE_SENT_CSV)
        with open(SALE_SENT_CSV, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fn)
            if not exists:
                writer.writeheader()
            writer.writerow({
                "Email": email_addr, "Name": name,
                "Original Subject": orig_sub, "Sales Subject": sales_sub,
                "Sales Body": sales_body, "Sales Sent At": sent_at,
            })

    _last_delay = [0.0]
    def _human_delay():
        base = random.gauss(82.5, 18.75)
        base = max(45.0, min(120.0, base))
        delay = base + base * random.uniform(-0.15, 0.15)
        if random.random() < 0.10:
            delay = random.uniform(90, 180)
        while abs(delay - _last_delay[0]) < 5.0:
            delay += random.uniform(3, 15)
        _last_delay[0] = delay
        return round(delay, 1)

    try:
        from datetime import datetime, timezone
        for i, prospect in enumerate(targets):
            if _sales_cancel_flag:
                _log("Campaign cancelled by user.")
                _sales_state["status"] = "cancelled"
                return

            email    = prospect.get("Email", "").strip()
            name     = prospect.get("Name", "").strip()
            orig_sub = prospect.get("Subject", "").strip()
            _sales_state["current_lead"] = f"{name or email} <{email}>"

            if not email:
                _log(f"[{i+1}/{_sales_state['total']}] Skipped: empty email row")
                _sales_state["skipped"] += 1
                continue

            _log(f"[{i+1}/{_sales_state['total']}] {name or email} <{email}>")

            # Generate
            try:
                _log(f"  → Generating AI email...")
                subject, body = await _gen_email(name, email, orig_sub)
                _log(f"  → Subject: {subject[:70]}")
            except Exception as e:
                _log(f"  ✗ AI failed: {e}")
                _sales_state["failed"] += 1
                continue

            # Send
            try:
                _log(f"  → Sending from {SALES_SENDER_EMAIL}...")
                await _send(email, subject, body)
                sent_at = datetime.now(timezone.utc).isoformat()
                _log(f"  ✓ Sent! Moving to sale_sent_history.csv")
                _sales_state["sent"] += 1
                _remove_from_sent(email)
                _append_sale_sent(email, name, orig_sub, subject, body, sent_at)
                # ── Register in sent_history so future campaigns skip this contact ──
                try:
                    from services.history_service import register_sent_email
                    register_sent_email(email=email, name=name, subject=subject, body=body)
                except Exception as e_hist:
                    _log(f"  ⚠ History register failed (non-fatal): {e_hist}")
            except Exception as e:
                err_msg = str(e)
                _log(f"  ✗ Send failed: {err_msg}")
                _sales_state["failed"] += 1
                if "Cannot send to" in err_msg or "Role-based" in err_msg or "Disposable" in err_msg:
                    _log(f"  → Removing invalid contact from sent_history.csv")
                    _remove_from_sent(email)
                continue

            # Humanized delay
            if i < len(targets) - 1 and not _sales_cancel_flag:
                delay = _human_delay()
                _log(f"  ⏱ Next send in {delay}s...")
                elapsed = 0.0
                while elapsed < delay:
                    if _sales_cancel_flag:
                        break
                    await asyncio.sleep(1.0)
                    elapsed += 1.0

        if _sales_cancel_flag:
            _sales_state["status"] = "cancelled"
        else:
            _sales_state["status"] = "completed"
            _log(f"Campaign complete — Sent: {_sales_state['sent']}, Failed: {_sales_state['failed']}, Skipped: {_sales_state['skipped']}")

    except Exception as e:
        _log(f"Fatal error: {e}")
        _sales_state["status"] = "failed"
    finally:
        _sales_state["current_lead"] = None


@app.post("/sales/cancel", tags=["Sales Campaign"])
async def cancel_sales_campaign():
    """Cancel the running sales campaign."""
    global _sales_cancel_flag
    _sales_cancel_flag = True
    return {"status": "cancelling", "message": "Cancel signal sent."}


@app.get("/sales/history", tags=["Sales Campaign"])
async def get_sales_history():
    """Return the sale_sent_history.csv records as JSON."""
    csv_path = "sale_sent_history.csv"
    if not os.path.exists(csv_path):
        return {"records": [], "total": 0}
    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            records.append(dict(row))
    return {"records": records, "total": len(records)}


# ── Google Sheets Campaign Endpoints ─────────────────────────────────────────

import re as _re
import urllib.parse as _urlparse


def _sheet_url_to_csv_export(url: str) -> str:
    """
    Convert any Google Sheets share/edit URL into a direct CSV export URL.

    Supports:
      - https://docs.google.com/spreadsheets/d/{ID}/edit#gid=0
      - https://docs.google.com/spreadsheets/d/{ID}/pub?...
      - https://docs.google.com/spreadsheets/d/{ID}  (bare)

    Returns the export URL, e.g.:
      https://docs.google.com/spreadsheets/d/{ID}/export?format=csv&gid={gid}
    """
    # Extract spreadsheet ID
    match = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(
            "Invalid Google Sheets URL — could not find spreadsheet ID. "
            "Make sure the URL looks like: https://docs.google.com/spreadsheets/d/YOUR_ID/..."
        )
    sheet_id = match.group(1)

    # Extract gid (tab id) if present
    gid_match = _re.search(r"[?&#]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"

    export_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )
    return export_url


from pydantic import BaseModel as _BaseModel

class SheetCampaignRequest(_BaseModel):
    sheet_url: str                                       # Google Sheets share link
    limit: Optional[int] = None                          # Max emails to send (None = all)
    mode: CampaignMode = CampaignMode.dry_run
    delay_seconds: int = 60
    min_lead_score: Optional[int] = None
    priority_filter: Optional[str] = None
    sort_by_score: bool = True


@app.post("/campaign/from-sheet", tags=["Campaign"])
async def run_campaign_from_sheet(
    request: SheetCampaignRequest,
    background_tasks: BackgroundTasks,
):
    """
    Launch an AI outreach campaign by pulling leads directly from a Google Sheet.

    The sheet must be publicly shared ("Anyone with the link can view").
    It will be fetched as CSV, de-duplicated against sent_history.json,
    sliced to `limit` contacts, then run through the full AI + SMTP pipeline
    from contact@nexariza.com.

    After the campaign finishes, the session metadata is saved so
    GET /campaign/last-session can report how many were sent last time.
    """
    global _campaign_state

    if _campaign_state["status"] == "running":
        raise HTTPException(status_code=400, detail="A campaign is already running.")

    # ── Convert sheet URL → CSV export URL ──────────────────────────────────
    try:
        csv_export_url = _sheet_url_to_csv_export(request.sheet_url)
        logger.info(f"[Sheets] Fetching CSV from: {csv_export_url}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── Fetch CSV from Google Sheets ─────────────────────────────────────────
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(csv_export_url)

        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Google Sheets access denied (HTTP {response.status_code}). "
                    "Make sure the sheet is shared publicly: "
                    "In Google Sheets click 'Share' → Under 'General access' select 'Anyone with the link' (Viewer)."
                ),
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch Google Sheet (HTTP {response.status_code}).",
            )

        csv_text = response.text
        if "<!DOCTYPE html" in csv_text[:200] or "<html" in csv_text[:200].lower():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Google returned a sign-in web page instead of CSV data. "
                    "Please check your Google Sheet sharing settings: "
                    "Click 'Share' (top-right) → Change 'Restricted' to 'Anyone with the link' → Viewer."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Network error fetching sheet: {e}")

    # ── Parse CSV into ClientInput objects directly in memory ────────────────
    try:
        raw_clients = parse_clients_from_csv_text(csv_text)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse sheet as CSV: {e}")

    if not raw_clients:
        raise HTTPException(
            status_code=400,
            detail=(
                "No valid leads with email addresses found in the sheet. "
                "Ensure your sheet has an 'Email' or 'Direct Email' column and contains rows."
            ),
        )

    total_in_sheet = len(raw_clients)
    logger.info(f"[Sheets] Parsed {total_in_sheet} leads from sheet.")

    # ── Fast De-duplicate against sent history (O(1) set lookup) ────────────
    try:
        from services.history_service import get_all_sent_emails
        all_sent = get_all_sent_emails()
        known_emails = {str(e).strip().lower() for e in all_sent.keys()}
        already_sent = [c for c in raw_clients if c.email.strip().lower() in known_emails]
        new_leads = [c for c in raw_clients if c.email.strip().lower() not in known_emails]
    except Exception as e:
        logger.warning(f"[Sheets] History check failed, proceeding without dedup: {e}")
        already_sent = []
        new_leads = raw_clients

    logger.info(
        f"[Sheets] {len(new_leads)} new leads (not yet emailed), "
        f"{len(already_sent)} already in sent history."
    )

    # ── Sort + filter ─────────────────────────────────────────────────────────
    clients = sort_and_filter_clients(
        new_leads,
        sort_by_score=request.sort_by_score,
        min_lead_score=request.min_lead_score,
        priority_filter=request.priority_filter,
    )

    if not clients:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No new leads to send after filtering. "
                f"Sheet has {total_in_sheet} rows, {len(already_sent)} already emailed."
            ),
        )

    # ── Apply user-specified limit ────────────────────────────────────────────
    if request.limit is not None and request.limit > 0:
        clients = clients[: request.limit]
        logger.info(f"[Sheets] Applying limit={request.limit} → {len(clients)} leads queued.")

    # ── Save sheet URL for session tracking (pre-run) ─────────────────────────
    _pending_session_sheet_url = request.sheet_url

    # ── Launch background campaign ────────────────────────────────────────────
    async def _run_and_save_session():
        await run_campaign_background_task(
            mode=request.mode,
            clients=clients,
            delay_seconds=request.delay_seconds,
        )
        # After campaign completes, persist session metadata
        try:
            from services.session_service import save_session
            sent = _campaign_state.get("sent", 0)
            skipped = _campaign_state.get("skipped", 0)
            total = _campaign_state.get("total", 0)
            save_session(
                sheet_url=request.sheet_url,
                sent_count=sent,
                total_leads=total,
                skipped_count=skipped,
                mode=request.mode.value,
            )
            logger.info(f"[Session] Saved post-campaign session: {sent} sent.")
        except Exception as e:
            logger.error(f"[Session] Failed to save session after campaign: {e}")

    background_tasks.add_task(_run_and_save_session)

    return {
        "status": "started",
        "mode": request.mode.value,
        "sheet_url": request.sheet_url,
        "total_in_sheet": total_in_sheet,
        "already_emailed": len(already_sent),
        "new_leads_found": len(new_leads),
        "queued_for_sending": len(clients),
        "message": (
            f"Campaign launched! {len(clients)} lead(s) queued from Google Sheet "
            f"({len(already_sent)} already emailed contacts skipped)."
        ),
    }


@app.get("/campaign/last-session", tags=["Campaign"])
async def get_last_session():
    """
    Returns metadata about the last campaign run (sheet URL, sent count, timestamp).
    Used by the frontend to pre-fill 'how many did we send last time?'.
    Returns null fields if no session has been saved yet.
    """
    try:
        from services.session_service import load_session
        session = load_session()
        if not session:
            return {
                "has_session": False,
                "sheet_url": None,
                "sent_count": 0,
                "total_leads": 0,
                "skipped_count": 0,
                "mode": None,
                "timestamp": None,
                "message": "No previous campaign session found.",
            }
        return {
            "has_session": True,
            **session,
            "message": (
                f"Last campaign: sent {session.get('sent_count', 0)} emails "
                f"on {session.get('timestamp', 'unknown date')}."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/campaign/last-session", tags=["Campaign"])
async def clear_last_session():
    """Clear the saved session history (for testing or reset)."""
    try:
        from services.session_service import clear_session
        clear_session()
        return {"message": "Session cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# ── Bounce Management Endpoints ───────────────────────────────────────────────

@app.get("/bounces", tags=["Bounces"])
async def list_bounces():
    """
    Return all hard-bounced email addresses.
    These are automatically skipped in every future campaign.
    """
    from services.history_service import get_all_bounced_emails
    bounced = get_all_bounced_emails()
    return {
        "total": len(bounced),
        "bounces": [
            {"email": email, **details}
            for email, details in sorted(bounced.items(), key=lambda x: x[1].get("bounced_at", ""), reverse=True)
        ],
    }


@app.post("/bounces", tags=["Bounces"])
async def add_bounce(email: str, name: str = "", reason: str = "Manually added"):
    """
    Manually register a hard bounce for an email address.
    Useful for addresses that bounced outside of a campaign (e.g. you noticed it in your inbox).
    """
    from services.history_service import register_bounce
    register_bounce(email=email, name=name, reason=reason)
    return {"message": f"'{email}' added to bounce list.", "reason": reason}


@app.delete("/bounces/{email}", tags=["Bounces"])
async def remove_bounce_entry(email: str):
    """
    Remove an email address from the hard-bounce blocklist.
    Use this if an address was incorrectly bounced or has been corrected.
    """
    from services.history_service import remove_bounce
    removed = remove_bounce(email)
    if removed:
        return {"message": f"'{email}' removed from bounce list."}
    raise HTTPException(status_code=404, detail=f"'{email}' not found in bounce list.")


@app.post("/bounces/scan", tags=["Bounces"])
async def scan_inbox_for_bounces():
    """
    Immediately scan the IMAP inbox for bounce (mailer-daemon) emails
    and register any hard-bounced addresses found.
    Returns how many new bounces were detected.
    """
    from services.history_service import register_bounce, get_all_bounced_emails
    from services.incoming_email_service import (
        get_imap_config, clean_header, parse_sender_email,
        get_email_body, _extract_bounced_address, _extract_bounce_reason,
    )
    import imaplib as _imaplib
    import email as _email

    config = get_imap_config()
    if not config["email"] or not config["password"]:
        raise HTTPException(status_code=503, detail="IMAP credentials not configured.")

    new_bounces = []
    errors = []

    def _scan():
        results = []
        errs = []
        try:
            mail = _imaplib.IMAP4_SSL(config["server"], config["port"])
            mail.login(config["email"], config["password"])
            mail.select("INBOX")
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                mail.close(); mail.logout()
                return results, errs

            for num in messages[0].split():
                _, data = mail.fetch(num, "(RFC822)")
                if not data or not data[0]:
                    continue
                raw = data[0][1]
                msg = _email.message_from_bytes(raw)
                from_hdr = clean_header(msg.get("From", ""))
                _, sender_email = parse_sender_email(from_hdr)
                sender_lower = sender_email.lower()
                is_bounce = (
                    "mailer-daemon" in sender_lower
                    or "postmaster" in sender_lower
                    or "delivery" in sender_lower
                )
                if not is_bounce:
                    continue
                mail.store(num, "+FLAGS", "\\Seen")
                subject = clean_header(msg.get("Subject", ""))
                body = get_email_body(msg)
                failed = _extract_bounced_address(body, subject)
                if failed:
                    reason = _extract_bounce_reason(body, subject)
                    results.append({"email": failed, "reason": reason})
            mail.close(); mail.logout()
        except Exception as e:
            errs.append(str(e))
        return results, errs

    import asyncio
    loop = asyncio.get_event_loop()
    found, errs = await loop.run_in_executor(None, _scan)
    errors.extend(errs)

    for item in found:
        register_bounce(email=item["email"], reason=item["reason"])
        new_bounces.append(item)

    return {
        "scanned": True,
        "new_bounces_detected": len(new_bounces),
        "bounces": new_bounces,
        "errors": errors,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

