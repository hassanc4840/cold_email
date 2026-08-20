from pydantic import BaseModel, EmailStr
from typing import Optional, List
from enum import Enum


class CampaignMode(str, Enum):
    live = "live"
    dry_run = "dry_run"


class PriorityLevel(str, Enum):
    """Enum for campaign priority sorting."""
    high = "High"
    medium = "Medium"
    low = "Low"


# ── Request Models ──────────────────────────────────────────────────────────

class ClientInput(BaseModel):
    # ── Core Contact ─────────────────────────────────
    name: str                                          # Primary Contact full name
    email: str                                         # Verified Email (used by email_service)
    website: Optional[str] = None                      # Company website URL (scraped for context)

    # ── Company Profile ──────────────────────────────
    company_name: Optional[str] = None                 # Official company/business name
    industry: Optional[str] = None                     # Sector (e.g. SaaS, Retail, FinTech)
    city: Optional[str] = None                         # HQ City
    state: Optional[str] = None                        # HQ State/Region
    employees: Optional[str] = None                    # Team size (e.g. "50-200")
    revenue: Optional[str] = None                      # Annual revenue range
    ceo: Optional[str] = None                          # CEO name (for executive-level targeting)

    # ── Contact Details ──────────────────────────────
    title: Optional[str] = None                        # Contact's job title (e.g. CTO, VP Ops)
    phone: Optional[str] = None                        # Direct phone number
    linkedin: Optional[str] = None                     # LinkedIn profile URL

    # ── AI Intelligence ──────────────────────────────
    website_quality: Optional[str] = None              # Website score/rating
    ai_readiness: Optional[str] = None                 # AI adoption readiness (Low/Med/High)
    lead_score: Optional[int] = None                   # Lead quality score 1–100
    buying_intent: Optional[str] = None                # Purchase signal (High/Medium/Low)

    # ── Strategic Intel ──────────────────────────────
    problem_statement: Optional[str] = None            # Key pain point — the email HOOK
    recommended_ai_solution: Optional[str] = None      # Nexariza AI product recommendation
    recommended_web_solution: Optional[str] = None     # Nexariza Web product recommendation

    # ── Deal Intel ───────────────────────────────────
    estimated_project_value: Optional[str] = None      # Projected deal size ($)
    estimated_timeline: Optional[str] = None           # Conversion timeline
    priority: Optional[str] = None                     # High / Medium / Low
    notes: Optional[str] = None                        # Free-form observations


class CampaignRequest(BaseModel):
    csv_path: Optional[str] = "clients.csv"
    mode: CampaignMode = CampaignMode.dry_run
    delay_seconds: int = 60                            # Anti-spam delay between emails
    smtp_config: Optional[dict] = None
    min_lead_score: Optional[int] = None               # Filter: skip leads below this score
    priority_filter: Optional[str] = None             # Filter: only process this priority level
    sort_by_score: bool = True                         # Sort leads by Lead Score desc before sending


class BatchCampaignRequest(BaseModel):
    clients: List[ClientInput]
    mode: CampaignMode = CampaignMode.dry_run
    delay_seconds: int = 60
    smtp_config: Optional[dict] = None
    sort_by_score: bool = True                         # Sort leads by Lead Score desc before sending
    min_lead_score: Optional[int] = None               # Filter: skip leads below this score
    priority_filter: Optional[str] = None             # Filter: only this priority level


class SingleClientRequest(BaseModel):
    client: ClientInput
    mode: CampaignMode = CampaignMode.dry_run


# ── Response Models ─────────────────────────────────────────────────────────

class ClientResult(BaseModel):
    name: str
    email: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    lead_score: Optional[int] = None
    priority: Optional[str] = None
    buying_intent: Optional[str] = None
    website_scraped: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    status: str          # "sent" | "previewed" | "failed" | "skipped"
    error: Optional[str] = None


class CampaignResponse(BaseModel):
    mode: CampaignMode
    total: int
    sent: int
    failed: int
    skipped: int
    results: List[ClientResult]


class AnalyzeClientResponse(BaseModel):
    client: ClientInput
    website_content_preview: Optional[str] = None
    generated_subject: str
    generated_body: str
    status: str


class EmailVerificationRequest(BaseModel):
    email: str


class EmailVerificationResponse(BaseModel):
    email: str
    is_valid: bool
    status: str          # "deliverable" | "undeliverable" | "catch_all" | "unknown"
    reason: str
    syntax_valid: bool
    dns_valid: bool
    mx_records: List[str]
    smtp_checked: bool
    mailbox_exists: bool
    is_catch_all: bool
    is_disposable: bool
    is_role_based: bool
    is_free: bool
    # SMTP ping metadata — which port/method was used
    smtp_port_used: Optional[int] = None   # 25 | 587 | None (if unreachable)
    smtp_method: Optional[str] = None      # "port25" | "port587_starttls" | "none"


class CampaignStatusResponse(BaseModel):
    status: str          # "idle" | "running" | "completed" | "cancelled" | "failed"
    mode: Optional[CampaignMode] = None
    total: int = 0
    processed: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    results: List[ClientResult] = []
    current_lead: Optional[str] = None


class SpamCheckRequest(BaseModel):
    subject: str
    body: str


class SpamCheckResponse(BaseModel):
    is_clean: bool
    warnings: List[str]
    spam_score: int
    cleaned_subject: str
    cleaned_body: str


# ── Internship Offer Letter & ID Card Models ────────────────────────────────

class InternInput(BaseModel):
    name: str
    email: str
    role: Optional[str] = "Software Engineering Intern"
    department: Optional[str] = "Engineering & AI"
    start_date: Optional[str] = "September 1, 2026"
    duration: Optional[str] = "3 Months"
    location: Optional[str] = "Remote / Hybrid"
    intern_id: Optional[str] = None
    phone: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    experience: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    skills: Optional[str] = None
    availability: Optional[str] = None
    salary_exp: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    additional_notes: Optional[str] = None


class InternshipConfigRequest(BaseModel):
    company_name: str = "Nexariza AI Technologies"
    hr_name: str = "Ahmad Yasin"
    hr_title: str = "Founder & CEO"
    hr_email: str = "contact@nexariza.com"
    custom_note: Optional[str] = "We are thrilled to welcome you to our innovation team!"


class InternshipSingleRequest(BaseModel):
    intern: InternInput
    config: Optional[InternshipConfigRequest] = None
    mode: CampaignMode = CampaignMode.dry_run


class InternshipBatchRequest(BaseModel):
    interns: List[InternInput]
    config: Optional[InternshipConfigRequest] = None
    mode: CampaignMode = CampaignMode.dry_run
    delay_seconds: int = 10


class InternshipResult(BaseModel):
    intern_id: str
    name: str
    email: str
    role: str
    status: str          # "sent" | "previewed" | "failed" | "skipped"
    application_type: Optional[str] = "internship_offer"  # "internship_offer" | "job_response"
    subject: Optional[str] = None
    error: Optional[str] = None


