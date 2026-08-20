# 🚀 Nexariza AI Outreach System

> **Automated cold email campaigns powered by Groq & Gemini AI.**
> Scrapes client websites, detects operational flaws, generates hyper-personalized pitches, and sends them via SMTP — all from a single API.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61dafb?logo=react)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8-646cff?logo=vite)](https://vitejs.dev)

---

## 📖 Table of Contents

1. [What Is Nexariza?](#-what-is-nexariza)
2. [System Architecture](#-system-architecture)
3. [Project Structure](#-project-structure)
4. [Technology Stack](#-technology-stack)
5. [Environment Setup](#-environment-setup)
6. [Installation & Running](#-installation--running)
7. [Core Pipeline](#-core-pipeline)
8. [Services Deep-Dive](#-services-deep-dive)
9. [Data Models](#-data-models)
10. [API Endpoints Reference](#-api-endpoints-reference)
11. [Frontend (React + Vite)](#-frontend-react--vite)
12. [CSV Lead Format](#-csv-lead-format)
13. [Campaign Modes](#-campaign-modes)
14. [Lead Filtering & Sorting](#-lead-filtering--sorting)
15. [Anti-Spam & Safety Features](#-anti-spam--safety-features)
16. [Email Verification System](#-email-verification-system)
17. [AI Auto-Responder](#-ai-auto-responder)
18. [Sent History & Duplicate Prevention](#-sent-history--duplicate-prevention)
19. [Branded HTML Email Template](#-branded-html-email-template)
20. [File Descriptions](#-file-descriptions)

---

## 🧠 What Is Nexariza?

Nexariza is a **workflow automation and AI solutions company** that helps businesses reduce manual processes, improve efficiency, and scale operations using smart automation pipelines, AI agents, and custom software integrations.

This repository is the **internal AI outreach system** — a full-stack application that:

- **Reads** a structured CSV list of business leads
- **Scrapes** each lead's website for context (homepage + /about, /services, /pricing, /contact)
- **Analyzes** the site for operational flaws using rule-based + AI scanning
- **Generates** a unique, hyper-personalized cold email using Groq (llama3) or Gemini 2.0 Flash as fallback
- **Validates** email addresses via DNS MX + deep SMTP checks
- **Sends** branded HTML emails via SMTP (Zoho Mail)
- **Tracks** all sent emails and prevents duplicate outreach
- **Auto-replies** to incoming prospect replies using AI

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        React Frontend (Vite)                        │
│           Campaign Dashboard · Lead Viewer · Status Monitor         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP (REST)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend  (main.py)                        │
│   /campaign/run  ·  /campaign/status  ·  /client/analyze  · etc.   │
└──────┬──────────┬───────────┬────────────┬────────────┬─────────────┘
       │          │           │            │            │
       ▼          ▼           ▼            ▼            ▼
  ┌─────────┐ ┌────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐
  │Scraper  │ │ Flaw   │ │ Groq / │ │  Email  │ │ History  │
  │Service  │ │Analyzer│ │ Gemini │ │ Service │ │ Service  │
  │(httpx + │ │(AI +   │ │ Service│ │(SMTP +  │ │(JSON +   │
  │ BS4)    │ │ rules) │ │(LLM)   │ │ HTML)   │ │ CSV log) │
  └─────────┘ └────────┘ └────────┘ └─────────┘ └──────────┘
```

---

## 📁 Project Structure

```
nexariza/
│
├── main.py                        # FastAPI application & all API routes
├── requirements.txt               # Python dependencies
├── .env                           # API keys, SMTP config, company description
├── clients.csv                    # Lead database (input)
├── sent_history.json              # All-time sent email registry (JSON)
├── sent_history.csv               # Sent email log (CSV export)
├── email_preview.html             # Sample rendered HTML email
│
├── models/
│   ├── __init__.py
│   └── schemas.py                 # Pydantic data models (request/response)
│
├── services/
│   ├── __init__.py
│   ├── scraper_service.py         # Website scraper (httpx + BeautifulSoup)
│   ├── flaw_analyzer.py           # AI-powered website flaw detection
│   ├── gemini_service.py          # Groq/Gemini LLM email generation
│   ├── email_service.py           # SMTP send, HTML builder, email verification
│   ├── history_service.py         # Sent history tracking & duplicate prevention
│   └── incoming_email_service.py  # IMAP inbox polling & AI auto-reply
│
├── frontend/
│   ├── index.html
│   ├── package.json               # React 19 + Vite 8 dependencies
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx               # App entry point
│       ├── App.jsx                # Main dashboard UI
│       ├── App.css                # Component styles
│       └── index.css              # Global styles
│
├── OmniRoute/                     # Bundled OmniRoute SDK (upstream library)
│
├── nexariza_app.py                # Standalone app (early version)
├── nexariza_app_enhanced.py       # Enhanced standalone app (intermediate version)
├── patch_email.py                 # Email patching utility
├── run_campaign.py                # CLI campaign runner script
├── send_outreach.py               # CLI outreach sender script
└── find_lines.py                  # Utility script
```

---

## 🛠️ Technology Stack

### Backend

| Layer | Technology | Purpose |
|---|---|---|
| Web Framework | **FastAPI** | REST API with async support |
| ASGI Server | **Uvicorn** | High-performance Python server |
| AI (Primary) | **Groq API** (llama3-8b-8192) | LLM email generation |
| AI (Fallback) | **Google Gemini 2.0 Flash** | Backup LLM when Groq fails |
| Web Scraping | **httpx + BeautifulSoup4** | Async website fetching & parsing |
| Email Send | **aiosmtplib + smtplib** | Async SMTP email dispatch |
| Email Validation | **email-validator + dnspython** | Syntax + DNS + MX validation |
| Data Validation | **Pydantic v2** | Request/response schemas |
| Config | **python-dotenv** | .env file loading |
| Caching | **cachetools (TTLCache)** | DNS result caching |
| Concurrency | **asyncio** | Async I/O for scraping & sending |

### Frontend

| Layer | Technology | Purpose |
|---|---|---|
| UI Framework | **React 19** | Component-based dashboard UI |
| Build Tool | **Vite 8** | Fast dev server & bundler |
| Styling | **Vanilla CSS** | Custom dark-mode dashboard styles |
| HTTP Client | **Fetch API** | Backend communication |
| Linting | **oxlint** | Fast Rust-based linter |

---

## ⚙️ Environment Setup

All secrets and configuration live in `.env` at the project root:

```env
# Groq API Keys (Primary → Fallback 2 → Fallback 3)
GROQ_API_KEY=gsk_...
GROQ_API_KEY_2=gsk_...
GROQ_API_KEY_3=gsk_...

# Google Gemini API Keys (used if ALL Groq keys fail)
GOOGLE_API_KEY=AQ.Ab8...
GOOGLE_API_KEY_2=AQ.Ab8...
GOOGLE_API_KEY_3=AQ.Ab8...

# SMTP Configuration (Zoho Mail)
SMTP_SERVER=smtp.zoho.com
SMTP_PORT=465
SENDER_EMAIL=contact@nexariza.com
SENDER_PASSWORD=your_password

# Optional IMAP (for auto-responder — auto-derived from SMTP if not set)
IMAP_SERVER=imap.zoho.com
IMAP_PORT=993

# Company description (injected into every AI prompt)
NEXARIZA_DESCRIPTION=Nexariza is a workflow automation and AI solutions company...
```

> ⚠️ Never commit `.env` to version control. It is already listed in `.gitignore`.

---

## 📦 Installation & Running

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)

### Backend

```bash
# 1. Clone the repository and navigate to the folder
cd nexariza

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Configure your .env file (see above)

# 4. Start the FastAPI server
uvicorn main:app --reload

# API will be live at:  http://127.0.0.1:8000
# Swagger Docs:         http://127.0.0.1:8000/docs
# ReDoc:                http://127.0.0.1:8000/redoc
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Dashboard at: http://localhost:5173
```

---

## ⚡ Core Pipeline

When a campaign runs, every lead goes through this exact pipeline:

```
Lead (from CSV / API)
        │
        ▼
1. ── Duplicate Check ──────────────────────────────────────────────
   Is this email already in sent_history.json?
   YES → status: "skipped"       NO → continue
        │
        ▼
2. ── Domain MX Validation ─────────────────────────────────────────
   Does the email domain have valid MX records?
   NO → status: "skipped"        YES → continue
        │
        ▼
3. ── Website Scraping ─────────────────────────────────────────────
   Fetch homepage + /about + /services (up to 3 pages, async)
   Extracts: page title, meta description, visible body text
   Falls back gracefully if site is unreachable
        │
        ▼
4. ── Flaw Analysis ────────────────────────────────────────────────
   Rule-based scan: manual processes, outdated site, no live chat...
   AI scan (Groq): 3-5 specific operational weaknesses identified
   Produces urgency level: High / Medium / Low
        │
        ▼
5. ── AI Email Generation ──────────────────────────────────────────
   Groq llama3-8b-8192 (primary) or Gemini 2.0 Flash (fallback)
   Injected with: all CSV lead intel + scraped content + flaw report
   Output: personalized subject line + email body
        │
        ▼
6. ── Send / Preview ───────────────────────────────────────────────
   DRY RUN → status: "previewed" (no email sent)
   LIVE    → send via SMTP → status: "sent" or "failed"
        │
        ▼
7. ── History Registration ─────────────────────────────────────────
   Register email in sent_history.json + sent_history.csv
   Prevents this address from being contacted again
```

---

## 🔧 Services Deep-Dive

### 1. Scraper Service
**File:** `services/scraper_service.py`

Asynchronously fetches client websites to gather personalization context.

**Key behaviours:**
- Uses a realistic browser `User-Agent` header to avoid bot blocks
- Always scrapes the **homepage first**, then tries extra paths concurrently: `/about`, `/about-us`, `/services`, `/contact`, `/pricing`
- Caps at **3 pages total** (1 homepage + 2 extra) to stay fast
- Strips noise tags: `<script>`, `<style>`, `<nav>`, `<svg>`, `<form>`, `<aside>`
- Extracts `<title>`, `<meta name="description">`, and visible body text
- Skips scraping for free/personal email domains (Gmail, Yahoo, Outlook, etc.)
- Returns both `web_content` (clean text) and `html_raw` (raw HTML for flaw detection)
- Handles timeouts gracefully (8s per page, 12s total client timeout)

---

### 2. Flaw Analyzer Service
**File:** `services/flaw_analyzer.py`

Identifies specific operational weaknesses in a client's website to create hyper-targeted email hooks.

**Two-stage analysis:**

**Stage 1 — Rule-based scan (instant, no API cost):**

| Signal Type | Keywords Detected |
|---|---|
| Manual intake process | "call us to", "fill out", "phone only", "no online booking" |
| Outdated website | "copyright 2018/2019/2020", "© 2018" |
| Slow response | "within 24-48 hours", "we will contact you shortly" |
| No live chat | Absence of: livechat, intercom, drift, tawk, crisp, zendesk |
| No analytics | Absence of: google-analytics, gtag, segment, mixpanel |
| No SSL/mobile | Missing https://, missing viewport meta tag |

**Stage 2 — AI scan (Groq/Gemini):**
Sends the scraped content to the LLM asking it to identify 3–5 specific, actionable flaws Nexariza can solve. Output is JSON-parsed into a `WebsiteFlawReport`.

```python
@dataclass
class WebsiteFlawReport:
    url: str
    flaws: List[str]           # 3-5 specific detected flaws
    summary: str               # 1-sentence hook for the email opener
    automation_gaps: List[str] # Specific automation opportunities
    urgency_level: str         # "High" | "Medium" | "Low"
```

---

### 3. Gemini / Groq Service
**File:** `services/gemini_service.py`

Generates the personalized subject line and email body using LLMs with automatic key failover.

**AI Client Pool (Priority Order):**
```
GROQ_API_KEY (primary)
  → GROQ_API_KEY_2 (fallback)
    → GROQ_API_KEY_3 (fallback)
      → GOOGLE_API_KEY (Gemini, last resort)
        → GOOGLE_API_KEY_2
          → GOOGLE_API_KEY_3
```

Adding a new key only requires adding it to `.env` — no code changes needed.

**Models used:**
- **Groq:** `llama3-8b-8192` — fast, high quality, low cost
- **Gemini:** `gemini-2.0-flash` — used when all Groq keys fail

**Two generation functions:**
1. `generate_outreach_email()` — cold outreach email generation with all 20+ lead fields + flaw report injected
2. `generate_reply_email()` — contextual reply generation for the AI auto-responder

---

### 4. Email Service
**File:** `services/email_service.py`

Handles all outgoing email delivery, HTML wrapping, and email verification.

| Function | Description |
|---|---|
| `send_email()` | Async SMTP send via aiosmtplib with SSL |
| `build_html_email()` | Wraps plain-text body in branded Nexariza HTML |
| `test_smtp_connection()` | Validates SMTP credentials (used by `/health`) |
| `get_smtp_config()` | Loads SMTP settings from environment |
| `validate_email_domain()` | DNS MX record check (async, cached) |
| `analyze_email()` | Full syntax + DNS + disposable/role-based analysis |
| `verify_email_deep()` | Deep SMTP handshake verification |

**Email classification built-in:**
- **Role-based prefixes** flagged: `admin@`, `info@`, `support@`, `sales@`, `marketing@`
- **Disposable domains** blocked: mailinator, 10minutemail, yopmail, guerrillamail, etc.
- **Free email domains** identified: Gmail, Yahoo, Outlook, Hotmail, ProtonMail, etc.

---

### 5. History Service
**File:** `services/history_service.py`

Maintains a persistent record of all sent emails and auto-replies.

**Storage:** `sent_history.json` (primary) + `sent_history.csv` (secondary export)

```json
{
  "sent_emails": {
    "john@company.com": {
      "name": "John Smith",
      "subject": "Automating Acme Corp's...",
      "body": "Hi John, I noticed...",
      "sent_at": "2026-01-15T10:30:00Z"
    }
  },
  "processed_replies": ["<message-id-1>"],
  "auto_replies": [{ "recipient": "...", "reply_body": "...", "sent_at": "..." }]
}
```

**Thread safety:** All read/write operations protected by `threading.Lock()`.

---

### 6. Incoming Email Service
**File:** `services/incoming_email_service.py`

Polls the inbox via IMAP every 30 seconds and auto-replies to prospects using AI.

**Flow:**
1. IMAP connects to `imap.zoho.com:993`
2. Fetches all `UNSEEN` emails from `INBOX`
3. For each email: checks if sender is in sent_history (i.e., we reached out to them)
4. If recognized: generates an AI reply and sends it via SMTP
5. Marks `Message-ID` as processed to prevent duplicate replies
6. Logs all auto-replies to `sent_history.json`

> **Note:** The auto-responder starts **disabled** by default. Use `POST /responder/toggle` to activate it.

---

## 📐 Data Models

All Pydantic models in `models/schemas.py`:

### `ClientInput` — Lead Data Model

| Field Group | Fields |
|---|---|
| Core Contact | `name`, `email`, `website` |
| Company Profile | `company_name`, `industry`, `city`, `state`, `employees`, `revenue`, `ceo` |
| Contact Details | `title`, `phone`, `linkedin` |
| AI Intelligence | `website_quality`, `ai_readiness`, `lead_score`, `buying_intent` |
| Strategic Intel | `problem_statement`, `recommended_ai_solution`, `recommended_web_solution` |
| Deal Intel | `estimated_project_value`, `estimated_timeline`, `priority`, `notes` |

### `CampaignRequest` — Run Campaign

```python
{
  "csv_path": "clients.csv",
  "mode": "dry_run",           # "dry_run" | "live"
  "delay_seconds": 60,
  "sort_by_score": true,
  "min_lead_score": 60,        # optional filter
  "priority_filter": "High"    # optional filter
}
```

### `ClientResult` — Per-Lead Outcome

```python
{
  "name": "...",
  "email": "...",
  "lead_score": 85,
  "priority": "High",
  "email_subject": "...",
  "email_body": "...",
  "status": "sent"             # "sent" | "previewed" | "failed" | "skipped"
}
```

### `CampaignStatusResponse` — Real-time Progress

```python
{
  "status": "running",         # "idle"|"running"|"completed"|"cancelled"|"failed"
  "mode": "live",
  "total": 150,
  "processed": 42,
  "sent": 38,
  "failed": 2,
  "skipped": 2,
  "current_lead": "John Smith (john@acme.com)"
}
```

---

## 🌐 API Endpoints Reference

**Base URL:** `http://127.0.0.1:8000`
**Interactive docs:** `/docs` (Swagger) · `/redoc` (ReDoc)

### Info Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | HTML landing page with quick links |
| `GET` | `/health` | API health + SMTP connection status |

### Analysis Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/client/analyze` | Scrape, flaw-detect, and generate email for one lead |

### Campaign Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/campaign/upload` | Upload a new `clients.csv` |
| `POST` | `/campaign/validate-csv` | Validate all emails in a CSV (DNS + SMTP) |
| `POST` | `/campaign/run` | Start a CSV-based campaign in the background |
| `POST` | `/campaign/run_batch` | Start a JSON-based batch campaign in the background |
| `GET` | `/campaign/status` | Poll real-time campaign progress |
| `POST` | `/campaign/cancel` | Cancel the currently running campaign |

### Validation Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/email/verify` | Deep email deliverability check (7-stage) |

### Auto-Responder Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/responder/status` | Is auto-responder active? How many replies sent? |
| `POST` | `/responder/toggle` | Turn auto-responder on or off |
| `POST` | `/responder/check` | Force an immediate manual inbox check |
| `GET` | `/responder/history` | All AI auto-replies sent so far |

---

## 🖥️ Frontend (React + Vite)

**Location:** `frontend/src/App.jsx`

A full-featured single-page dashboard built with React 19 and Vite 8.

**Features:**
- **Campaign Control Panel** — configure mode, delay, filters, and launch campaigns
- **Real-time Status Monitor** — polls `/campaign/status` to show live progress, per-lead results, sent/failed/skipped counts
- **Lead Viewer** — view and manage leads from the uploaded CSV
- **CSV Upload** — drag-and-drop to replace `clients.csv`
- **Email Preview** — view generated email subjects and bodies per lead
- **Campaign Cancel** — abort a running campaign mid-execution
- **Auto-Responder Controls** — toggle inbox monitoring on/off

**Commands:**
```bash
cd frontend
npm install
npm run dev      # Dev server at http://localhost:5173
npm run build    # Production build
npm run lint     # Lint with oxlint
npm run preview  # Preview production build
```

---

## 📊 CSV Lead Format

The system reads leads from `clients.csv`. Column names are flexible — the parser does **case-insensitive fuzzy matching**:

| Field | Accepted Column Names |
|---|---|
| Name | `Decision Maker`, `Primary Contact`, `Full Name` |
| Email | `Direct Email`, `Corporate Email`, `Verified Email`, `Email Address` |
| Website | `Website`, `Website URL` |
| Company | `Company Name` |
| Industry | `Industry`, `sector` |
| City | `Headquarters City`, `HQ City`, `City` |
| Employees | `Employee Size`, `Team Size` |
| Revenue | `Estimated Revenue`, `Annual Revenue` |
| CEO | `CEO`, `Founder`, `Owner` |
| Title | `Decision Maker Position`, `Job Title` |
| Lead Score | `Priority Score (1-100)`, `Lead Score`, `Score` |
| Problem | `Problem Statement`, `Pain Point` |
| AI Solution | `Recommended AI Solution`, `AI Opportunity` |
| Web Solution | `Recommended Web Solution`, `Website Opportunity` |
| Priority | `Priority`, `Buying Intent` |
| Notes | `Notes`, `Reason for Qualification` |

> Rows with a blank email column are automatically skipped.

---

## 🎯 Campaign Modes

| Mode | Behavior | Delay |
|---|---|---|
| `dry_run` | Generates emails but **does NOT send**. Status: `"previewed"` | 2 seconds |
| `live` | Generates AND **sends** emails via SMTP. Status: `"sent"` / `"failed"` | `delay_seconds` (default 60s) |

---

## 🔀 Lead Filtering & Sorting

Before any campaign starts, leads pass through a filter + sort pipeline:

1. **Score Filter** (`min_lead_score`) — removes leads below the threshold (leads with no score are kept)
2. **Priority Filter** (`priority_filter`) — keeps only `"High"` / `"Medium"` / `"Low"` leads
3. **Sort** (`sort_by_score = true`) — sorts by: Priority (High → Medium → Low), then Lead Score (desc)

This ensures the **hottest leads are always contacted first**.

---

## 🛡️ Anti-Spam & Safety Features

| Feature | Details |
|---|---|
| Duplicate check | Email checked against `sent_history.json` before any processing |
| MX validation | Emails with no MX records are skipped (no API calls wasted) |
| Anti-spam delay | Configurable delay (default 60s) between live sends |
| Cancellable | Campaign checks cancel flag before each lead and during sleep |
| DNS concurrency cap | Max 10 concurrent DNS/SMTP lookups via `asyncio.Semaphore(10)` |
| Graceful scrape failure | Campaign continues with domain-only context if scraping fails |
| TTL DNS caching | MX results cached to reduce DNS resolver load |

---

## ✉️ Email Verification System

The `/email/verify` endpoint performs a **7-stage deep check**:

```
Stage 1: Syntax validation        → email-validator library
Stage 2: Disposable domain check  → known disposable domain list
Stage 3: Role-based prefix check  → admin@, info@, support@, etc.
Stage 4: Free email detection     → gmail.com, yahoo.com, etc.
Stage 5: DNS MX lookup            → dnspython async resolver
Stage 6: SMTP handshake           → aiosmtplib EHLO + RCPT TO check
Stage 7: Catch-all detection      → tests random address at same domain
```

**Result classifications:**
- `deliverable` — valid syntax, valid MX, SMTP accepts the mailbox
- `undeliverable` — SMTP rejected or no MX records
- `catch_all` — domain accepts any email address
- `unknown` — SMTP check was inconclusive

---

## 🤖 AI Auto-Responder

The auto-responder watches the inbox and replies to prospects automatically.

**Controls:**
| Endpoint | Action |
|---|---|
| `GET /responder/status` | Is it running? How many replies sent? |
| `POST /responder/toggle` | Turn it on or off |
| `POST /responder/check` | Trigger an immediate check manually |
| `GET /responder/history` | Full list of all AI replies sent |

**How it identifies replies to respond to:**
- Checks if the sender's email exists in `sent_history.json`
- Only auto-replies to people Nexariza has already reached out to
- Marks each `Message-ID` as processed to prevent duplicate replies

---

## 📜 Sent History & Duplicate Prevention

Every sent email is logged in **two formats** for redundancy:

**`sent_history.json`** — primary store:
```json
{
  "sent_emails": { "email@domain.com": { "name": "...", "subject": "...", "sent_at": "..." } },
  "processed_replies": ["<msg-id-1>", "<msg-id-2>"],
  "auto_replies": [{ "recipient": "...", "reply_body": "...", "sent_at": "..." }]
}
```

**`sent_history.csv`** — secondary CSV log for spreadsheet review.

All write operations use `threading.Lock()` to prevent race conditions.

---

## 🎨 Branded HTML Email Template

Every outgoing email is wrapped in a professional Nexariza HTML template:

- Clean white card layout with rounded corners and shadow
- Vivid blue gradient header banner with Nexariza logo
- Body text converted from plain-text to styled HTML paragraphs
- Footer with: Nexariza 3D logo image, website link, email, phone, WhatsApp
- "Automate. Scale. Win." tagline
- Unsubscribe / disclaimer text

The template is built by `build_html_email()` in `services/email_service.py`.
A rendered sample is saved at `email_preview.html`.

---

## 📄 File Descriptions

| File | Description |
|---|---|
| `main.py` | FastAPI app — all routes, campaign orchestration, CSV parsing (907 lines) |
| `requirements.txt` | Python package dependencies |
| `.env` | Secret keys and configuration (never committed) |
| `clients.csv` | Input lead database |
| `sent_history.json` | All-time sent email registry (auto-generated) |
| `sent_history.csv` | CSV export of sent history (auto-generated) |
| `email_preview.html` | Sample rendered branded HTML email |
| `models/schemas.py` | All Pydantic request/response data models |
| `services/scraper_service.py` | Async website scraper (httpx + BeautifulSoup) |
| `services/flaw_analyzer.py` | AI + rule-based website audit engine |
| `services/gemini_service.py` | Groq/Gemini LLM client with multi-key failover |
| `services/email_service.py` | SMTP delivery, HTML template builder, email verification |
| `services/history_service.py` | Sent history tracking (JSON + CSV), duplicate prevention |
| `services/incoming_email_service.py` | IMAP inbox polling + AI auto-reply engine |
| `frontend/src/App.jsx` | Main React dashboard UI |
| `frontend/src/index.css` | Global CSS (dark theme, typography) |
| `nexariza_app.py` | Standalone early-version app (legacy) |
| `nexariza_app_enhanced.py` | Enhanced standalone intermediate version (legacy) |
| `patch_email.py` | One-off email patching utility |
| `run_campaign.py` | CLI script to trigger a campaign without the API |
| `send_outreach.py` | CLI script for direct outreach sending |
| `find_lines.py` | Utility script for file inspection |
| `OmniRoute/` | Bundled OmniRoute SDK (upstream Node.js library) |

---

## 🏢 About Nexariza

**Website:** [nexariza.com](https://nexariza.com)
**Email:** contact@nexariza.com
**Phone / WhatsApp:** +92-370-7348001

Nexariza helps businesses reduce manual processes, improve efficiency, and scale operations using smart automation pipelines, AI agents, and custom software integrations.

---

*Built with ❤️ by the Nexariza team.*
