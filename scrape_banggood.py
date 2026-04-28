#!/usr/bin/env python3
"""Banggood scraper HTTP-only. Sin Playwright."""
import sys, json, re, asyncio
from urllib.parse import quote_plus
import httpx

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"}

PRICE_PATTERNS = [
    r'Solo US\$([\d,.]+)',
    r'<span[^>]*price[^>]*>[^<]*US\$([\d,.]+)',
    r'US\$([\d]+\.[\d]{2})',
]

async def get_price(client, url):
    try:
        r = await client.get(url, timeout=10.0)
        for pat in PRICE_PATTERNS:
            m = re.search(pat, r.text)
            if m:
                try: return float(m.group(1).replace(",", ""))
                except: pass
    except: pass
    return 0.0

async def search(keywords: str, min_price=None, max_price=None, max_products=20):
    query = quote_plus(keywords)
    url = f"https://www.banggood.com/search/{query}.html"
    
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        r = await client.get(url, timeout=15.0)
        products = re.findall(r'href="(https://www\.banggood\.com/[^"]*-p-\d+[^"]*)"[^>]*title="([^"]+)"', r.text)
        
        results = []
        tasks = []
        for prod_url, title in products:
            if len(results) >= max_products: break
            p_id = re.search(r"-p-(\d+)", prod_url)
            pid = p_id.group(1) if p_id else "?"
            price = await get_price(client, prod_url.split("?")[0])
            if min_price is not None and price < min_price: continue
            if max_price is not None and price > max_price: continue
            img = re.search(r'src="(https://imgaz[^"]+)"', r.text[:r.text.find(prod_url)+5000] + r.text)
            results.append({
                "product_id": pid, "url": prod_url.split("?")[0], "title": title[:150],
                "price_usd": price, "image_url": img.group(1) if img else "",
                "source": "banggood-http", "platform": "banggood"
            })
        return results

if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "phone case"
    mn = float(sys.argv[2]) if len(sys.argv) > 2 else None
    mx = float(sys.argv[3]) if len(sys.argv) > 3 else None
    mp = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    res = asyncio.run(search(kw, mn, mx, mp))
    print(json.dumps(res))
