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
)
from services.scraper_service import get_client_web_context
from services.gemini_service import generate_outreach_email
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

    # ── Duplicate / History Check ────────────────────────────────────────────
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

    # Step 1: Scrape web context
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
        }

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
        )
        result.email_subject = subject
        result.email_body = body
    except Exception as e:
        result.status = "failed"
        result.error = f"Gemini generation failed: {str(e)}"
        logger.error(f"Groq failed for {name} ({email}): {e}")
        return result

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
            # In dry_run, enforce a smaller delay (e.g., 2 seconds) to avoid API rate limits
            actual_delay = delay_seconds if mode == CampaignMode.live else 2.0
            
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


def read_clients_from_csv(csv_path: str) -> List[ClientInput]:
    """Read all 23 CSV columns and return a list of fully-populated ClientInput objects."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    clients = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # ── Core Contact ─────────────────────────────────────────────────
            name    = _csv_get(row, "Decision Maker", "Decision Maker Name", "Primary Contact", "name", "Full Name") or ""
            email   = _csv_get(row, "Direct Email", "Corporate Email", "Business Email", "Verified Email", "email", "Email Address", "Contact Email") or ""
            website = _csv_get(row, "Website", "website", "Website URL")

            if not email.strip():
                continue  # Skip rows with no email

            # Resolve city and state fallbacks
            city = _csv_get(row, "Headquarters City", "HQ City", "City")
            state = _csv_get(row, "State", "HQ State")
            hq = _csv_get(row, "Headquarters", "HQ")
            if hq and not city:
                parts = hq.split(",")
                city = parts[0].strip()
                if len(parts) > 1 and not state:
                    state = parts[1].strip()

            # ── Build full ClientInput with all columns ────────────────────
            client = ClientInput(
                name=name,
                email=email,
                website=website,
                # Company Profile
                company_name         = _csv_get(row, "Company Name", "company"),
                industry             = _csv_get(row, "Industry", "sector"),
                city                 = city,
                state                = state,
                employees            = _csv_get(row, "Employee Size", "Employees", "Team Size"),
                revenue              = _csv_get(row, "Estimated Revenue", "Revenue", "Annual Revenue"),
                ceo                  = _csv_get(row, "CEO", "Chief Executive Officer", "Founder", "Owner"),
                # Contact Details
                title                = _csv_get(row, "Decision Maker Position", "Title", "Position", "Job Title"),
                phone                = _csv_get(row, "Direct Phone", "Business Phone", "Phone Number", "Phone", "Telephone"),
                linkedin             = _csv_get(row, "LinkedIn Profile", "Decision Maker LinkedIn", "LinkedIn", "LinkedIn URL"),
                # AI Intelligence
                website_quality      = _csv_get(row, "Technology Stack", "Website Technology", "Website Quality", "Tech Stack"),
                ai_readiness         = _csv_get(row, "AI Readiness", "AI Adoption"),
                lead_score           = _parse_lead_score(_csv_get(row, "Priority Score (1-100)", "Lead Score", "Score")),
                buying_intent        = _csv_get(row, "Buying Intent", "Intent"),
                # Strategic Intel
                problem_statement    = _csv_get(row, "Problem Statement", "Current Problems", "Problems", "Pain Point"),
                recommended_ai_solution  = _csv_get(row, "Recommended AI Solution", "AI Opportunity", "AI Solution"),
                recommended_web_solution = _csv_get(row, "Recommended Web Solution", "Website Opportunity", "Web Solution"),
                # Deal Intel
                estimated_project_value  = _csv_get(row, "Estimated Project Value", "Project Value", "Value", "Expected ROI"),
                estimated_timeline       = _csv_get(row, "Estimated Timeline", "Timeline"),
                priority                 = _csv_get(row, "Priority", "Buying Intent"),
                notes                    = _csv_get(row, "Notes", "Reason for Qualification", "comments"),
            )
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
async def health_check():
    """Returns API health and SMTP connection status (non-blocking, 5s timeout)."""
    try:
        smtp = await asyncio.wait_for(test_smtp_connection(), timeout=5.0)
    except asyncio.TimeoutError:
        smtp = {"status": "error", "message": "SMTP check timed out after 5s"}
    except Exception as e:
        smtp = {"status": "error", "message": str(e)}
    return {
        "api": "ok",
        "smtp": smtp,
        "gemini_key_set": bool(
            os.getenv("GROQ_API_KEY")
        ),
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
