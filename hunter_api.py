#!/usr/bin/env python3
"""Hunter API v2 - Banggood (Playwright with HTTP fallback) + AliExpress CDP."""
import os, subprocess, json, sqlite3, re
from datetime import datetime
from urllib.parse import quote_plus
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Hunter API", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "backend", "research.db")
JSON_OUT = os.path.join(BASE, "hunter_products.json")

class HunterRequest(BaseModel):
    platform: str = "banggood"
    keywords: str = ""
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    max_products: int = 20

def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR, description TEXT, category VARCHAR,
        source_url VARCHAR, image_url VARCHAR,
        product_cost_usd FLOAT, shipping_cost_usd FLOAT DEFAULT 0,
        hs_code VARCHAR DEFAULT '', tariff_rate FLOAT DEFAULT 0,
        iva_rate FLOAT DEFAULT 22, stat_fee_rate FLOAT DEFAULT 0,
        agent_fee_usd FLOAT DEFAULT 0,
        total_landed_cost_uyu FLOAT DEFAULT 0,
        price_cost_plus_uyu FLOAT DEFAULT 0, price_value_uyu FLOAT DEFAULT 0,
        price_aggressive_uyu FLOAT DEFAULT 0, price_luxury_uyu FLOAT DEFAULT 0,
        price_extreme_uyu FLOAT DEFAULT 0, price_premium_vs_comp_uyu FLOAT DEFAULT 0,
        margin_cost_plus FLOAT DEFAULT 0, margin_value FLOAT DEFAULT 0,
        margin_aggressive FLOAT DEFAULT 0, margin_luxury FLOAT DEFAULT 0,
        margin_extreme FLOAT DEFAULT 0, margin_premium_vs_comp FLOAT DEFAULT 0,
        status VARCHAR DEFAULT 'new',
        ml_competitor_price FLOAT, ml_competitor_url VARCHAR,
        demand_score INTEGER DEFAULT 50, opportunity_score INTEGER,
        best_strategy VARCHAR, best_margin FLOAT, notes TEXT,
        created_at DATETIME, updated_at DATETIME
    )""")
    conn.commit()
    conn.close()

init_db()

def insert_db(product):
    try:
        conn = sqlite3.connect(DB)
        now = datetime.utcnow().isoformat()
        title = product["title"][:150]
        url = product["url"]
        img = product.get("image_url", "")
        price = product["price_usd"]
        platform = product.get("platform", "banggood")
        existing = conn.execute("SELECT id FROM products WHERE source_url=?", (url,)).fetchone()
        if existing:
            conn.execute("UPDATE products SET name=?, image_url=?, product_cost_usd=?, updated_at=? WHERE id=?",
                (title, img, price, now, existing[0]))
        else:
            conn.execute("INSERT INTO products (name,source_url,image_url,product_cost_usd,status,demand_score,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (title, url, img, price, f"hunter_{platform}", 50, now, now))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  DB ERROR: {e}")
        return False

def hunt_banggood_sync(keywords, min_price=None, max_price=None, max_products=20):
    """Scrapea Banggood con Playwright (headless Chromium)."""
    PYTHON = sys.executable
    scraper = os.path.join(BASE, "scrape_banggood.py")
    cmd = [PYTHON, scraper, keywords]
    if min_price is not None: cmd.append(str(min_price))
    if max_price is not None: cmd.append(str(max_price))
    cmd.append(str(max_products))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=BASE)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception as e:
        print(f"  BG error: {e}")
    return []

def hunt_aliexpress_cdp(keywords=None, min_price=None, max_price=None):
    HUNTER_SCRIPT = os.path.join(BASE, "hunter_cdp.py")
    PYTHON = os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python") if os.path.exists(os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python")) else "python3"
    if not os.path.exists(HUNTER_SCRIPT):
        return []
    cmd = [PYTHON, HUNTER_SCRIPT, "aliexpress"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=BASE)
        json_path = os.path.join(BASE, "hunter_products.json")
        if os.path.exists(json_path):
            with open(json_path) as f:
                return json.load(f)
    except:
        pass
    return []

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "hunter-api"}

@app.post("/api/hunter/search")
def hunter_search(req: HunterRequest):
    all_results = []
    if req.platform in ("banggood", "bg", "all"):
        products = hunt_banggood_sync(req.keywords, req.min_price, req.max_price, req.max_products)
        for p in products:
            insert_db(p)
            all_results.append(p)
    if req.platform in ("aliexpress", "ae", "all"):
        products = hunt_aliexpress_cdp(req.keywords, req.min_price, req.max_price)
        for p in products:
            insert_db(p)
            all_results.append(p)
    if all_results:
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
    return {"added": len(all_results), "platform": req.platform, "keywords": req.keywords, "products": all_results, "success": True}

@app.get("/api/hunter/products")
def get_hunter_products(status: str = None, limit: int = 50):
    conn = sqlite3.connect(DB)
    query = "SELECT id, name, source_url, image_url, product_cost_usd, status, created_at FROM products"
    params = []
    if status:
        query += " WHERE status LIKE ?"
        params.append("hunter_%")
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "url": r[2], "image": r[3], "price_usd": r[4], "status": r[5], "created": r[6]} for r in rows]

@app.delete("/api/hunter/products/{pid}")
def delete_product(pid: int):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return {"deleted": True}

@app.get("/api/hunter/status")
def hunter_status():
    return {"banggood_auto": True, "aliexpress_cdp": False, "note": "CDP only works locally"}

STATIC_DIR = os.path.join(BASE, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
