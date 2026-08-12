"""
sofifa_player_preview.py
-------------------------
Pick-a-player preview tool for EA FC 26, via SoFIFA.
Fetches FULL attributes + PlayStyles for ONE player at a time,
using a headless browser to clear SoFIFA's Cloudflare check.

This is a STARTING POINT, not a finished tool — the first run is
diagnostic. SoFIFA blocks non-browser requests entirely, so I couldn't
inspect its live page structure myself. Run this once against a known
player, look at what gets printed, and adjust the extraction path.

Usage:
    python sofifa_player_preview.py https://sofifa.com/player/248280/isaac-vanmalsawma/260044/
    python sofifa_player_preview.py 248280

Requires:
    pip install playwright --break-system-packages
    playwright install chromium
"""
import asyncio
import json
import re
import sys
from playwright.async_api import async_playwright

BASE_URL = "https://sofifa.com/player/{id}"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


async def fetch_player(url_or_id: str, max_retries: int = 5) -> dict:
    url = url_or_id if url_or_id.startswith("http") else BASE_URL.format(id=url_or_id)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        # Skip images/fonts/css — we only need the HTML/JSON payload.
        await page.route(
            re.compile(r"\.(png|jpg|jpeg|css|woff2?)$"), lambda r: r.abort()
        )

        html = ""
        for attempt in range(max_retries):
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            if "just a moment" not in html.lower() and "cf-challenge" not in html.lower():
                break
            print(f"  Cloudflare challenge, retrying ({attempt + 1}/{max_retries})...")
            await asyncio.sleep(10)
        else:
            await browser.close()
            raise RuntimeError("Cloudflare challenge never cleared — try non-headless mode.")

        await browser.close()

    # Preferred path: pull the embedded Next.js JSON (if sofifa is Next.js-based,
    # this will be far more stable than scraping visible DOM elements).
    match = NEXT_DATA_RE.search(html)
    if match:
        try:
            data = json.loads(match.group(1))
            return {"source": "__NEXT_DATA__", "data": data.get("props", data)}
        except json.JSONDecodeError:
            pass

    # Fallback: no JSON blob found — hand back raw HTML so you can find
    # the right selectors by hand (view-source / dev tools), the same way
    # prashantghimire/sofifa-web-scraper's PlayerScraper class does it.
    return {"source": "raw_html", "html_length": len(html), "html_snippet": html[:2000]}


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "248280"
    print(f"Fetching {target}...")
    result = asyncio.run(fetch_player(target))
    print(json.dumps(result, indent=2, ensure_ascii=False)[:4000])