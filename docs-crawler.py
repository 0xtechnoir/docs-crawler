#!/usr/bin/env python3
import argparse
import asyncio
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from tqdm import tqdm

# Try to import weasyprint for PDF generation
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

# ---------- CONFIG ----------
UA            = "NotebookLM-prep-crawler/1.1 (+contact: you@example.com)"
OUT_FILE      = Path("doc_dump")
CONCURRENCY   = 6
MAX_RETRIES   = 3
TIMEOUT       = 30
# ----------------------------

# ---------- Crawl helpers (unchanged) ----------
@dataclass
class Fetch:
    url: str; status: int
    text: Optional[str] = None
    data: Optional[bytes] = None
    ctype: Optional[str] = None
    err: Optional[str] = None

def same_host(u, base): return urlparse(u).netloc == urlparse(base).netloc
def ok_content(u, base_url):
    if not same_host(u, base_url):
        return False

    # Parse URL to check for unwanted patterns
    parsed = urlparse(u)

    # Skip URLs with query parameters (usually dynamic content)
    if parsed.query:
        return False

    # Skip common non-documentation paths
    path = parsed.path.lower()
    skip_patterns = [
        '/admin', '/api/', '/login', '/logout', '/register', '/signup',
        '/search', '/tag/', '/category/', '/author/', '/user/',
        '/wp-admin', '/wp-content', '/wp-includes',  # WordPress
        '/_next/', '/static/', '/assets/', '/js/', '/css/', '/images/',  # Static assets
        '/feed', '/rss', '/atom',  # RSS feeds
        '/sitemap', '/robots.txt',  # SEO files
        '/mailto:', '/tel:',  # Contact links
        '/#',  # Anchor links
    ]

    for pattern in skip_patterns:
        if pattern in path:
            return False

    return True

async def req(session, url, binary=False, tries=MAX_RETRIES):
    for a in range(1, tries + 1):
        try:
            async with session.get(url, timeout=TIMEOUT) as r:
                ct = r.headers.get("Content-Type", "")
                if r.status >= 400:
                    return Fetch(url, r.status, err=f"HTTP {r.status}")
                if binary:
                    return Fetch(url, r.status, data=await r.read(), ctype=ct)
                return Fetch(url, r.status, text=await r.text(), ctype=ct)
        except Exception as e:
            if a == tries: return Fetch(url, 0, err=str(e))

def xml_items(root, tag): return [el.text.strip() for el in root.iter() if el.tag.endswith(tag) and el.text]

async def sitemap_urls(session, url, base_url) -> List[str]:
    seen, out, stack = set(), [], [url]
    while stack:
        sm = stack.pop()
        if sm in seen: continue
        seen.add(sm)
        res = await req(session, sm)
        if res.text is None: continue
        try:
            root = ET.fromstring(res.text)
        except ET.ParseError: continue
        if root.tag.endswith("sitemapindex"):
            stack.extend(xml_items(root, "loc"))
        elif root.tag.endswith("urlset"):
            # Preserve order by adding URLs in the order they appear in the sitemap
            for u in xml_items(root, "loc"):
                if ok_content(u, base_url) and u not in out:
                    out.append(u)
    return out

def sort_urls_logically(urls: List[str], base_url: str) -> List[str]:
    """Sort URLs in a logical order for documentation"""
    # Remove duplicate URLs with different anchor fragments
    unique_urls = {}
    for url in urls:
        parsed = urlparse(url)
        # Use URL without anchor fragment as key
        base_url_no_anchor = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if base_url_no_anchor not in unique_urls:
            unique_urls[base_url_no_anchor] = url

    urls = list(unique_urls.values())

    def url_priority(url: str) -> tuple:
        parsed = urlparse(url)
        path = parsed.path.lower()
        path_parts = [p for p in path.split('/') if p]

        # Priority 1: Homepage
        if path in ['', '/', '/docs', '/documentation']:
            return (0, '', 0, 0, path)

        # Get the main section (first path part)
        main_section = path_parts[0] if path_parts else ''

        # Priority 2: Shorter paths within each section (likely overview/intro pages)
        # Priority 3: Longer paths within each section (likely detailed pages)
        return (1, main_section, len(path_parts), path)

    return sorted(urls, key=url_priority)

async def crawl_site_for_pages(session, base_url: str) -> List[str]:
    """Fallback: crawl the site to discover pages when no sitemap is available"""
    print("No sitemap found, crawling site to discover pages...")

    discovered_urls = []  # Use list to preserve discovery order
    discovered_set = set()  # For fast lookup
    to_visit = [base_url]
    visited = set()

    while to_visit and len(discovered_urls) < 100:  # Limit to prevent infinite crawling
        current_url = to_visit.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            res = await req(session, current_url)
            if not res.text:
                continue

            soup = BeautifulSoup(res.text, "lxml")

            # Find all links on the page
            for link in soup.find_all("a", href=True):
                href = link["href"]

                # Convert relative URLs to absolute
                if href.startswith("/"):
                    full_url = urljoin(base_url, href)
                elif href.startswith("http"):
                    full_url = href
                else:
                    continue

                # Only include URLs from the same domain
                if urlparse(full_url).netloc == urlparse(base_url).netloc:
                    # Filter for documentation pages (avoid admin, api, etc.)
                    if ok_content(full_url, base_url) and full_url not in discovered_set:
                        discovered_set.add(full_url)
                        discovered_urls.append(full_url)  # Preserve discovery order
                        to_visit.append(full_url)

        except Exception as e:
            print(f"Error crawling {current_url}: {e}")
            continue

    # Sort the discovered URLs logically
    sorted_urls = sort_urls_logically(discovered_urls, base_url)
    return sorted_urls

async def discover_pages(session, base_url: str, sitemap_url: str) -> List[str]:
    """Try sitemap first, fall back to crawling if no sitemap exists"""
    print(f"Trying sitemap at: {sitemap_url}")

    # Try sitemap first
    try:
        sitemap_pages = await sitemap_urls(session, sitemap_url, base_url)
        if sitemap_pages:
            print(f"✅ Successfully found {len(sitemap_pages)} pages from sitemap")
            return sitemap_pages
        else:
            print("❌ Sitemap found but no pages extracted")
    except Exception as e:
        print(f"❌ Sitemap not found or invalid: {e}")

    # Fall back to crawling
    print("🔄 Falling back to crawling...")
    return await crawl_site_for_pages(session, base_url)


# ----------------------------------------------

async def page_markdown(session, url) -> Tuple[str, str]:
    r = await req(session, url)
    if not r.text: return url, f"## {url}\n\n*Failed to fetch.*\n\n---\n"

    # Parse HTML and extract clean content
    soup = BeautifulSoup(r.text, "lxml")

    # Remove unwanted elements
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "img", "svg", "iframe"]):
        tag.decompose()

    # Get title
    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else url

    # More comprehensive content extraction for different site structures
    main_content = None

    # Try common documentation site selectors
    selectors = [
        "main", "article",
        "[role='main']", "[role='article']",
        ".content", "#content", ".main", "#main",
        ".doc-content", ".documentation-content", ".docs-content",
        ".page-content", ".post-content", ".entry-content",
        ".gitbook-root", ".gitbook-body", ".gitbook-content",
        ".markdown-body", ".markdown-content",
        ".doc-body", ".documentation-body"
    ]

    for selector in selectors:
        main_content = soup.select_one(selector)
        if main_content and len(main_content.get_text(strip=True)) > 100:  # Ensure it has substantial content
            break

    # If no specific content area found, try to find the largest text container
    if not main_content or len(main_content.get_text(strip=True)) < 100:
        # Find all divs and get the one with the most text content
        divs = soup.find_all("div")
        best_div = None
        max_text_length = 0

        for div in divs:
            text_length = len(div.get_text(strip=True))
            if text_length > max_text_length and text_length > 200:  # Minimum content threshold
                # Skip navigation-like divs
                div_html = str(div).lower()
                if not any(nav_word in div_html for nav_word in ['nav', 'menu', 'sidebar', 'header', 'footer']):
                    best_div = div
                    max_text_length = text_length

        if best_div:
            main_content = best_div

    # Fallback to body if still no content
    if not main_content or len(main_content.get_text(strip=True)) < 50:
        main_content = soup.find("body") or soup

    # Convert to clean markdown
    body = md(str(main_content), heading_style="ATX", strip=["script", "style", "nav", "header", "footer", "img", "svg"]).strip()

    # Clean up the markdown
    if body and len(body.strip()) > 50:  # Ensure we have meaningful content
        hdr = f"## {title_text}\n\n**Source:** {url}\n\n"
        return url, hdr + body + "\n\n---\n"
    else:
        return url, f"## {title_text}\n\n**Source:** {url}\n\n*No content extracted.*\n\n---\n"

def save_markdown(md_text: str, out_path: Path):
    print(f"Markdown size: {len(md_text)/1024:.1f} KB")

    # Clean up markdown to avoid YAML parsing issues
    # Remove any lines that might be interpreted as YAML
    lines = md_text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Skip lines that look like YAML metadata
        if line.strip().startswith('---') and len(cleaned_lines) < 10:
            continue
        if line.strip().startswith('...'):
            continue
        cleaned_lines.append(line)

    cleaned_md = '\n'.join(cleaned_lines)

    # Save as markdown file
    md_path = out_path.with_suffix('.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_md)
    print(f"Wrote {md_path} ({md_path.stat().st_size/1024:.1f} KB)")

    # Generate beautiful HTML first, then convert to PDF
    try:
        import subprocess
        html_path = out_path.with_suffix('.html')
        result = subprocess.run(['pandoc', '--from', 'markdown_strict', '--to', 'html', '--standalone',
                               '--css', 'https://cdn.jsdelivr.net/npm/water.css@2/out/water.css',
                               str(md_path), '-o', str(html_path)],
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"Created {html_path} ({html_path.stat().st_size/1024:.1f} KB)")

            # Now convert the beautiful HTML to PDF using WeasyPrint
            if WEASYPRINT_AVAILABLE:
                try:
                    pdf_path = out_path.with_suffix('.pdf')

                    # Read the beautiful HTML file
                    with open(html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()

                    # Generate PDF with timeout
                    import signal
                    def timeout_handler(signum, frame):
                        raise TimeoutError("PDF generation timed out")

                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(120)  # 2 minute timeout

                    try:
                        HTML(string=html_content).write_pdf(pdf_path)
                        signal.alarm(0)  # Cancel timeout
                        print(f"Also created {pdf_path} ({pdf_path.stat().st_size/1024:.1f} KB)")
                    except Exception as e:
                        signal.alarm(0)  # Cancel timeout
                        print(f"PDF generation failed: {e}")

                except Exception as e:
                    print(f"PDF generation skipped: {e}")
            else:
                print("Open the HTML file in a browser and use Print (Cmd+P) to save as PDF")
        else:
            print(f"HTML conversion failed: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        print(f"HTML conversion skipped: {e}")

    print("The markdown file is ready for NotebookLM")

async def main(base_url: str):
    # Ensure base_url ends with a slash
    if not base_url.endswith('/'):
        base_url = base_url + '/'

    sitemap_url = f"{base_url}sitemap.xml"

    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        pages = await discover_pages(s, base_url, sitemap_url)
        print(f"Discovered {len(pages)} pages.")

        # Debug: Print discovered pages in order
        print("\nDiscovered pages in order:")
        for i, page in enumerate(pages, 1):  # Show ALL pages
            print(f"  {i:2d}. {page}")
        print()

        if not pages:
            print("No pages discovered. Check the BASE URL and ensure the site is accessible.")
            return

        sem, results = asyncio.Semaphore(CONCURRENCY), {}
        async def worker(u):
            async with sem:
                _, md_text = await page_markdown(s, u)
                results[u] = md_text
        tasks = [asyncio.create_task(worker(u)) for u in pages]
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Crawling"):
            await f

    print("Compiling markdown...")
    # Extract domain name from BASE URL for the title
    from urllib.parse import urlparse
    domain = urlparse(base_url).netloc

    # Print the final order of pages as they appear in the document
    print("\nFinal document order:")
    for i, page in enumerate(pages, 1):
        print(f"{i:2d}. {page}")

    all_md = (
        f"# {domain} — Snapshot ({time.strftime('%Y-%m-%d')})\n\n"
        "> Clean documentation content extracted from sitemap.\n\n"
        + "".join(results[u] for u in pages)
    )
    print("Saving markdown...")
    save_markdown(all_md, OUT_FILE)
    print("Done!")

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Universal documentation scraper that creates clean markdown and PDF output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run docs-crawler.py https://docs.cartridge.gg/
  uv run docs-crawler.py https://docs.example.com
  uv run docs-crawler.py https://docs.yom.net/
        """
    )
    parser.add_argument(
        "base_url",
        help="Base URL of the documentation site to scrape (e.g., https://docs.example.com/)"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    asyncio.run(main(args.base_url))
