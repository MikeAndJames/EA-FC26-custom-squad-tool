import json
from pathlib import Path
import asyncio

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Please install playwright:")
    print("  pip install playwright")
    print("  playwright install chromium")
    exit(1)

ICON_NAMES_JSON = Path("data/icon_names.json")

async def scrape_missing_icons():
    # Load existing known icons
    names_map = {}
    if ICON_NAMES_JSON.exists():
        with open(ICON_NAMES_JSON, "r", encoding="utf-8") as f:
            names_map = json.load(f)
            
    # Load all extracted IDs from player_data's logic or a predefined list
    # We will just scan through names_map to find generic "Icon Legend #ID" values 
    missing_ids = [pid for pid, name in names_map.items() if "Icon Legend" in name or name == ""]
    
    if not missing_ids:
        print("No missing names to scrape! Add IDs as keys to data/icon_names.json with empty values to scrape new ones.")
        return

    print(f"Found {len(missing_ids)} missing names. Starting scraper...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        for pid in missing_ids:
            try:
                # Scrape FUT.gg for the player name
                url = f"https://www.fut.gg/players/{pid}/"
                print(f"Scraping ID {pid}...", end=" ", flush=True)
                
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # Check for 404 or block
                title = await page.title()
                if "404" in title or "Just a moment" in title:
                    print(f"Failed (Title: {title})")
                    continue
                
                # FUT.gg titles are usually "Player Name EA FC 26 Ratings..."
                # Or we can get it from the h1
                h1_locator = page.locator("h1")
                if await h1_locator.count() > 0:
                    real_name = await h1_locator.first.inner_text()
                    # Clean up suffix
                    real_name = real_name.replace(" FC 26", "").replace(" FC 24", "").strip()
                    print(f"Found: {real_name}")
                    names_map[str(pid)] = real_name
                    
                    # Save progressively
                    with open(ICON_NAMES_JSON, "w", encoding="utf-8") as f:
                        json.dump(names_map, f, indent=2, ensure_ascii=False)
                else:
                    print("Failed to find H1 tag.")
                    
            except Exception as e:
                print(f"Error: {e}")
                
            # Be nice to the server
            await asyncio.sleep(2)
            
        await browser.close()
    print("Done scraping!")

if __name__ == "__main__":
    asyncio.run(scrape_missing_icons())
