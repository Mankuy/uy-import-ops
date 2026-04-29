#!/usr/bin/env python3
"""Hunter Service v2 — Clean, self-contained product scraper."""
import os, re, json, sqlite3
from datetime import datetime
from urllib.parse import quote_plus

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx

app = FastAPI(title="Hunter API v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "hunter.db")

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, source_url TEXT, image_url TEXT,
            product_cost_usd REAL, source TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
        c.commit()

init_db()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"}

# ─── Banggood Scraper (pure HTTP, no browser) ───
async def scrape_banggood(keywords: str, min_price=None, max_price=None, max_products=20):
    results = []
    query = quote_plus(keywords)
    url = f"https://www.banggood.com/search/{query}.html"
    
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30.0) as c:
        try:
            r = await c.get(url)
            html = r.text
        except Exception as e:
            return {"error": f"Banggood request failed: {e}", "products": []}
        
        # Find product links with titles
        links = re.findall(
            r'href="(https://(?:www\.)?banggood\.com/[^"]*-p-\d+[^"]*)"[^>]*title="([^"]+)"',
            html
        )
        
        if not links:
            # Fallback: try finding links differently
            links_raw = re.findall(
                r'<a[^>]*href="(https://(?:www\.)?banggood\.com/[^"]*-p-\d+[^"]*)"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )
            links = [(url, re.sub(r'<[^>]+>', '', title).strip()) for url, title in links_raw]
        
        for prod_url, title in links:
            if len(results) >= max_products:
                break
            
            # Extract price from the product page or surrounding HTML
            price = 0.0
            pid_match = re.search(r'-p-(\d+)', prod_url)
            pid = pid_match.group(1) if pid_match else "?"
            
            # Try to find price near the link
            context_start = max(0, html.find(prod_url) - 2000)
            context_end = min(len(html), html.find(prod_url) + 3000)
            context = html[context_start:context_end]
            
            # Multiple price patterns
            for pat in [
                r'US\$(\d+\.?\d*)',
                r'price["\s:]+(\d+\.?\d*)',
                r'"price":\s*"?(\d+\.?\d*)',
                r'data-price="(\d+\.?\d*)"',
                r'<span[^>]*class="[^"]*price[^"]*"[^>]*>[^$]*\$?(\d+\.?\d*)',
            ]:
                m = re.search(pat, context)
                if m:
                    try:
                        price = float(m.group(1))
                        break
                    except:
                        pass
            
            # Try fetching product page for price
            if price == 0.0:
                try:
                    pr = await c.get(prod_url.split("?")[0], timeout=10.0)
                    for pat in [
                        r'US\$(\d+\.?\d*)',
                        r'"price":\s*"?(\d+\.?\d*)',
                        r'data-price="(\d+\.?\d*)"',
                    ]:
                        m = re.search(pat, pr.text)
                        if m:
                            try:
                                price = float(m.group(1))
                                break
                            except:
                                pass
                except:
                    pass
            
            # Filter by price
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue
            
            # Clean title
            title_clean = re.sub(r'<[^>]+>', '', title).strip()[:200]
            
            results.append({
                "product_id": pid,
                "url": prod_url.split("?")[0],
                "title": title_clean,
                "price_usd": round(price, 2),
                "image_url": "",
                "source": "banggood",
                "platform": "banggood"
            })
        
        # Save to DB
        with sqlite3.connect(DB_PATH) as conn:
            for prod in results:
                try:
                    conn.execute(
                        """INSERT OR REPLACE INTO products 
                        (name, source_url, product_cost_usd, source, status, updated_at)
                        VALUES (?,?,?,?,'hunter_new',?)""",
                        (prod["title"], prod["url"], prod["price_usd"], prod["source"], datetime.utcnow().isoformat())
                    )
                except:
                    pass
            conn.commit()
        
        return {
            "added": len(results),
            "keywords": keywords,
            "source": "banggood",
            "products": results,
            "success": True
        }

# ─── API Endpoints ───
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "hunter-v2", "time": datetime.utcnow().isoformat()}

@app.post("/api/hunter/search")
async def hunter_search(request: Request):
    try:
        body = await request.json()
    except:
        body = {}
    
    keywords = body.get("keywords", "")
    if not keywords:
        return JSONResponse({"error": "keywords required", "success": False}, status_code=400)
    
    min_price = body.get("min_price")
    max_price = body.get("max_price")
    max_products = body.get("max_products", 20)
    source = body.get("source", "banggood")  # banggood is the only HTTP source
    
    if source == "banggood":
        result = await scrape_banggood(keywords, min_price, max_price, max_products)
    else:
        return JSONResponse({"error": f"Source '{source}' not available via HTTP", "success": False}, status_code=400)
    
    return result

@app.get("/api/products")
def list_products(limit: int = 20, offset: int = 0):
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT * FROM products ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/stats")
def stats():
    with sqlite3.connect(DB_PATH) as c:
        total = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        avg_price = c.execute("SELECT AVG(product_cost_usd) FROM products WHERE product_cost_usd > 0").fetchone()[0] or 0
        by_source = c.execute("SELECT source, COUNT(*) FROM products GROUP BY source").fetchall()
        return {
            "total_products": total,
            "avg_price_usd": round(avg_price, 2),
            "by_source": {s: c for s, c in by_source}
        }

# ─── Static Frontend ───
STATIC_DIR = os.path.join(BASE, "static")
if os.path.exists(os.path.join(STATIC_DIR, "index.html")):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
