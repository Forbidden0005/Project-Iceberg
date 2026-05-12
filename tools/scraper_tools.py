"""
Web scraping tools with pagination support.

Handles multiple pagination types:
- Next/Previous buttons (click-based)
- URL patterns (page=1, page=2, etc.)
- Infinite scroll (scroll-to-load)

Requires: playwright (pip install playwright && playwright install)
"""

import json
import re
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def scrape_paginated(
    url: str,
    selector: str,
    extract: str = "href",
    pagination: Literal["auto", "button", "url", "scroll"] = "auto",
    max_pages: int = 10,
    next_button: str | None = None,
) -> dict[str, Any]:
    """
    Scrape data from paginated websites.
    
    Args:
        url: Starting URL to scrape
        selector: CSS selector for elements to extract (e.g., "a.mcp-link")
        extract: What to extract - "href", "text", "html", or attribute name
        pagination: Pagination type - "auto" (detect), "button" (click next), 
                   "url" (increment page param), "scroll" (infinite scroll)
        max_pages: Maximum pages to scrape (default: 10)
        next_button: CSS selector for next button (optional, auto-detect if not provided)
    
    Returns:
        {
            "success": bool,
            "data": list of extracted values,
            "pages_scraped": int,
            "total_items": int,
            "error": str | None
        }
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "success": False,
            "data": [],
            "pages_scraped": 0,
            "total_items": 0,
            "error": "Playwright not installed. Run: pip install playwright && playwright install",
        }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            all_data = []
            pages_scraped = 0
            
            # Navigate to starting URL
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)  # Let JS settle
            
            # Auto-detect pagination if needed
            if pagination == "auto":
                pagination = _detect_pagination_type(page, next_button)
            
            while pages_scraped < max_pages:
                # Extract data from current page
                elements = page.query_selector_all(selector)
                
                for elem in elements:
                    value = _extract_value(elem, extract, page.url)
                    if value:
                        all_data.append(value)
                
                pages_scraped += 1
                
                # Try to go to next page
                has_next = False
                
                if pagination == "button":
                    has_next = _click_next_button(page, next_button)
                elif pagination == "url":
                    has_next = _navigate_next_url(page, pages_scraped)
                elif pagination == "scroll":
                    has_next = _scroll_to_load(page)
                
                if not has_next:
                    break
                
                # Wait for new content to load
                page.wait_for_timeout(2000)
            
            browser.close()
            
            # Deduplicate data
            all_data = list(dict.fromkeys(all_data))
            
            return {
                "success": True,
                "data": all_data,
                "pages_scraped": pages_scraped,
                "total_items": len(all_data),
                "error": None,
            }
    
    except PlaywrightTimeout:
        return {
            "success": False,
            "data": [],
            "pages_scraped": 0,
            "total_items": 0,
            "error": f"Timeout loading {url}",
        }
    except Exception as e:
        return {
            "success": False,
            "data": [],
            "pages_scraped": 0,
            "total_items": 0,
            "error": str(e),
        }


def _detect_pagination_type(page, next_button_hint: str | None) -> str:
    """Auto-detect pagination type."""
    # Check for common next button selectors
    next_selectors = [
        next_button_hint,
        "a[rel='next']",
        "button:has-text('Next')",
        "a:has-text('Next')",
        ".next",
        ".pagination-next",
        "[aria-label*='next' i]",
    ]
    
    for sel in next_selectors:
        if sel and page.query_selector(sel):
            return "button"
    
    # Check if URL has page parameters
    current_url = page.url
    if re.search(r'[?&](page|p)=\d+', current_url):
        return "url"
    
    # Default to scroll for infinite scroll sites
    return "scroll"


def _extract_value(element, extract: str, base_url: str) -> str | None:
    """Extract value from element based on extract parameter."""
    try:
        if extract == "text":
            return element.inner_text().strip()
        elif extract == "html":
            return element.inner_html()
        elif extract == "href":
            href = element.get_attribute("href")
            if href:
                # Convert relative URLs to absolute
                return urljoin(base_url, href)
            return None
        else:
            # Custom attribute
            return element.get_attribute(extract)
    except Exception:
        return None


def _click_next_button(page, next_button: str | None) -> bool:
    """Click the next button and return True if successful."""
    next_selectors = [
        next_button,
        "a[rel='next']",
        "button:has-text('Next')",
        "a:has-text('Next')",
        ".next",
        ".pagination-next",
        "[aria-label*='next' i]",
    ]
    
    for sel in next_selectors:
        if not sel:
            continue
        
        try:
            elem = page.query_selector(sel)
            if elem and elem.is_visible():
                elem.click()
                page.wait_for_load_state("domcontentloaded")
                return True
        except Exception:
            continue
    
    return False


def _navigate_next_url(page, current_page_num: int) -> bool:
    """Navigate to next page by incrementing URL parameter."""
    current_url = page.url
    next_page_num = current_page_num + 1
    
    # Try common page parameter patterns
    patterns = [
        (r'([?&]page=)\d+', rf'\g<1>{next_page_num}'),
        (r'([?&]p=)\d+', rf'\g<1>{next_page_num}'),
        (r'(/page/)\d+', rf'\g<1>{next_page_num}'),
    ]
    
    for pattern, replacement in patterns:
        if re.search(pattern, current_url):
            next_url = re.sub(pattern, replacement, current_url)
            try:
                page.goto(next_url, wait_until="domcontentloaded", timeout=15000)
                return True
            except Exception:
                return False
    
    # If no pattern found, try appending page parameter
    sep = "&" if "?" in current_url else "?"
    next_url = f"{current_url}{sep}page={next_page_num}"
    
    try:
        page.goto(next_url, wait_until="domcontentloaded", timeout=15000)
        return True
    except Exception:
        return False


def _scroll_to_load(page) -> bool:
    """Scroll to bottom to trigger infinite scroll loading."""
    try:
        # Get current content height
        old_height = page.evaluate("document.body.scrollHeight")
        
        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
        
        # Check if new content loaded
        new_height = page.evaluate("document.body.scrollHeight")
        
        return new_height > old_height
    except Exception:
        return False


def register(registry):
    """Register scraper tools with the tool registry."""
    registry.register(
        "scrape_paginated",
        scrape_paginated,
        description=(
            "Scrape data from paginated websites. Handles button clicks, URL patterns, "
            "and infinite scroll. Returns list of extracted data. "
            "Example: scrape_paginated('https://example.com', 'a.link', extract='href', max_pages=5)"
        ),
        category="web",
        args=[
            {
                "name": "url",
                "required": True,
                "description": "Starting URL to scrape",
            },
            {
                "name": "selector",
                "required": True,
                "description": "CSS selector for elements to extract (e.g., 'a.mcp-link', 'h2.title')",
            },
            {
                "name": "extract",
                "required": False,
                "description": "What to extract: 'href' (links), 'text' (text content), 'html', or attribute name. Default: 'href'",
            },
            {
                "name": "pagination",
                "required": False,
                "description": "Pagination type: 'auto' (detect), 'button' (click next), 'url' (increment page), 'scroll' (infinite). Default: 'auto'",
            },
            {
                "name": "max_pages",
                "required": False,
                "description": "Maximum pages to scrape. Default: 10",
            },
            {
                "name": "next_button",
                "required": False,
                "description": "CSS selector for next button (optional, auto-detected if not provided)",
            },
        ],
    )
