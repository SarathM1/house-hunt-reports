import json
import re
import time
from pathlib import Path

import httpx

from .config import FIRECRAWL_API_KEY, RunContext
from .db import Dedup
from .models import ListingDetail, ListingSummary

FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
SEO_URL_TEMPLATE = "https://www.nobroker.in/2bhk-flats-for-rent-in-{locality}_bangalore"


def _firecrawl_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def scrape_seo_page(locality: str, api_key: str = "") -> str:
    api_key = api_key or FIRECRAWL_API_KEY
    url = SEO_URL_TEMPLATE.format(locality=locality)
    resp = httpx.post(
        FIRECRAWL_URL,
        headers=_firecrawl_headers(api_key),
        json={"url": url, "formats": ["markdown"], "waitFor": 5000},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Firecrawl failed for {url}: {data}")
    return data["data"]["markdown"]


def _extract_property_id(url: str) -> str:
    parts = url.rstrip("/").split("/")
    if parts[-1] == "detail":
        return parts[-2].split("-")[-1]
    return parts[-1].split("-")[-1]


def _extract_amount(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    if not match:
        return 0
    raw = match.group(1) if match.group(1) else "0"
    return int(raw.replace(",", "")) if raw else 0


def parse_listings_from_markdown(md: str, source_locality: str) -> list[ListingSummary]:
    listings = []
    blocks = re.split(r"##\s+\[", md)
    for block in blocks[1:]:
        try:
            title_match = re.match(
                r"(.+?)\]\((https://www\.nobroker\.in/property/[^\)]+)\)", block
            )
            if not title_match:
                continue
            title = title_match.group(1).strip()
            url = title_match.group(2).strip()
            property_id = _extract_property_id(url)
            rent = _extract_amount(block, r"₹\s*([\d,]+)")
            maintenance = _extract_amount(block, r"₹\s*([\d,]+)\s*Maintenance")
            deposit = _extract_amount(block, r"₹\s*([\d,]+)\s*Deposit")
            sqft = _extract_amount(block, r"([\d,]+)\s*sqft")

            address_match = re.search(
                r"([^\n]*\b(?:Layout|Road|Rd|Cross|Main|Near|Opp|Gear|Sector)\b[^\n]*)",
                block,
            )
            address = address_match.group(1).strip() if address_match else ""

            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", block)
            available_date = date_match.group(1) if date_match else None

            image_urls = re.findall(r"!\[.*?\]\((https://[^\)]+)\)", block)

            listings.append(
                ListingSummary(
                    property_id=property_id,
                    title=title,
                    rent=rent,
                    deposit=deposit,
                    maintenance=maintenance if maintenance else None,
                    sqft=sqft,
                    address=address,
                    locality=source_locality,
                    building_name=None,
                    detail_url=url,
                    available_date=available_date,
                    image_urls=image_urls,
                )
            )
        except Exception:
            continue
    return listings


def scrape_detail_page(url: str, api_key: str = "") -> str:
    api_key = api_key or FIRECRAWL_API_KEY
    resp = httpx.post(
        FIRECRAWL_URL,
        headers=_firecrawl_headers(api_key),
        json={"url": url, "formats": ["markdown"], "waitFor": 5000},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Firecrawl failed for {url}: {data}")
    return data["data"]["markdown"]


def _extract_table_value(md: str, key: str) -> str | None:
    pattern = rf"\|\s*{re.escape(key)}\s*\|\s*(.+?)\s*\|"
    match = re.search(pattern, md, re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_detail_from_markdown(md: str, property_id: str) -> ListingDetail:
    furnishing = _extract_table_value(md, "Furnishing") or ""
    floor = _extract_table_value(md, "Floor") or ""
    power_backup = _extract_table_value(md, "Power Backup")
    facing = _extract_table_value(md, "Facing")
    parking = _extract_table_value(md, "Parking")
    building_age = _extract_table_value(md, "Age of Building")
    preferred_tenant = _extract_table_value(md, "Preferred Tenant")
    water_supply = _extract_table_value(md, "Water Supply")

    bathrooms_str = _extract_table_value(md, "Bathrooms")
    bathrooms = int(bathrooms_str) if bathrooms_str and bathrooms_str.isdigit() else None

    balconies_str = _extract_table_value(md, "Balconies")
    balconies = int(balconies_str) if balconies_str and balconies_str.isdigit() else None

    security_str = _extract_table_value(md, "Gated Security")
    gated_security = security_str.lower() == "yes" if security_str else None

    desc_match = re.search(r"##\s*Description\s*\n([\s\S]+?)(?=\n##|\Z)", md)
    description = desc_match.group(1).strip() if desc_match else ""

    return ListingDetail(
        property_id=property_id,
        furnishing=furnishing,
        floor=floor,
        power_backup=power_backup,
        facing=facing,
        bathrooms=bathrooms,
        balconies=balconies,
        parking=parking,
        building_age=building_age,
        preferred_tenant=preferred_tenant,
        water_supply=water_supply,
        gated_security=gated_security,
        description=description,
    )


def run_scrape(ctx: RunContext) -> Path:
    config = ctx.config
    dedup = Dedup()
    all_summaries: list[ListingSummary] = []
    seen_ids: set[str] = set()

    for locality in config.target_localities:
        print(f"Scraping {locality}...")
        try:
            md = scrape_seo_page(locality)
            listings = parse_listings_from_markdown(md, locality)
            for ls in listings:
                if ls.property_id in seen_ids or dedup.is_seen(ls.property_id):
                    continue
                if ls.rent > config.max_rent:
                    continue
                seen_ids.add(ls.property_id)
                all_summaries.append(ls)
            print(f"  {len(listings)} found, {len(seen_ids)} unique passing filters")
            time.sleep(2)
        except Exception as e:
            print(f"  Error: {e}")

    results = []
    for i, summary in enumerate(all_summaries):
        print(f"[{i + 1}/{len(all_summaries)}] Detail: {summary.title[:50]}...")
        try:
            md = scrape_detail_page(summary.detail_url)
            detail = parse_detail_from_markdown(md, summary.property_id)
            dedup.mark_seen(summary.property_id)
            results.append({"summary": summary.model_dump(), "detail": detail.model_dump()})
            time.sleep(2)
        except Exception as e:
            print(f"  Detail scrape failed: {e}")
            results.append({"summary": summary.model_dump(), "detail": None})

    out_path = ctx.path("raw.json")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Saved {len(results)} listings to {out_path}")
    return out_path
