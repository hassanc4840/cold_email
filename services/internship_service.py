"""
internship_service.py
---------------------
Handles Internship Offer Letter and Intern ID Card generation and delivery.
Features:
- Parses intern CSV data.
- Generates high-end HTML Offer Letters & Futuristic HTML/CSS Intern ID Cards.
- Delivers branded emails with attached downloadable ID Cards.
- Async batch processing with campaign state tracking.
"""

import io
import csv
import logging
import asyncio
import time
import random
from typing import List, Dict, Any, Optional
from models.schemas import InternInput, InternshipConfigRequest, InternshipResult, CampaignMode
from services.email_service import send_email, validate_email_domain

logger = logging.getLogger(__name__)


def get_human_delay(base_seconds: float = 12.0) -> float:
    """
    Calculates a human-like delay with random jitter and micro-variations.
    Ensures natural dispatch cadence to protect sender reputation and prevent anti-spam flag triggers.
    """
    base = max(base_seconds, 10.0)
    # Jitter range: 85% to 145% of base delay
    jitter = random.uniform(0.85, 1.45)
    delay = base * jitter
    # Sub-second decimal variance
    delay += random.uniform(0.2, 2.5)
    return round(delay, 2)

# Global execution state for Internship Offer Letter Batch Sends
_internship_state = {
    "status": "idle",  # "idle" | "running" | "completed" | "cancelled" | "failed"
    "mode": None,
    "total": 0,
    "processed": 0,
    "sent": 0,
    "failed": 0,
    "skipped": 0,
    "results": [],
    "current_intern": None,
}
_cancel_internship_flag = False


def get_internship_state() -> dict:
    return _internship_state


def cancel_internship_campaign():
    global _cancel_internship_flag
    _cancel_internship_flag = True


NEXARIZA_LOGO_URL = "https://nexariza.com/Nexariza%203d%20Logo.webp"


def parse_interns_csv(csv_content: str) -> List[Dict[str, str]]:
    """
    Parses a CSV string of interns with flexible exact and substring header matching.
    Supports Google Forms, Typeform, Excel, and custom CSV column headers.
    Returns a list of dicts with standardized keys:
    name, email, role, department, start_date, duration, location, intern_id
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    interns = []
    
    idx = 1
    for row in reader:
        # Normalize header keys to lowercase stripped strings and spaces
        normalized_row = {}
        for k, v in row.items():
            if k:
                clean_k = k.strip().lower()
                normalized_row[clean_k] = v.strip() if v else ""
                clean_k_space = clean_k.replace("_", " ")
                normalized_row[clean_k_space] = v.strip() if v else ""

        def get_val(keys: List[str], default: str = "") -> str:
            # 1. Exact match lookup
            for k in keys:
                if k in normalized_row and normalized_row[k]:
                    return normalized_row[k]
            # 2. Substring match for Google Forms / long question headers
            for header, val in normalized_row.items():
                if val:
                    for k in keys:
                        if len(k) > 2 and k in header:
                            return val
            return default

        email = get_val([
            "email", "e-mail", "email address", "email_address", "intern email", "intern_email",
            "candidate email", "candidate_email", "mail", "gmail", "address"
        ])
        
        name = get_val([
            "name", "full name", "full_name", "intern name", "intern_name",
            "student name", "student_name", "candidate name", "candidate_name", "applicant name"
        ])

        if not email or not name:
            continue  # Skip invalid rows missing core identity

        # Match Role / Domain / Track / Position / Field / Job-Title
        role = get_val([
            "job-title", "job_title", "job title", "job-title", "job", "job_id",
            "role", "internship role", "intern_role", "internship_role",
            "domain", "internship domain", "intern_domain", "internship_domain",
            "track", "internship track", "intern_track", "internship_track",
            "position", "internship position", "intern_position", "internship_position",
            "applied for", "applied_for", "applied role", "applied_role",
            "profile", "post", "field", "specialization", "course", "technology", "topic"
        ], "Software Engineering Intern")

        # Format role title: preserve exact title from CSV (do not force-append 'Intern' if applicant applied for a job)
        role_lower = role.lower()

        # Department (exclude 'domain' here so it matches role first)
        department = get_val([
            "department", "dept", "team", "division", "unit"
        ])

        # Infer department from role if not explicitly set
        if not department:
            r_lower = role.lower()
            if any(k in r_lower for k in ["ai", "ml", "machine learning", "agentic", "agent", "deep learning", "nlp", "llm"]):
                department = "AI & Machine Learning"
            elif any(k in r_lower for k in ["web", "frontend", "backend", "full stack", "fullstack", "software", "python", "node", "react"]):
                department = "Software Engineering"
            elif any(k in r_lower for k in ["mobile", "android", "ios", "flutter", "react native"]):
                department = "Mobile Development"
            elif any(k in r_lower for k in ["design", "ui", "ux", "product", "figma"]):
                department = "UI/UX & Product Design"
            elif any(k in r_lower for k in ["data", "analytics", "sql", "bi"]):
                department = "Data Science & Analytics"
            elif any(k in r_lower for k in ["cloud", "devops", "aws", "docker"]):
                department = "DevOps & Cloud Engineering"
            else:
                department = "Engineering & AI"

        start_date = get_val(["start_date", "start date", "joining_date", "commencement_date", "created_at", "created at", "date"], "September 1, 2026")
        duration = get_val(["duration", "period", "tenure", "months"], "3 Months")
        location = get_val(["location", "work_type", "type", "mode"], "Remote / Hybrid")
        
        intern_id = get_val(["intern_id", "id", "internship_id", "badge_no"])
        if not intern_id:
            intern_id = f"NEX-2026-INT-{idx:03d}"

        # Extended fields from candidate database export
        phone = get_val(["phone", "phone_number", "contact", "mobile", "phone number"])
        resume_url = get_val(["resume_url", "resume_uri", "resume", "cv", "cv_url", "resume link"])
        cover_letter = get_val(["cover_letter", "cover letter", "cover_letter_text"])
        experience = get_val(["experience", "exp", "years_of_experience", "years of experience"])
        linkedin_url = get_val(["linkedin_url", "linkedin", "linkedin_profile", "linkedin profile"])
        portfolio_url = get_val(["portfolio_url", "portfolio", "github_url", "github", "website"])
        skills = get_val(["skills", "tech_stack", "technologies"])
        availability = get_val(["availability", "available_from"])
        salary_exp = get_val(["salary_exp", "salary_expectation", "salary expectation", "stipend", "expected_salary"])
        status = get_val(["status", "application_status"])
        created_at = get_val(["created_at", "created at", "applied_at", "application_date"])
        additional_notes = get_val(["additional_notes", "additional notes", "notes", "remarks"])

        idx += 1
        interns.append({
            "name": name,
            "email": email,
            "role": role,
            "department": department,
            "start_date": start_date,
            "duration": duration,
            "location": location,
            "intern_id": intern_id,
            "phone": phone,
            "resume_url": resume_url,
            "cover_letter": cover_letter,
            "experience": experience,
            "linkedin_url": linkedin_url,
            "portfolio_url": portfolio_url,
            "skills": skills,
            "availability": availability,
            "salary_exp": salary_exp,
            "status": status,
            "created_at": created_at,
            "additional_notes": additional_notes
        })

    return interns


def build_intern_card_html(intern: Dict[str, str], config: Dict[str, str]) -> str:
    """
    Renders a stunning glassmorphic, futuristic Intern ID Card in HTML/CSS with official Nexariza 3D Logo.
    """
    name = intern.get("name", "Intern Name")
    role = intern.get("role", "Software Engineering Intern")
    dept = intern.get("department", "Engineering & AI")
    intern_id = intern.get("intern_id", "NEX-2026-INT-001")
    company = config.get("company_name", "Nexariza AI Technologies")
    
    # Initials for avatar
    parts = name.split()
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

    return f"""
    <div style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 32px 0;">
      <div style="max-width: 550px; margin: 0 auto; background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%); border-radius: 24px; border: 1px solid rgba(139, 92, 246, 0.5); box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6), 0 0 30px rgba(139, 92, 246, 0.3); overflow: hidden; position: relative;">
        
        <!-- Header Banner with Nexariza Logo -->
        <div style="background: linear-gradient(90deg, #6366f1 0%, #a855f7 50%, #ec4899 100%); padding: 18px 24px; display: flex; align-items: center; justify-content: space-between;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <img src="{NEXARIZA_LOGO_URL}" height="36" style="height: 36px; width: auto; object-fit: contain; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));" alt="Nexariza" />
            <span style="color: #ffffff; font-weight: 800; font-size: 18px; letter-spacing: 0.5px; text-transform: uppercase;">
              {company}
            </span>
          </div>
          <div style="background: rgba(255, 255, 255, 0.25); backdrop-filter: blur(8px); padding: 6px 14px; border-radius: 12px; font-size: 12px; color: #ffffff; font-weight: 800; letter-spacing: 0.5px; white-space: nowrap;">
            VERIFIED INTERN
          </div>
        </div>

        <!-- Main Card Body -->
        <div style="padding: 36px 28px; display: flex; gap: 24px; align-items: center;">
          <!-- Avatar Badge -->
          <div style="width: 90px; height: 90px; min-width: 90px; background: linear-gradient(135deg, #6366f1, #a855f7); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #ffffff; font-size: 32px; font-weight: 800; border: 4px solid rgba(255, 255, 255, 0.3); box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);">
            {initials}
          </div>

          <!-- Metadata -->
          <div style="flex: 1; text-align: left;">
            <div style="font-size: 26px; font-weight: 800; color: #f8fafc; margin-bottom: 6px; letter-spacing: 0.3px;">
              {name}
            </div>
            <div style="font-size: 16px; font-weight: 600; color: #818cf8; margin-bottom: 16px;">
              {role}
            </div>
            
            <div style="display: flex; gap: 24px; font-size: 13px; color: #94a3b8;">
              <div>
                <span style="display: block; color: #64748b; font-size: 11px; text-transform: uppercase; font-weight: 700; margin-bottom: 4px;">Department</span>
                <strong style="color: #e2e8f0; font-size: 14px;">{dept}</strong>
              </div>
              <div>
                <span style="display: block; color: #64748b; font-size: 11px; text-transform: uppercase; font-weight: 700; margin-bottom: 4px;">Intern ID</span>
                <strong style="color: #38bdf8; font-size: 14px;">{intern_id}</strong>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer Visual Barcode accent -->
        <div style="background: rgba(15, 23, 42, 0.9); border-top: 1px dashed rgba(255, 255, 255, 0.15); padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #64748b;">
          <span>STATUS: <strong style="color: #4ade80;">ACTIVE 2026</strong></span>
          <span style="letter-spacing: 4px; font-family: monospace; color: #94a3b8; font-size: 14px;">||| | |||| | ||| |||| |</span>
          <span style="font-weight: bold;">NEXARIZA AI ID</span>
        </div>
      </div>
    </div>
    """


def is_job_application(role: str) -> bool:
    """
    Determines if applicant applied for a full-time job position rather than an internship.
    """
    if not role:
        return False
    role_lower = role.strip().lower()
    
    # If the role explicitly includes any intern keyword, it is an internship
    intern_keywords = ["intern", "internship", "trainee", "co-op", "apprentice", "fellow"]
    for kw in intern_keywords:
        if kw in role_lower:
            return False
            
    # Job-indicating terms when "intern" is absent
    job_keywords = [
        "job", "full-time", "fulltime", "permanent", "senior", "lead", "manager",
        "head", "director", "developer", "engineer", "architect", "designer",
        "analyst", "specialist", "consultant", "executive", "associate"
    ]
    for kw in job_keywords:
        if kw in role_lower:
            return True
            
    return True


def build_job_response_email_html(intern: Dict[str, str], config: Dict[str, str]) -> str:
    """
    Builds a clean, formal response email for applicants who applied for a full-time job instead of an internship.
    Politely informs them we offer internships and lists available internship opportunities.
    """
    name = intern.get("name", "Applicant")
    role = intern.get("role", "Full-Time Position")
    company = config.get("company_name", "Nexariza AI Technologies")
    hr_name = config.get("hr_name", "Ahmad Yasin")
    hr_title = config.get("hr_title", "Founder & CEO")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <title>Application Status — {company}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; font-size: 15px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%; background-color: #ffffff;">
    <tr>
      <td align="center" style="padding: 24px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; font-size: 15px; color: #1e293b;">
          
          <!-- Simple Header -->
          <tr>
            <td style="padding-bottom: 20px; border-bottom: 1px solid #e2e8f0;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td align="left" valign="middle">
                    <img src="{NEXARIZA_LOGO_URL}" width="36" height="36" style="display: block; width: 36px; height: 36px; object-fit: contain;" alt="Logo" />
                  </td>
                  <td align="right" valign="middle" style="font-size: 18px; font-weight: 700; color: #0f172a;">
                    {company}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 28px 0;">
              <p style="margin: 0 0 16px 0; font-size: 15px; color: #0f172a;">Dear <strong>{name}</strong>,</p>
              
              <p style="margin: 0 0 16px 0; color: #334155; line-height: 1.6;">
                Thank you for applying for the <strong>{role}</strong> position at <strong>{company}</strong>. We appreciate your interest in our team and taking the time to share your application.
              </p>

              <p style="margin: 0 0 20px 0; color: #334155; line-height: 1.6;">
                We wanted to let you know that we are currently offering <strong>Internship Programs only</strong> and do not have full-time job vacancies available at this moment.
              </p>

              <div style="background-color: #f8fafc; border-left: 4px solid #6366f1; border-radius: 6px; padding: 20px; margin: 24px 0;">
                <p style="margin: 0 0 12px 0; font-weight: 700; color: #0f172a; font-size: 15px;">
                  🚀 Current Internship Opportunities at Nexariza:
                </p>
                <ul style="margin: 0; padding-left: 20px; color: #334155; line-height: 1.8;">
                  <li><strong>AI & Machine Learning Internship</strong> (Generative AI, LLMs, Computer Vision)</li>
                  <li><strong>Full-Stack Software Engineering Internship</strong> (Python, FastAPI, React, Node.js)</li>
                  <li><strong>Mobile App Development Internship</strong> (React Native, Flutter)</li>
                  <li><strong>UI/UX & Product Design Internship</strong> (Figma, Modern Design Systems)</li>
                  <li><strong>Data Science & Analytics Internship</strong> (Python, SQL, Data Pipelines)</li>
                  <li><strong>DevOps & Cloud Engineering Internship</strong> (Docker, AWS, CI/CD)</li>
                </ul>
              </div>

              <p style="margin: 0 0 20px 0; color: #334155; line-height: 1.6;">
                If you are interested in gaining hands-on practical experience through one of our internship tracks, please reply directly to this email with your preferred internship role and updated resume.
              </p>

              <p style="margin: 0 0 24px 0; color: #334155; line-height: 1.6;">
                We wish you every success in your professional journey!
              </p>

              <div style="border-top: 1px solid #e2e8f0; padding-top: 20px; margin-top: 28px; color: #334155;">
                Best regards,<br/><br/>
                <strong style="color: #0f172a; font-size: 16px;">{hr_name}</strong><br/>
                <span style="color: #64748b;">{hr_title}</span><br/>
                <span style="color: #6366f1; font-weight: 600;">{company}</span>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="border-top: 1px solid #f1f5f9; padding-top: 16px; font-size: 12px; color: #94a3b8; text-align: center;">
              &copy; 2026 {company}. Official Application Communication.
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_full_offer_email_html(intern: Dict[str, str], config: Dict[str, str]) -> str:
    """
    Builds a clean, simple, formal, mobile-responsive HTML email for the Internship Offer Letter.
    """
    name = intern.get("name", "Intern")
    role = intern.get("role", "Software Engineering Intern")
    dept = intern.get("department", "Engineering & AI")
    start_date = intern.get("start_date", "September 1, 2026")
    duration = intern.get("duration", "3 Months")
    location = intern.get("location", "Remote / Hybrid")
    intern_id = intern.get("intern_id", "NEX-2026-INT-001")
    
    company = config.get("company_name", "Nexariza AI Technologies")
    hr_name = config.get("hr_name", "Ahmad Yasin")
    hr_title = config.get("hr_title", "Founder & CEO")
    custom_note = config.get("custom_note", "")

    custom_note_html = ""
    if custom_note and custom_note.strip():
        custom_note_html = f"""
        <p style="margin: 0 0 16px 0; color: #334155; line-height: 1.6;">
          {custom_note}
        </p>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <title>Internship Offer Letter</title>
</head>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; font-size: 15px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%; background-color: #ffffff;">
    <tr>
      <td align="center" style="padding: 24px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; font-size: 15px; color: #1e293b;">
          
          <!-- Simple Header -->
          <tr>
            <td style="padding-bottom: 20px; border-bottom: 1px solid #e2e8f0;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td align="left" valign="middle">
                    <img src="{NEXARIZA_LOGO_URL}" width="36" height="36" style="display: block; width: 36px; height: 36px; object-fit: contain;" alt="Logo" />
                  </td>
                  <td align="right" valign="middle" style="font-size: 18px; font-weight: 700; color: #0f172a;">
                    {company}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Body -->
          <tr>
            <td style="padding: 28px 0;">
              <p style="margin: 0 0 8px 0; font-size: 12px; color: #6366f1; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
                Official Offer Letter
              </p>
              <h1 style="margin: 0 0 20px 0; font-size: 22px; font-weight: 800; color: #0f172a;">
                Internship Offer Position
              </h1>

              <p style="margin: 0 0 16px 0; font-size: 15px; color: #0f172a;">Dear <strong>{name}</strong>,</p>

              <p style="margin: 0 0 16px 0; color: #334155; line-height: 1.6;">
                We are pleased to offer you the position of <strong>{role}</strong> in the <strong>{dept}</strong> division at <strong>{company}</strong>. We were impressed by your background and are excited to welcome you to our team.
              </p>

              {custom_note_html}

              <!-- Internship Summary Box -->
              <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 20px; margin: 24px 0;">
                <p style="margin: 0 0 14px 0; font-weight: 700; color: #0f172a; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">
                  📋 Internship Details
                </p>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size: 14px; color: #334155; line-height: 1.8;">
                  <tr>
                    <td style="padding-bottom: 6px;" width="110"><strong>Role:</strong></td>
                    <td style="padding-bottom: 6px;">{role}</td>
                  </tr>
                  <tr>
                    <td style="padding-bottom: 6px;"><strong>Department:</strong></td>
                    <td style="padding-bottom: 6px;">{dept}</td>
                  </tr>
                  <tr>
                    <td style="padding-bottom: 6px;"><strong>Start Date:</strong></td>
                    <td style="padding-bottom: 6px;">{start_date}</td>
                  </tr>
                  <tr>
                    <td style="padding-bottom: 6px;"><strong>Duration:</strong></td>
                    <td style="padding-bottom: 6px;">{duration}</td>
                  </tr>
                  <tr>
                    <td style="padding-bottom: 6px;"><strong>Work Mode:</strong></td>
                    <td style="padding-bottom: 6px;">{location}</td>
                  </tr>
                  <tr>
                    <td><strong>Intern ID:</strong></td>
                    <td><span style="color: #6366f1; font-weight: 600;">{intern_id}</span></td>
                  </tr>
                </table>
              </div>

              <p style="margin: 0 0 24px 0; color: #334155; line-height: 1.6;">
                Please reply directly to this email to formally confirm your acceptance of this offer. We look forward to working with you!
              </p>

              <div style="border-top: 1px solid #e2e8f0; padding-top: 20px; margin-top: 28px; color: #334155;">
                Warm regards,<br/><br/>
                <strong style="color: #0f172a; font-size: 16px;">{hr_name}</strong><br/>
                <span style="color: #64748b;">{hr_title}</span><br/>
                <span style="color: #6366f1; font-weight: 600;">{company}</span>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="border-top: 1px solid #f1f5f9; padding-top: 16px; font-size: 12px; color: #94a3b8; text-align: center;">
              &copy; 2026 {company}. Official Internship Communication.
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_downloadable_card_file(intern: Dict[str, str], config: Dict[str, str]) -> str:
    """
    Creates a standalone HTML file content for the intern card attachment.
    Includes a 'Print / Download ID Badge' button.
    """
    card_html = build_intern_card_html(intern, config)
    name = intern.get("name", "Intern")
    intern_id = intern.get("intern_id", "ID")

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Intern Card - {name} ({intern_id})</title>
  <style>
    body {{
      background: #090d16;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      font-family: Arial, sans-serif;
    }}
    .print-btn {{
      margin-top: 20px;
      padding: 12px 24px;
      background: linear-gradient(135deg, #6366f1, #a855f7);
      color: #ffffff;
      border: none;
      border-radius: 10px;
      font-size: 14px;
      font-weight: bold;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
    }}
    @media print {{
      .print-btn {{ display: none; }}
      body {{ background: white; }}
    }}
  </style>
</head>
<body>
  {card_html}
  <button class="print-btn" onclick="window.print()">🖨️ Print / Save Internship Card</button>
</body>
</html>"""


async def process_single_intern(
    intern: Dict[str, str],
    config: Dict[str, str],
    mode: CampaignMode = CampaignMode.dry_run,
    smtp_config: Optional[dict] = None
) -> InternshipResult:
    """
    Sends or simulates an internship offer letter email for one intern.
    """
    name = intern.get("name", "Intern").strip()
    email = intern.get("email", "").strip()
    role = intern.get("role", "Software Engineering Intern").strip()
    intern_id = intern.get("intern_id", "NEX-INT-001")
    company = config.get("company_name", "Nexariza AI Technologies")

    result = InternshipResult(
        intern_id=intern_id,
        name=name,
        email=email,
        role=role,
        status="pending",
    )

    if not email:
        result.status = "failed"
        result.error = "Missing recipient email address"
        return result

    # Validate Domain MX
    is_valid_domain = await validate_email_domain(email)
    if not is_valid_domain:
        result.status = "skipped"
        result.error = "Invalid domain: Null MX or no MX records found"
        return result

    # Check if applicant applied for a full-time job position or an internship
    if is_job_application(role):
        subject = f"Application Status & Internship Opportunities — {name} | {company}"
        html_body = build_job_response_email_html(intern, config)
        result.application_type = "job_response"
    else:
        subject = f"🎓 Internship Offer Letter — {name} | {company}"
        html_body = build_full_offer_email_html(intern, config)
        result.application_type = "internship_offer"

    result.subject = subject

    if mode == CampaignMode.dry_run:
        result.status = "previewed"
        logger.info(f"[Dry Run] Prepared {result.application_type} for {name} <{email}>")
        return result

    # Live Mode - Send Email
    try:
        success = await send_email(
            recipient=email,
            subject=subject,
            body=html_body,
            sender_name=f"{config.get('hr_name', 'Ahmad Yasin')} | {company}",
            is_html=True,
            smtp_config=smtp_config,
            is_important=True
        )

        if success:
            result.status = "sent"
            logger.info(f"Successfully sent {result.application_type} to {email}")
        else:
            result.status = "failed"
            result.error = "SMTP server rejected recipient"
    except Exception as e:
        logger.error(f"Error sending internship offer to {email}: {e}")
        result.status = "failed"
        result.error = str(e)

    return result


async def run_internship_batch(
    interns: List[Dict[str, str]],
    config: Dict[str, str],
    mode: CampaignMode = CampaignMode.dry_run,
    delay_seconds: int = 10,
    smtp_config: Optional[dict] = None
):
    """
    Background batch processor for internship emails.
    """
    global _internship_state, _cancel_internship_flag
    _cancel_internship_flag = False

    _internship_state.update({
        "status": "running",
        "mode": mode.value,
        "total": len(interns),
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "results": [],
        "current_intern": None,
    })

    email_count = 0
    for idx_intern, intern in enumerate(interns):
        if _cancel_internship_flag:
            _internship_state["status"] = "cancelled"
            logger.info("Internship campaign cancelled by user.")
            break

        _internship_state["current_intern"] = f"{intern.get('name')} ({intern.get('email')})"

        res = await process_single_intern(
            intern=intern,
            config=config,
            mode=mode,
            smtp_config=smtp_config
        )

        _internship_state["results"].append(res.dict())
        _internship_state["processed"] += 1

        if res.status in ["sent", "previewed"]:
            _internship_state["sent"] += 1
            email_count += 1
        elif res.status == "skipped":
            _internship_state["skipped"] += 1
        else:
            _internship_state["failed"] += 1

        # Apply human-like delay between email sends in live mode (if not the last intern)
        if mode == CampaignMode.live and idx_intern < len(interns) - 1:
            if _cancel_internship_flag:
                _internship_state["status"] = "cancelled"
                break

            actual_delay = get_human_delay(float(delay_seconds))

            # Periodic human pause every 5 to 7 emails
            if email_count > 0 and email_count % random.randint(5, 7) == 0:
                micro_break = round(random.uniform(8.0, 16.0), 2)
                actual_delay += micro_break
                logger.info(f"☕ [Human Breather] Taking a short human break of +{micro_break}s after {email_count} emails...")

            logger.info(f"⏳ [Human Delay] Waiting {actual_delay}s before dispatching next candidate email...")

            # Sleep in 1-second ticks for immediate campaign cancellation responsiveness
            sleep_secs = int(actual_delay)
            rem_sec = actual_delay - sleep_secs
            for _ in range(sleep_secs):
                if _cancel_internship_flag:
                    break
                await asyncio.sleep(1.0)
            if not _cancel_internship_flag and rem_sec > 0:
                await asyncio.sleep(rem_sec)

    if _internship_state["status"] != "cancelled":
        _internship_state["status"] = "completed"

    _internship_state["current_intern"] = None
    logger.info(f"Internship batch completed. Sent/Previewed: {_internship_state['sent']}/{_internship_state['total']}")
