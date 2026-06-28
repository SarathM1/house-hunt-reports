"""Generate a PDF report of top listings using Playwright."""
import asyncio
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "pdf_template.html"


def generate_pdf(scored_path: Path, out_path: Path, threshold: float = 75) -> Path:
    entries = json.loads(scored_path.read_text())
    qualified = [e for e in entries if not e["disqualified"] and e["final_score"] >= threshold]
    qualified.sort(key=lambda x: x["final_score"], reverse=True)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template(TEMPLATE_NAME)
    html = template.render(entries=qualified, threshold=threshold)

    async def _render():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            await page.pdf(path=str(out_path), format="A4", margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"})
            await browser.close()

    asyncio.run(_render())
    print(f"PDF: {out_path} ({len(qualified)} listings)", flush=True)
    return out_path
