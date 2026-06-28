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


async def _scrape_images(page) -> list[str]:
    """Click the main photo to open gallery, then collect all image URLs."""
    try:
        photo = page.locator('img[src*="images.nobroker.in"]').first
        if await photo.count() > 0:
            await photo.click()
            await page.wait_for_timeout(1500)
        urls = await page.evaluate("""() => {
            const urls = new Set();
            document.querySelectorAll('img').forEach(i => {
                if (i.src.includes('images.nobroker.in')) urls.add(i.src);
            });
            document.querySelectorAll('[style]').forEach(el => {
                const m = (el.style.backgroundImage || '').match(/url\\(["']?(https:\\/\\/images\\.nobroker\\.in[^"')]+)/);
                if (m) urls.add(m[1]);
            });
            return Array.from(urls);
        }""")
        return urls
    except Exception:
        return []


async def _scrape_one(context, url: str, property_id: str, idx: int, total: int, sem: asyncio.Semaphore, scrape_images: bool = False) -> tuple[str, ListingDetail | None, list[str]]:
    async with sem:
        _log(f"  [{idx+1}/{total}] {property_id}...")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            text = await page.inner_text("body")
            detail = _parse_detail_from_text(text, property_id)
            images = await _scrape_images(page) if scrape_images else []
            _log(f"  ✓ {property_id}: furnishing={detail.furnishing}, power={detail.power_backup}, floor={detail.floor}, images={len(images)}")
            return property_id, detail, images
        except Exception as e:
            _log(f"  ✗ {property_id}: {e}")
            return property_id, None, []
        finally:
            await page.close()


async def _scrape_details_async(entries: list[dict], with_images: bool = False) -> dict[str, tuple[ListingDetail | None, list[str]]]:
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
        tasks = [_scrape_one(context, url, pid, i, len(urls), sem, scrape_images=with_images) for i, (pid, url) in enumerate(urls)]
        for coro in asyncio.as_completed(tasks):
            pid, detail, images = await coro
            if detail:
                results[pid] = (detail, images)
        await browser.close()

    return results


def scrape_details_playwright(entries: list[dict], with_images: bool = False) -> list[dict]:
    """Scrape detail pages for entries missing detail data. Returns updated entries."""
    urls_needed = [e for e in entries if not e.get("detail") or not e["detail"].get("furnishing")]
    if not urls_needed:
        _log("All entries already have detail data.")
        return entries

    _log(f"=== Detail pages via Playwright ({len(urls_needed)} listings) ===")
    results = asyncio.run(_scrape_details_async(entries, with_images=with_images))

    updated = []
    for entry in entries:
        pid = entry["summary"]["property_id"]
        if pid in results:
            detail, images = results[pid]
            entry["detail"] = detail.model_dump()
            if images:
                entry["summary"]["image_urls"] = images
        updated.append(entry)

    _log(f"  Got details for {len(results)}/{len(urls_needed)} listings")
    return updated


def scrape_images_for_top(entries: list[dict], threshold: float) -> list[dict]:
    """Scrape images only for top-scored, non-disqualified listings."""
    top = [e for e in entries if not e.get("disqualified") and e.get("final_score", 0) >= threshold and not e.get("summary", {}).get("image_urls")]
    if not top:
        _log("No top listings need images.")
        return entries

    _log(f"=== Scraping images for {len(top)} top listings ===")
    urls = [(e["summary"]["property_id"], e["summary"]["detail_url"]) for e in top]

    async def _fetch_images():
        results = {}
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            tasks = []
            for i, (pid, url) in enumerate(urls):
                tasks.append(_scrape_one(context, url, pid, i, len(urls), sem, scrape_images=True))
            for coro in asyncio.as_completed(tasks):
                pid, _, images = await coro
                if images:
                    results[pid] = images
            await browser.close()
        return results

    image_map = asyncio.run(_fetch_images())

    for entry in entries:
        pid = entry["summary"]["property_id"]
        if pid in image_map:
            entry["summary"]["image_urls"] = image_map[pid]
            _log(f"  {pid}: {len(image_map[pid])} images")

    return entries
