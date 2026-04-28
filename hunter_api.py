#!/usr/bin/env python3
"""Hunter API - Microservicio para buscar productos. Sirve frontend + API + hunter."""
import os, json, re, subprocess
from datetime import datetime
from urllib.parse import quote_plus
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Hunter Dashboard", version="5.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE, "backend")
DB = os.path.join(DB_DIR, "research.db")
os.makedirs(DB_DIR, exist_ok=True)

# ─── DB Init ───
import sqlite3
conn = sqlite3.connect(DB)
conn.execute("""CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR, source_url VARCHAR, image_url VARCHAR,
    product_cost_usd FLOAT, status VARCHAR DEFAULT 'new',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)""")
conn.commit()
conn.close()

# ─── API ───
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "hunter-dashboard"}

@app.post("/api/hunter/search")
async def hunter_search(request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    kw = body.get("keywords", "phone case")
    mn = body.get("min_price")
    mx = body.get("max_price")
    mp = body.get("max_products", 20)
    
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as c:
        query = quote_plus(kw)
        r = await c.get(f"https://www.banggood.com/search/{query}.html")
        html = r.text
        links = re.findall(r'href="(https://www\\.banggood\\.com/[^"]*-p-\\d+[^"]*)"[^>]*title="([^"]+)"', html)
        results = []
        for url, title in links:
            if len(results) >= mp: break
            pid = re.search(r"-p-(\\d+)", url)
            price = 0.0
            try:
                pr = await c.get(url.split("?")[0], timeout=10.0)
                for pat in [r'Solo US\\$([\\d,.]+)', r'US\\$([\\d]+\\.[\\d]{2})']:
                    m = re.search(pat, pr.text)
                    if m:
                        try: price = float(m.group(1).replace(",","")); break
                        except: pass
            except: pass
            if mn is not None and price < mn: continue
            if mx is not None and price > mx: continue
            
            # Save to DB
            try:
                conn_db = sqlite3.connect(DB)
                conn_db.execute("INSERT OR REPLACE INTO products (name, source_url, product_cost_usd, status, updated_at) VALUES (?,?,?,'hunter_new',?)",
                    (title[:150], url.split("?")[0], price, datetime.utcnow().isoformat()))
                conn_db.commit()
                conn_db.close()
            except: pass
            
            results.append({"product_id": pid.group(1) if pid else "?", "url": url.split("?")[0],
                "title": title[:150], "price_usd": price, "image_url": "", "source": "banggood", "platform": "banggood"})
        return {"added": len(results), "keywords": kw, "products": results, "success": True}

# ─── Static frontend ───
STATIC = os.path.join(BASE, "static")
if os.path.exists(STATIC):
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
