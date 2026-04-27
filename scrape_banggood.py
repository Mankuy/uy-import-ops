#!/usr/bin/env python3
"""Mini scraper Banggood con Playwright."""
import sys, json, re, os
from urllib.parse import quote_plus

async def scrape():
    from playwright.async_api import async_playwright
    keywords = sys.argv[1] if len(sys.argv) > 1 else "phone case"
    min_price = float(sys.argv[2]) if len(sys.argv) > 2 else None
    max_price = float(sys.argv[3]) if len(sys.argv) > 3 else None
    max_products = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        query = quote_plus(keywords)
        await page.goto(f"https://www.banggood.com/search/{query}.html", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        
        results = []
        products = await page.evaluate("""() => {
            const prices = document.querySelectorAll('span.price');
            const out = [];
            for (const priceEl of prices) {
                const txt = priceEl.textContent.trim();
                const m = txt.match(/[\\d,.]+/);
                if (!m) continue;
                let container = priceEl;
                let link = null, titleEl = null, imgEl = null;
                for (let i = 0; i < 15; i++) {
                    container = container.parentElement;
                    if (!container) break;
                    if (!link) { const a = container.querySelector('a[href]'); if (a && a.href.includes('banggood.com') && !a.href.includes('/search')) link = a; }
                    if (!titleEl) { const t = container.querySelector('a[title]'); if (t) titleEl = t; }
                    if (!imgEl) { const img = container.querySelector('img[src*="imgaz"]'); if (img) imgEl = img; }
                }
                if (link) {
                    out.push({url: link.href.split('?')[0], title: titleEl ? titleEl.getAttribute('title') : link.textContent.trim().substring(0,150), price: parseFloat(m[0].replace(/,/g,'')), image: imgEl ? imgEl.src : ''});
                }
            }
            return out;
        }""")
        
        for p_data in products:
            if min_price is not None and p_data["price"] < min_price: continue
            if max_price is not None and p_data["price"] > max_price: continue
            pid = re.search(r"/p-(\\d+)", p_data["url"])
            results.append({
                "product_id": pid.group(1) if pid else "?",
                "url": p_data["url"],
                "title": p_data["title"][:150],
                "price_usd": p_data["price"],
                "image_url": p_data["image"],
                "source": "banggood-pw",
                "platform": "banggood",
            })
            if len(results) >= max_products: break
        
        await browser.close()
        print(json.dumps(results))

if __name__ == "__main__":
    import asyncio
    asyncio.run(scrape())
