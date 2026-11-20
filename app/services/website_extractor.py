"""Website Content Extraction Engine using HTTPX and BeautifulSoup."""

import re
import json
import logging
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup, Comment

from app.config import settings
from app.schemas import ExtractedWebsiteData, TechnicalSeoHealth
from app.utils.validators import validate_url_security, SSRFProtectionError, InvalidURLError, DNSResolutionError

logger = logging.getLogger(__name__)

# Standard browser headers to avoid basic bot blocks while being polite
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 (SitePulseAI Website Intelligence)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# Regex patterns for contact data
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?\d{1,3}[-.\s]?)?(\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}")

# Subpage keywords to prioritize for business intelligence
HIGH_VALUE_PATH_KEYWORDS = [
    "about", "services", "service", "solutions", "products", "offerings",
    "what-we-do", "company", "pricing", "features"
]


class WebsiteExtractionError(Exception):
    """Raised when website extraction fails due to network, HTTP, or parsing issues."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class WebsiteExtractor:
    """Robust, SSRF-safe website extractor that inspects and parses HTML content."""

    def __init__(self, timeout: float = None, max_content_length: int = None):
        self.timeout = timeout or settings.REQUEST_TIMEOUT_SECONDS
        self.max_content_length = max_content_length or settings.MAX_CONTENT_LENGTH

    async def fetch_html(self, target_url: str) -> Tuple[str, str, int]:
        """
        Safely fetch HTML with SSRF checks on initial URL and on every redirect destination.
        Returns: (html_text, final_effective_url, status_code)
        """
        current_url = validate_url_security(target_url)
        redirect_count = 0

        # We manage redirects manually so we can enforce SSRF validation at every step
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(self.timeout, connect=self.timeout),
            follow_redirects=False,
            verify=True,
        ) as client:
            while True:
                try:
                    response = await client.get(current_url)
                except httpx.TimeoutException:
                    raise WebsiteExtractionError(
                        f"Request to '{current_url}' timed out after {self.timeout}s.",
                        status_code=504,
                    )
                except httpx.RequestError as exc:
                    raise WebsiteExtractionError(
                        f"Connection failed for '{current_url}': {str(exc)}",
                        status_code=502,
                    )

                # Check redirect status
                if response.is_redirect:
                    redirect_count += 1
                    if redirect_count > settings.MAX_REDIRECTS:
                        raise WebsiteExtractionError(
                            f"Too many redirects (limit is {settings.MAX_REDIRECTS}).",
                            status_code=400,
                        )
                    location = response.headers.get("location")
                    if not location:
                        raise WebsiteExtractionError("Redirect response missing 'Location' header.", status_code=502)

                    # Build absolute redirect URL and validate SSRF
                    next_url = urljoin(current_url, location)
                    try:
                        current_url = validate_url_security(next_url)
                    except (SSRFProtectionError, InvalidURLError, DNSResolutionError) as err:
                        raise WebsiteExtractionError(
                            f"Disallowed redirect destination '{next_url}': {str(err)}",
                            status_code=400,
                        )
                    continue

                # Process final response
                if response.status_code == 404:
                    raise WebsiteExtractionError(f"Target website returned 404 Not Found at '{current_url}'.", status_code=404)
                if response.status_code == 403:
                    raise WebsiteExtractionError(f"Target website returned 403 Forbidden at '{current_url}'. Access denied.", status_code=403)
                if response.status_code >= 400:
                    raise WebsiteExtractionError(
                        f"Target website returned HTTP {response.status_code} at '{current_url}'.",
                        status_code=response.status_code,
                    )

                # Check Content-Type
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    raise WebsiteExtractionError(
                        f"URL did not return HTML content (Received Content-Type: '{content_type}').",
                        status_code=415,
                    )

                # Check content length
                raw_bytes = response.content
                if len(raw_bytes) > self.max_content_length:
                    raise WebsiteExtractionError(
                        f"Website response exceeded maximum size limit ({len(raw_bytes)} > {self.max_content_length} bytes).",
                        status_code=413,
                    )

                # Decode HTML with fallback
                try:
                    encoding = response.encoding or "utf-8"
                    html = raw_bytes.decode(encoding, errors="replace")
                except Exception:
                    html = raw_bytes.decode("utf-8", errors="replace")

                if not html.strip():
                    raise WebsiteExtractionError("Website returned completely empty content.", status_code=422)

                return html, str(response.url), response.status_code

    def clean_and_extract_metadata(self, html: str, base_url: str) -> Tuple[ExtractedWebsiteData, TechnicalSeoHealth]:
        """
        Parse HTML, extract structured entities, compute technical SEO metrics,
        and sanitize the text.
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. Title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # 2. Meta tags
        meta_desc = ""
        meta_desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)}) or \
                         soup.find("meta", attrs={"property": re.compile(r"^og:description$", re.I)})
        if meta_desc_tag and meta_desc_tag.get("content"):
            meta_desc = meta_desc_tag["content"].strip()

        meta_keywords: List[str] = []
        meta_kw_tag = soup.find("meta", attrs={"name": re.compile(r"^keywords$", re.I)})
        if meta_kw_tag and meta_kw_tag.get("content"):
            meta_keywords = [k.strip() for k in meta_kw_tag["content"].split(",") if k.strip()]

        # Brand name hints from OpenGraph or JSON-LD
        brand_name = ""
        og_site_name = soup.find("meta", attrs={"property": re.compile(r"^og:site_name$", re.I)})
        if og_site_name and og_site_name.get("content"):
            brand_name = og_site_name["content"].strip()

        # Check Schema.org JSON-LD
        schema_location = ""
        for script_tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script_tag.string or "")
                # Handle @graph or direct object
                items = data.get("@graph", [data]) if isinstance(data, dict) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if not brand_name and item.get("@type") in ("Organization", "Corporation", "LocalBusiness"):
                        brand_name = item.get("name", "")
                    if item.get("address"):
                        addr = item["address"]
                        if isinstance(addr, dict):
                            schema_location = ", ".join(filter(None, [
                                addr.get("streetAddress"),
                                addr.get("addressLocality"),
                                addr.get("addressRegion"),
                                addr.get("addressCountry")
                            ]))
                        elif isinstance(addr, str):
                            schema_location = addr
            except Exception:
                continue

        # If brand name still empty, derive from title
        if not brand_name and title:
            # Common patterns: "Company Name - Home" or "Product | Company Name"
            parts = re.split(r"[-|–—:]", title)
            if len(parts) > 1:
                brand_name = parts[-1].strip() if len(parts[-1].strip()) < 30 else parts[0].strip()
            else:
                brand_name = title[:40].strip()

        # 3. Headings & Heading Health
        h1_headings = [h.get_text(" ", strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
        h2_headings = [h.get_text(" ", strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)]
        h3_headings = [h.get_text(" ", strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)]

        # Duplicate or empty headings check
        all_headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        duplicate_or_empty_headings: List[str] = []
        seen_headings: Set[str] = set()
        for h in all_headings:
            text = h.get_text(strip=True)
            if not text:
                duplicate_or_empty_headings.append(f"Empty <{h.name}> tag found")
            elif text.lower() in seen_headings:
                duplicate_or_empty_headings.append(f"Duplicate heading: '{text[:50]}'")
            else:
                seen_headings.add(text.lower())

        # 4. Navigation Labels
        nav_labels: List[str] = []
        for nav in soup.find_all(["nav", "header"]):
            for a in nav.find_all("a"):
                txt = a.get_text(strip=True)
                if txt and len(txt) < 40 and txt not in nav_labels:
                    nav_labels.append(txt)

        # 5. Internal Links & Subpage discovery
        parsed_base = urlparse(base_url)
        internal_links: Set[str] = set()
        candidate_subpages: List[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            abs_url = urljoin(base_url, href)
            parsed_abs = urlparse(abs_url)

            # Check same origin domain
            if parsed_abs.netloc.lower() == parsed_base.netloc.lower():
                clean_link = abs_url.split("#")[0].rstrip("/")
                if clean_link and clean_link != base_url.rstrip("/"):
                    internal_links.add(clean_link)
                    path_lower = parsed_abs.path.lower()
                    if any(keyword in path_lower for keyword in HIGH_VALUE_PATH_KEYWORDS):
                        if clean_link not in candidate_subpages:
                            candidate_subpages.append(clean_link)

        # 6. Image Alt Text Health
        images = soup.find_all("img")
        total_images = len(images)
        images_missing_alt = sum(1 for img in images if not img.get("alt") or not img.get("alt").strip())

        # 7. Contact Details and Social Links
        full_page_text = soup.get_text(" ")
        emails = list(set(EMAIL_REGEX.findall(full_page_text)))
        # Filter obvious file extension matches that look like emails
        emails = [e for e in emails if not re.search(r"\.(png|jpg|jpeg|gif|svg|webp|css|js)$", e, re.I)][:5]

        # Check mailto links too
        for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
            mail = a["href"].replace("mailto:", "").split("?")[0].strip()
            if mail and mail not in emails:
                emails.append(mail)

        # Phone numbers
        raw_phones = PHONE_REGEX.findall(full_page_text)
        phones: List[str] = []
        for p in soup.find_all("a", href=re.compile(r"^tel:", re.I)):
            p_val = a_val = p["href"].replace("tel:", "").strip()
            if p_val and p_val not in phones:
                phones.append(p_val)
        for rp in raw_phones:
            p_str = "".join(rp).strip()
            if len(re.sub(r"\D", "", p_str)) >= 7 and p_str not in phones:
                phones.append(p_str)
        phones = phones[:4]

        # Social links
        social_links: Dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if "linkedin.com" in href and "linkedin" not in social_links:
                social_links["linkedin"] = a["href"]
            elif ("twitter.com" in href or "x.com" in href) and "x" not in social_links:
                social_links["x"] = a["href"]
            elif "facebook.com" in href and "facebook" not in social_links:
                social_links["facebook"] = a["href"]
            elif "instagram.com" in href and "instagram" not in social_links:
                social_links["instagram"] = a["href"]
            elif "youtube.com" in href and "youtube" not in social_links:
                social_links["youtube"] = a["href"]

        # 8. Clean text: Strip non-content and boilerplate elements
        for element in soup(["script", "style", "noscript", "svg", "iframe", "canvas", "meta", "link"]):
            element.decompose()

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove common cookie banner / modal / popup classes and ids
        for banner in soup.find_all(attrs={"class": re.compile(r"cookie|consent|banner|gdpr|popup|modal-backdrop", re.I)}):
            banner.decompose()
        for banner in soup.find_all(attrs={"id": re.compile(r"cookie|consent|banner|gdpr", re.I)}):
            banner.decompose()

        # Extract main text
        main_content = soup.find("main") or soup.find("article") or soup.find("body") or soup
        text_lines = [line.strip() for line in main_content.get_text("\n").splitlines()]
        # Remove empty lines and obvious duplicate consecutive lines
        cleaned_lines: List[str] = []
        prev_line = ""
        for line in text_lines:
            if line and line != prev_line and len(line) > 1:
                cleaned_lines.append(line)
                prev_line = line

        main_text = "\n".join(cleaned_lines)

        # Enforce character budget to protect token limits
        if len(main_text) > settings.MAX_EXTRACTED_CHARS:
            main_text = main_text[:settings.MAX_EXTRACTED_CHARS] + "\n...[Content truncated for token budget]..."

        # Assemble Technical SEO Health observations
        seo_health_notes: List[str] = []
        if not title:
            seo_health_notes.append("Missing <title> tag on homepage.")
        elif len(title) < 20:
            seo_health_notes.append(f"Title is very short ({len(title)} chars): '{title}'. Recommended length: 50-60 chars.")
        elif len(title) > 70:
            seo_health_notes.append(f"Title is long ({len(title)} chars): may be truncated in search results.")

        if not meta_desc:
            seo_health_notes.append("Missing meta description on homepage.")
        elif len(meta_desc) < 70:
            seo_health_notes.append(f"Meta description is short ({len(meta_desc)} chars). Recommended: 140-160 chars.")
        elif len(meta_desc) > 170:
            seo_health_notes.append(f"Meta description is long ({len(meta_desc)} chars): will be truncated in SERPs.")

        if not h1_headings:
            seo_health_notes.append("No <h1> heading found on homepage.")
        elif len(h1_headings) > 1:
            seo_health_notes.append(f"Multiple <h1> headings found ({len(h1_headings)}). Best practice is one primary H1.")

        if images_missing_alt > 0:
            seo_health_notes.append(f"{images_missing_alt} out of {total_images} images lack descriptive alt text.")

        if len(internal_links) < 3:
            seo_health_notes.append("Low internal linking detected on homepage.")

        technical_health = TechnicalSeoHealth(
            missing_title=not bool(title),
            missing_meta_description=not bool(meta_desc),
            missing_h1=len(h1_headings) == 0,
            duplicate_or_empty_headings=duplicate_or_empty_headings[:5],
            images_missing_alt=images_missing_alt,
            total_images_analyzed=total_images,
            internal_links_count=len(internal_links),
            notes=seo_health_notes,
        )

        extracted_data = ExtractedWebsiteData(
            url=base_url,
            final_url=base_url,
            title=title,
            meta_description=meta_desc,
            meta_keywords=meta_keywords[:15],
            h1_headings=h1_headings[:5],
            h2_headings=h2_headings[:15],
            h3_headings=h3_headings[:20],
            main_text=main_text,
            navigation_labels=nav_labels[:20],
            internal_links=list(internal_links)[:30],
            emails=emails,
            phones=phones,
            social_links=social_links,
            business_name=brand_name,
            address_or_location=schema_location,
            pages_crawled=1,
            total_images_found=total_images,
            images_missing_alt=images_missing_alt,
        )

        return extracted_data, technical_health

    async def extract(self, url: str) -> Tuple[ExtractedWebsiteData, TechnicalSeoHealth]:
        """
        Main extraction entry point.
        Fetches the target homepage, parses it, and optionally fetches up to
        MAX_SUBPAGES_TO_CRAWL high-value subpages (like /about, /services) to enrich intelligence.
        """
        # Fetch homepage
        html, final_url, status = await self.fetch_html(url)
        data, tech_health = self.clean_and_extract_metadata(html, final_url)
        data.final_url = final_url

        # Check for valuable subpages to crawl (up to MAX_SUBPAGES_TO_CRAWL)
        subpages_to_crawl: List[str] = []
        parsed_final = urlparse(final_url)
        for link in data.internal_links:
            plink = urlparse(link)
            if plink.netloc.lower() == parsed_final.netloc.lower():
                path = plink.path.lower()
                if any(kw in path for kw in HIGH_VALUE_PATH_KEYWORDS):
                    if link not in subpages_to_crawl:
                        subpages_to_crawl.append(link)
            if len(subpages_to_crawl) >= settings.MAX_SUBPAGES_TO_CRAWL:
                break

        # Fetch candidate subpages
        subpage_summaries: List[Dict[str, str]] = []
        for sub_url in subpages_to_crawl:
            try:
                sub_html, _, _ = await self.fetch_html(sub_url)
                sub_soup = BeautifulSoup(sub_html, "html.parser")
                sub_title = sub_soup.find("title")
                title_txt = sub_title.get_text(strip=True) if sub_title else ""
                # Strip non-content
                for el in sub_soup(["script", "style", "noscript", "svg", "nav", "footer"]):
                    el.decompose()
                sub_text = " ".join([l.strip() for l in sub_soup.get_text("\n").splitlines() if l.strip()])
                subpage_summaries.append({
                    "url": sub_url,
                    "title": title_txt,
                    "excerpt": sub_text[:1500],
                })
            except Exception as e:
                logger.debug(f"Subpage crawl skipped for '{sub_url}': {e}")
                continue

        if subpage_summaries:
            data.subpage_summaries = subpage_summaries
            data.pages_crawled += len(subpage_summaries)

        return data, tech_health
