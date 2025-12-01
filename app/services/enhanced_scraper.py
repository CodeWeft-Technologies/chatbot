"""
Enhanced web scraping with Playwright JS rendering and Readability content extraction.
Falls back to BeautifulSoup if Playwright is unavailable.
"""
from typing import Optional, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

# Try importing Playwright and Readability
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available - using BeautifulSoup fallback")

try:
    from readability import Document
    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False
    logger.warning("Readability not available - using basic extraction")

try:
    import langdetect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger.warning("langdetect not available - language detection disabled")

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin


class ScrapedContent:
    """Container for scraped web content with metadata"""
    def __init__(
        self,
        content: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        canonical_url: Optional[str] = None,
        language: Optional[str] = None,
        final_url: Optional[str] = None,
    ):
        self.content = content
        self.title = title
        self.description = description
        self.canonical_url = canonical_url
        self.language = language
        self.final_url = final_url


def detect_language(text: str) -> Optional[str]:
    """Detect language of text content"""
    if not LANGDETECT_AVAILABLE or not text or len(text.strip()) < 20:
        return None
    try:
        return langdetect.detect(text)
    except Exception as e:
        logger.debug(f"Language detection failed: {e}")
        return None


def extract_with_readability(html: str, url: str) -> Tuple[str, Optional[str]]:
    """Extract main content using Readability algorithm"""
    if not READABILITY_AVAILABLE:
        return html, None
    
    try:
        doc = Document(html)
        title = doc.title()
        content_html = doc.summary()
        
        # Convert extracted HTML to clean text
        soup = BeautifulSoup(content_html, "html.parser")
        
        # Remove remaining noise
        for tag in soup.find_all(["script", "style", "noscript", "template"]):
            tag.decompose()
        
        text = soup.get_text("\n")
        return text, title
    except Exception as e:
        logger.warning(f"Readability extraction failed: {e}")
        return html, None


def scrape_with_playwright(url: str, timeout: int = 30000) -> Tuple[str, str]:
    """
    Scrape URL using Playwright for JS-rendered content.
    Returns (html, final_url)
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError("Playwright not available")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                locale="en-US",
            )
            page = context.new_page()
            
            # Navigate and wait for network idle
            page.goto(url, timeout=timeout, wait_until="networkidle")
            
            # Wait a bit for dynamic content
            page.wait_for_timeout(1000)
            
            html = page.content()
            final_url = page.url
            
            return html, final_url
        finally:
            browser.close()


def scrape_with_requests(url: str, timeout: int = 20) -> Tuple[str, str]:
    """
    Fallback scraping using requests + BeautifulSoup.
    Returns (html, final_url)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    r = requests.get(url, timeout=timeout, headers=headers)
    r.raise_for_status()
    
    # Check for AMP version
    soup = BeautifulSoup(r.text, "html.parser")
    amp = soup.find("link", attrs={"rel": "amphtml"})
    amp_href = amp.get("href") if amp else None
    
    if amp_href:
        try:
            amp_url = urljoin(r.url, amp_href)
            r2 = requests.get(amp_url, timeout=timeout, headers=headers)
            r2.raise_for_status()
            return r2.text, r2.url
        except Exception as e:
            logger.debug(f"AMP fetch failed: {e}")
    
    return r.text, r.url


def extract_metadata(soup: BeautifulSoup, final_url: str) -> Dict[str, Any]:
    """Extract metadata from HTML soup"""
    metadata = {}
    
    # Title
    try:
        if soup.title:
            metadata["title"] = soup.title.string.strip()
    except Exception:
        pass
    
    # Description
    try:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            desc = meta_desc.get("content", "").strip()
            if desc:
                metadata["description"] = desc
    except Exception:
        pass
    
    # Canonical URL
    try:
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical:
            href = canonical.get("href", "").strip()
            if href:
                metadata["canonical_url"] = urljoin(final_url, href)
    except Exception:
        pass
    
    return metadata


def clean_text(text: str) -> str:
    """Clean and normalize text content"""
    try:
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)
    except Exception:
        return text or ""


def extract_content_fallback(soup: BeautifulSoup) -> str:
    """
    Fallback content extraction using cascading selectors.
    Used when Readability is not available or fails.
    For landing pages / homepages, extracts all visible text from body.
    """
    # Remove noise
    for tag in soup.find_all(["script", "style", "noscript", "template"]):
        tag.decompose()
    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        tag.decompose()
    
    # Try content selectors in order (for article pages)
    candidates = []
    selectors = [
        lambda s: s.find("article"),
        lambda s: s.find(attrs={"role": "main"}),
        lambda s: s.find(id="main"),
        lambda s: s.find(id="content"),
        lambda s: s.find(id="root"),  # React/Vue apps
        lambda s: s.find(id="app"),   # React/Vue apps
        lambda s: s.find(class_="article"),
        lambda s: s.find(class_="post"),
        lambda s: s.find(class_="content"),
        lambda s: s.find(class_="entry-content"),
    ]
    
    for selector in selectors:
        try:
            el = selector(soup)
            if el:
                text = el.get_text("\n", strip=True)
                if text and len(text) > 200:  # Only consider substantial content
                    candidates.append(text)
        except Exception:
            pass
    
    # Special handling for MSN
    try:
        host = urlparse(soup.find("link", attrs={"rel": "canonical"}).get("href", "")).netloc.lower()
        if "msn.com" in host:
            article_selectors = [
                lambda s: s.find("article"),
                lambda s: s.find(attrs={"itemprop": "articleBody"}),
                lambda s: s.find("section", attrs={"itemprop": "articleBody"}),
                lambda s: s.find("div", attrs={"itemprop": "articleBody"}),
            ]
            for sel in article_selectors:
                try:
                    el = sel(soup)
                    if el:
                        paragraphs = [p.get_text(" ") for p in el.find_all("p")]
                        text = "\n".join(paragraphs)
                        if text:
                            return text
                except Exception:
                    pass
    except Exception:
        pass
    
    # Use best candidate if found
    if candidates:
        return max(candidates, key=len) or ""
    
    # For landing pages / homepages with no clear article structure,
    # extract all visible text from body
    body = soup.find("body")
    if body:
        return body.get_text("\n", strip=True)
    
    # Last resort: all text
    return soup.get_text("\n", strip=True)


def scrape_url(
    url: str,
    use_playwright: bool = True,
    timeout: int = 30,
) -> ScrapedContent:
    """
    Scrape URL with automatic fallback strategy:
    1. Try Playwright (if enabled and available) for JS-rendered content
    2. Fall back to requests + BeautifulSoup
    3. Try Readability for clean content extraction
    4. Fall back to cascading selector strategy
    """
    # Normalize URL
    url = url.strip()
    if not url:
        raise ValueError("URL is required")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    
    # Fetch HTML
    html = None
    final_url = url
    
    if use_playwright and PLAYWRIGHT_AVAILABLE:
        try:
            html, final_url = scrape_with_playwright(url, timeout * 1000)
            logger.info(f"Scraped with Playwright: {url}")
        except Exception as e:
            logger.warning(f"Playwright failed, falling back to requests: {e}")
    
    if not html:
        html, final_url = scrape_with_requests(url, timeout)
        logger.info(f"Scraped with requests: {url}")
    
    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract metadata
    metadata = extract_metadata(soup, final_url)
    
    # Extract content
    content = ""
    title = metadata.get("title")
    
    if READABILITY_AVAILABLE:
        try:
            content, readability_title = extract_with_readability(html, final_url)
            if not title and readability_title:
                title = readability_title
            
            # If Readability extracted very little, it's likely a homepage/landing page
            # that doesn't fit the article format - use fallback instead
            if len(content.strip()) < 500:
                logger.debug(f"Readability extracted only {len(content)} chars, using fallback")
                content = extract_content_fallback(soup)
                logger.debug("Used fallback content extraction")
            else:
                logger.debug("Used Readability for content extraction")
        except Exception as e:
            logger.warning(f"Readability failed: {e}")
            content = extract_content_fallback(soup)
    else:
        content = extract_content_fallback(soup)
        logger.debug("Used fallback content extraction")
    
    # Clean content
    content = clean_text(content)
    
    # Detect language
    language = detect_language(content)
    
    # Assemble final text (title + description + content)
    text_parts = []
    if title:
        text_parts.append(title)
    if metadata.get("description"):
        text_parts.append(metadata["description"])
    text_parts.append(content)
    
    final_text = "\n\n".join([t for t in text_parts if t])
    
    return ScrapedContent(
        content=final_text,
        title=title,
        description=metadata.get("description"),
        canonical_url=metadata.get("canonical_url", final_url),
        language=language,
        final_url=final_url,
    )
