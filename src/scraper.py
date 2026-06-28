"""Scrape NoBroker listings via Firecrawl cloud API."""
import json
import re
import time
from datetime import date
from pathlib import Path

import requests

from .config import FIRECRAWL_API_KEY, RAW_DIR, TARGET_LOCALITIES
from .models import ListingSummary

FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
HEADERS = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

SEO_URL_TEMPLATE = "https://www.nobroker.in/2bhk-flats-for-rent-in-{locality}_bangalore"


def scrape_seo_page(locality: str) -> str:
    """Scrape a NoBroker SEO listing page, return markdown."""
    url = SEO_URL_TEMPLATE.format(locality=locality)
    resp = requests.post(
        FIRECRAWL_URL,
        headers=HEADERS,
        json={"url": url, "formats": ["markdown"], "waitFor": 5000},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Firecrawl failed for {url}: {data}")
    return data["data"]["markdown"]


def parse_listings_from_markdown(md: str, source_locality: str) -> list[ListingSummary]:
    """Extract listing summaries from NoBroker SEO page markdown."""
    listings = []
    detail_urls = re.findall(
        r'(https://www\.nobroker\.in/property/[^\s\)\]"]+/detail)', md
    )
    # ponytail: regex parsing — upgrade to proper HTML parser if markdown format changes
    blocks = re.split(r'##\s+\[', md)
    for block in blocks[1:]:  # skip preamble
        try:
            title_match = re.match(r'(.+?)\]\((https://www\.nobroker\.in/property/[^\)]+)\)', block)
            if not title_match:
                continue

            title = title_match.group(1).strip()
            url = title_match.group(2).strip()

            rent = _extract_amount(block, r'₹\s*([\d,]+)')
            maintenance = _extract_amount(block, r'₹\s*([\d,]+)\s*Maintenance')
            deposit = _extract_amount(block, r'₹([\d,]+)\s*\n.*Deposit|₹([\d,]+)\s*$', multi_line=True)
            sqft = _extract_int(block, r'([\d,]+)\s*sqft')

            address_match = re.search(r'(?:Layout|Road|Rd|Cross|Main|Near|Opp)[^₹\n]{5,100}', block)
            address = address_match.group(0).strip() if address_match else ""

            listings.append(ListingSummary(
                title=title,
                url=url,
                rent=rent,
                maintenance=maintenance,
                deposit=deposit,
                sqft=sqft,
                address=address,
                locality=source_locality,
                source_locality=source_locality,
            ))
        except Exception:
            continue

    return listings


def _extract_amount(text: str, pattern: str, multi_line: bool = False) -> int:
    flags = re.MULTILINE if multi_line else 0
    match = re.search(pattern, text, flags)
    if not match:
        return 0
    raw = match.group(1) if match.group(1) else (match.group(2) if match.lastindex and match.lastindex >= 2 else "0")
    return int(raw.replace(",", "")) if raw else 0


def _extract_int(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def scrape_detail_page(url: str) -> str:
    """Scrape individual listing detail page, return markdown."""
    resp = requests.post(
        FIRECRAWL_URL,
        headers=HEADERS,
        json={"url": url, "formats": ["markdown"], "waitFor": 5000},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Firecrawl failed for {url}: {data}")
    return data["data"]["markdown"]


def scrape_all_localities() -> list[ListingSummary]:
    """Scrape all target localities, return combined listings."""
    all_listings = []
    seen_urls = set()

    for locality in TARGET_LOCALITIES:
        print(f"Scraping {locality}...")
        try:
            md = scrape_seo_page(locality)
            listings = parse_listings_from_markdown(md, locality)
            for l in listings:
                if l.url not in seen_urls:
                    seen_urls.add(l.url)
                    all_listings.append(l)
            print(f"  Found {len(listings)} listings ({len(seen_urls)} unique total)")
            time.sleep(2)  # rate limiting courtesy
        except Exception as e:
            print(f"  Error scraping {locality}: {e}")

    return all_listings


def save_raw(listings: list[ListingSummary], tag: str = "") -> Path:
    """Save raw listings to timestamped JSON file."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date.today().isoformat()}{'-' + tag if tag else ''}.json"
    path = RAW_DIR / filename
    path.write_text(json.dumps([l.model_dump() for l in listings], indent=2))
    print(f"Saved {len(listings)} listings to {path}")
    return path


def run():
    """Full scrape pipeline."""
    listings = scrape_all_localities()
    if listings:
        return save_raw(listings)
    print("No listings found.")
    return None
