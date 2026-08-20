"""
scraper_service.py
------------------
Fetches a client's website (up to 3 pages) and extracts meaningful text
content to give Gemini/Groq context for crafting a personalized pitch email.

Also calls flaw_analyzer to detect operational weaknesses in the site.

Fallback: If httpx + BeautifulSoup fails (JS-rendered sites, bot-blocked,
empty content), uses PixelRAG (pixelshot) to screenshot the website and
Gemini Vision to read the screenshot — no HTML parsing needed.
"""

import httpx
import asyncio
import re
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Optional, Tuple
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

# Extra pages to crawl for richer context
EXTRA_PATHS = ["/about", "/about-us", "/services", "/contact", "/pricing"]


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


def _extract_text_and_html(response_text: str, max_chars: int = 1500) -> Tuple[str, str]:
    """
    Parse HTML and return (clean_text, raw_html).
    Strips noise tags; preserves raw HTML for rule-based flaw scanning.
    """
    soup = BeautifulSoup(response_text, "html.parser")

    # Remove noise elements but keep the raw HTML before stripping
    raw_html = response_text  # keep full HTML for flaw scanning

    for tag in soup(["script", "style", "nav", "noscript", "svg", "img", "form", "aside"]):
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
    body_text = re.sub(r"\s+", " ", body_text)

    parts = []
    if title:
        parts.append(f"Page Title: {title}")
    if meta_desc:
        parts.append(f"Meta Description: {meta_desc}")
    if body_text:
        parts.append(f"Content: {body_text[:max_chars]}")

    return "\n".join(parts), raw_html


async def _fetch_page(client: httpx.AsyncClient, url: str) -> Optional[Tuple[str, str]]:
    """
    Fetch a single page and return (clean_text, raw_html) or None on error.
    """
    try:
        resp = await client.get(url, timeout=8.0)
        resp.raise_for_status()
        return _extract_text_and_html(resp.text)
    except Exception as e:
        logger.debug(f"Could not fetch {url}: {e}")
        return None


# ── PixelRAG Fallback (screenshot → Gemini Vision) ────────────────────────────

# Minimum content length to consider httpx scrape "successful"
_MIN_CONTENT_LENGTH = 50

# Prompt for Gemini Vision to extract text from website screenshots
_VISION_EXTRACT_PROMPT = (
    "Extract all visible text content from this website screenshot. "
    "Include: page title, navigation menu items, headings, body text, "
    "contact information, services offered, pricing if visible, and "
    "any other meaningful business information. "
    "Format the output as clean, structured text with sections. "
    "Do NOT describe the visual design — only extract the text content."
)


async def _pixelrag_fallback(url: str, max_chars: int = 2500) -> Optional[Tuple[str, None]]:
    """
    Fallback scraper: takes a screenshot of the website using pixelshot,
    then sends it to Gemini Vision to extract text content.

    Returns (clean_text, None) or (None, None) on failure.
    Note: html_raw is always None since we're reading from a screenshot.
    """
    from services.gemini_service import _call_gemini_vision

    try:
        from pixelrag_render import render_url
    except ImportError:
        logger.warning(
            "[PixelRAG] pixelrag not installed. "
            "Run: pip install pixelrag && playwright install chromium"
        )
        return None, None

    logger.info(f"[PixelRAG] Falling back to screenshot scrape for: {url}")

    try:
        # 1. Screenshot the webpage into tile images (run in worker thread since render_url calls asyncio.run internally)
        with tempfile.TemporaryDirectory() as tmpdir:
            tile_dirs = await asyncio.to_thread(render_url, url, output_dir=tmpdir)

            # render_url returns a list of Path objects pointing to tile directories
            if not tile_dirs:
                logger.warning(f"[PixelRAG] No tiles rendered for {url}")
                return None, None

            # Collect image files (.jpg, .png) from tile directories
            image_files = []
            for t_dir in tile_dirs:
                t_path = Path(t_dir)
                if t_path.is_dir():
                    # Find all tile images sorted in order
                    imgs = sorted(list(t_path.glob("*.jpg")) + list(t_path.glob("*.png")))
                    image_files.extend(imgs)
                elif t_path.is_file() and t_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    image_files.append(t_path)

            if not image_files:
                logger.warning(f"[PixelRAG] No tile images found in output for {url}")
                return None, None

            # 2. Read up to 2 tiles max (homepage + upper fold) for broader coverage
            combined_text_parts = []
            tiles_to_process = image_files[:2]

            for img_file in tiles_to_process:
                image_bytes = img_file.read_bytes()
                if not image_bytes:
                    continue

                # 3. Send screenshot to Gemini Vision
                mime = "image/png" if img_file.suffix.lower() == ".png" else "image/jpeg"
                extracted_text = await _call_gemini_vision(
                    image_bytes=image_bytes,
                    prompt=_VISION_EXTRACT_PROMPT,
                    mime_type=mime,
                    max_tokens=1500,
                    temperature=0.2,
                )

                if extracted_text and extracted_text.strip():
                    combined_text_parts.append(extracted_text.strip())

            if not combined_text_parts:
                logger.warning(f"[PixelRAG] Vision extraction returned no text for {url}")
                return None, None

            full_text = "\n\n---\n\n".join(combined_text_parts)
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars]

            logger.info(
                f"[PixelRAG] Successfully extracted {len(full_text)} chars "
                f"from {len(tiles_to_process)} tile(s) for {url}"
            )
            return full_text, None

    except Exception as e:
        logger.warning(f"[PixelRAG] Fallback failed for {url}: {e}")
        return None, None


# ── Main Scraper (httpx first, then PixelRAG fallback) ────────────────────────

async def scrape_website(url: str, max_chars: int = 2500) -> Optional[Tuple[str, str]]:
    """
    Async scrape a URL (homepage + extra pages) and return
    (combined_clean_text, combined_raw_html) or (None, None) on failure.

    If httpx + BeautifulSoup fails or returns insufficient content,
    automatically falls back to PixelRAG (screenshot → Gemini Vision).
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Normalise base URL
    base = url.rstrip("/")

    combined_text_parts = []
    combined_html_parts = []
    httpx_failed = False

    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=12.0,
        ) as client:

            # 1. Always scrape the homepage first
            result = await _fetch_page(client, base)
            if result:
                text, html = result
                combined_text_parts.append(text)
                combined_html_parts.append(html)
            else:
                logger.warning(f"[Scraper] Homepage unreachable via httpx: {base}")
                httpx_failed = True

            # 2. Try extra pages concurrently (best-effort)
            if not httpx_failed:
                extra_urls = [f"{base}{path}" for path in EXTRA_PATHS]
                tasks = [_fetch_page(client, u) for u in extra_urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                fetched = 0
                for res in results:
                    if isinstance(res, tuple) and res[0]:
                        text, html = res
                        combined_text_parts.append(text)
                        combined_html_parts.append(html)
                        fetched += 1
                        if fetched >= 2:  # Cap at 2 extra pages
                            break

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error scraping {url}: {e.response.status_code}")
        httpx_failed = True
    except Exception as e:
        logger.warning(f"Failed to scrape {url} via httpx: {e}")
        httpx_failed = True

    # Check if httpx got enough content
    if not httpx_failed and combined_text_parts:
        full_text = "\n\n---\n\n".join(combined_text_parts)
        full_html = "\n".join(combined_html_parts)

        # Trim combined text to max_chars
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars]

        # If content is too short, it's likely a JS-rendered page with no real text
        if len(full_text.strip()) >= _MIN_CONTENT_LENGTH:
            logger.info(f"[Scraper] httpx scraped {len(combined_text_parts)} pages from {base}")
            return full_text, full_html
        else:
            logger.info(
                f"[Scraper] httpx returned only {len(full_text.strip())} chars for {base} "
                f"— too short, trying PixelRAG fallback"
            )

    # ── PixelRAG Fallback ─────────────────────────────────────────────────────
    logger.info(f"[Scraper] httpx failed or insufficient for {base} — invoking PixelRAG")
    return await _pixelrag_fallback(base, max_chars)


async def get_client_web_context(email: str, website: Optional[str] = None) -> dict:
    """
    Main entry point. Returns a dict with:
      - domain: str
      - is_free_email: bool
      - website_url: str | None
      - web_content: str | None       (scraped clean text)
      - html_raw: str | None          (raw HTML for flaw scanning)
      - flaw_report: WebsiteFlawReport | None
    """
    from services.flaw_analyzer import analyze_website_flaws

    domain = get_domain_from_email(email)
    free_email = is_free_email(email)

    result = {
        "domain": domain,
        "is_free_email": free_email,
        "website_url": None,
        "web_content": None,
        "html_raw": None,
        "flaw_report": None,
    }

    target_url = None
    if website:
        target_url = website
        result["website_url"] = website
    elif not free_email and domain:
        target_url = domain
        result["website_url"] = domain

    if target_url:
        web_content, html_raw = await scrape_website(target_url)
        result["web_content"] = web_content
        result["html_raw"] = html_raw

        # Run flaw analysis if we got content
        if web_content:
            try:
                flaw_report = await analyze_website_flaws(
                    url=target_url,
                    web_content=web_content,
                    html_raw=html_raw or "",
                )
                result["flaw_report"] = flaw_report
                logger.info(
                    f"[Scraper] Flaw report ready for {target_url}: "
                    f"{len(flaw_report.flaws)} flaws, urgency={flaw_report.urgency_level}"
                )
            except Exception as e:
                logger.warning(f"[Scraper] Flaw analysis failed for {target_url}: {e}")

    return result

