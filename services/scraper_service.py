"""
scraper_service.py
------------------
Fetches a client's website and extracts meaningful text content
to give Gemini context for crafting a personalized pitch email.
"""

import httpx
from bs4 import BeautifulSoup
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Known free/personal email domains — no point scraping these
FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "live.com", "protonmail.com", "icloud.com", "aol.com",
    "mail.com", "zoho.com", "yandex.com", "msn.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def get_domain_from_email(email: str) -> Optional[str]:
    """Extract domain from an email address."""
    try:
        return email.split("@")[1].lower().strip()
    except IndexError:
        return None


def is_free_email(email: str) -> bool:
    """Returns True if the email belongs to a free/personal provider."""
    domain = get_domain_from_email(email)
    return domain in FREE_EMAIL_DOMAINS if domain else True


async def scrape_website(url: str, max_chars: int = 2500) -> Optional[str]:
    """
    Async scrape a URL and return cleaned visible text content.
    Returns None if unreachable or error.
    """
    # Ensure URL has a scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=10.0,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove noise elements
        for tag in soup(["script", "style", "nav", "footer", "header",
                          "noscript", "svg", "img", "form", "aside"]):
            tag.decompose()

        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and meta_tag.get("content"):
            meta_desc = meta_tag["content"].strip()

        # Extract title
        title = soup.title.string.strip() if soup.title else ""

        # Extract visible body text
        body_text = soup.get_text(separator=" ", strip=True)
        # Collapse whitespace
        import re
        body_text = re.sub(r"\s+", " ", body_text)

        # Compose summary
        parts = []
        if title:
            parts.append(f"Page Title: {title}")
        if meta_desc:
            parts.append(f"Meta Description: {meta_desc}")
        if body_text:
            parts.append(f"Content: {body_text[:max_chars]}")

        return "\n".join(parts)

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error scraping {url}: {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Failed to scrape {url}: {e}")
        return None


async def get_client_web_context(email: str, website: Optional[str] = None) -> dict:
    """
    Main entry point. Returns a dict with:
    - domain: str
    - is_free_email: bool
    - website_url: str | None
    - web_content: str | None  (scraped text)
    """
    domain = get_domain_from_email(email)
    free_email = is_free_email(email)

    result = {
        "domain": domain,
        "is_free_email": free_email,
        "website_url": None,
        "web_content": None,
    }

    if website:
        # Explicit website provided — use it
        result["website_url"] = website
        result["web_content"] = await scrape_website(website)
    elif not free_email and domain:
        # Business email — infer website from domain
        result["website_url"] = domain
        result["web_content"] = await scrape_website(domain)
    # If free email and no website provided, web_content stays None

    return result
