"""Scrape NoBroker detail pages via Playwright (renders SPA fully)."""
import asyncio
import re

from playwright.async_api import async_playwright

from .models import ListingDetail

MAX_CONCURRENT = 3


def _log(msg: str) -> None:
    print(msg, flush=True)


def _extract(page_text: str, label: str) -> str | None:
    # NoBroker detail pages have label on one line, value on next
    pattern = rf"(?:^|\n)\s*{re.escape(label)}\s*\n\s*([^\n]+)"
    match = re.search(pattern, page_text, re.IGNORECASE)
    if not match:
        return None
    val = match.group(1).strip()
    # Skip if value looks like another label (e.g. "No. of Bedroom")
    if val.endswith(":") or "No. of" in val:
        return None
    return val


def _parse_detail_from_text(text: str, property_id: str) -> ListingDetail:
    furnishing = _extract(text, "Furnishing Status") or _extract(text, "Furnishing") or ""
    floor = _extract(text, "Floor") or ""
    facing = _extract(text, "Facing")
    water_supply = _extract(text, "Water Supply")
    building_age = _extract(text, "Age of Building")
    parking_val = _extract(text, "Parking")
    preferred_tenant = _extract(text, "Preferred Tenant")

    bathrooms_str = _extract(text, "Bathroom")
    bathrooms = int(bathrooms_str) if bathrooms_str and bathrooms_str.isdigit() else None

    balconies_str = _extract(text, "Balcony")
    balconies = int(balconies_str) if balconies_str and balconies_str.isdigit() else None

    gated_str = _extract(text, "Gated Security")
    gated_security = gated_str.lower() == "yes" if gated_str else None

    power_backup = None
    if re.search(r"power\s*backup", text, re.IGNORECASE):
        power_backup = "Yes"

    desc_match = re.search(r"Description\n(.+?)(?:\n(?:Amenities|NoBroker|Nearby|Neighbourhood)|\Z)", text, re.DOTALL | re.IGNORECASE)
    description = desc_match.group(1).strip() if desc_match else ""

    return ListingDetail(
        property_id=property_id,
        furnishing=furnishing,
        floor=floor,
        power_backup=power_backup,
        facing=facing,
        bathrooms=bathrooms,
        balconies=balconies,
        parking=parking_val,
        building_age=building_age,
        preferred_tenant=preferred_tenant,
        water_supply=water_supply,
        gated_security=gated_security,
        description=description,
    )


async def _scrape_one(context, url: str, property_id: str, idx: int, total: int, sem: asyncio.Semaphore) -> tuple[str, ListingDetail | None]:
    async with sem:
        _log(f"  [{idx+1}/{total}] {property_id}...")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            text = await page.inner_text("body")
            detail = _parse_detail_from_text(text, property_id)
            _log(f"  ✓ {property_id}: furnishing={detail.furnishing}, power={detail.power_backup}, floor={detail.floor}")
            return property_id, detail
        except Exception as e:
            _log(f"  ✗ {property_id}: {e}")
            return property_id, None
        finally:
            await page.close()


async def _scrape_details_async(entries: list[dict]) -> dict[str, ListingDetail]:
    urls = [(e["summary"]["property_id"], e["summary"]["detail_url"]) for e in entries if not e.get("detail") or not e["detail"].get("furnishing")]
    if not urls:
        return {}

    results = {}
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        tasks = [_scrape_one(context, url, pid, i, len(urls), sem) for i, (pid, url) in enumerate(urls)]
        for coro in asyncio.as_completed(tasks):
            pid, detail = await coro
            if detail:
                results[pid] = detail
        await browser.close()

    return results


def scrape_details_playwright(entries: list[dict]) -> list[dict]:
    """Scrape detail pages for entries missing detail data. Returns updated entries."""
    urls_needed = [e for e in entries if not e.get("detail") or not e["detail"].get("furnishing")]
    if not urls_needed:
        _log("All entries already have detail data.")
        return entries

    _log(f"=== Detail pages via Playwright ({len(urls_needed)} listings) ===")
    details = asyncio.run(_scrape_details_async(entries))

    updated = []
    for entry in entries:
        pid = entry["summary"]["property_id"]
        if pid in details:
            entry["detail"] = details[pid].model_dump()
        updated.append(entry)

    _log(f"  Got details for {len(details)}/{len(urls_needed)} listings")
    return updated
