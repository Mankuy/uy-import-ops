#!/usr/bin/env python3
"""Hunter API - Micro-servicio para buscar productos en Banggood y AliExpress."""
import os, subprocess, json, sqlite3, re
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Hunter API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE = os.path.dirname(os.path.abspath(__file__))
HUNTER_SCRIPT = os.path.join(BASE, "hunter_cdp.py")
PYTHON = os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python")
DB = os.path.join(BASE, "backend", "research.db")

class HunterRequest(BaseModel):
    platform: str = "banggood"
    keywords: str = ""
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    max_products: int = 20


def init_db():
    """Crea la DB y tabla products si no existen."""
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR,
        description TEXT,
        category VARCHAR,
        source_url VARCHAR,
        image_url VARCHAR,
        product_cost_usd FLOAT,
        shipping_cost_usd FLOAT DEFAULT 0,
        hs_code VARCHAR DEFAULT '',
        tariff_rate FLOAT DEFAULT 0,
        iva_rate FLOAT DEFAULT 22,
        stat_fee_rate FLOAT DEFAULT 0,
        agent_fee_usd FLOAT DEFAULT 0,
        total_landed_cost_uyu FLOAT DEFAULT 0,
        price_cost_plus_uyu FLOAT DEFAULT 0,
        price_value_uyu FLOAT DEFAULT 0,
        price_aggressive_uyu FLOAT DEFAULT 0,
        price_luxury_uyu FLOAT DEFAULT 0,
        price_extreme_uyu FLOAT DEFAULT 0,
        price_premium_vs_comp_uyu FLOAT DEFAULT 0,
        margin_cost_plus FLOAT DEFAULT 0,
        margin_value FLOAT DEFAULT 0,
        margin_aggressive FLOAT DEFAULT 0,
        margin_luxury FLOAT DEFAULT 0,
        margin_extreme FLOAT DEFAULT 0,
        margin_premium_vs_comp FLOAT DEFAULT 0,
        status VARCHAR DEFAULT 'new',
        ml_competitor_price FLOAT,
        ml_competitor_url VARCHAR,
        demand_score INTEGER DEFAULT 50,
        opportunity_score INTEGER,
        best_strategy VARCHAR,
        best_margin FLOAT,
        notes TEXT,
        created_at DATETIME,
        updated_at DATETIME
    )""")
    conn.commit()
    conn.close()

init_db()
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "hunter-api"}

@app.post("/api/hunter/search")
def hunter_search(req: HunterRequest):
    cmd = [PYTHON, HUNTER_SCRIPT, req.platform]
    if req.keywords:
        cmd.append(req.keywords)
    if req.min_price is not None:
        cmd.append(str(req.min_price))
    if req.max_price is not None:
        cmd.append(str(req.max_price))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=BASE)
        json_path = os.path.join(BASE, "hunter_products.json")
        products = []
        if os.path.exists(json_path):
            with open(json_path) as f:
                products = json.load(f)
        products = products[:req.max_products]
        return {"added": len(products), "platform": req.platform, "keywords": req.keywords, "products": products, "success": result.returncode == 0}
    except subprocess.TimeoutExpired:
        return {"added": 0, "error": "Timeout (90s)", "success": False}
    except Exception as e:
        return {"added": 0, "error": str(e), "success": False}

@app.get("/api/hunter/products")
def get_hunter_products(status: str = None, limit: int = 50):
    conn = sqlite3.connect(DB)
    query = "SELECT id, name, source_url, image_url, product_cost_usd, status, created_at FROM products"
    params = []
    if status:
        query += " WHERE status LIKE ?"
        params.append(f"hunter_%")
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
    r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
    m = re.search(r"via\s+([\d.]+)", r.stdout)
    gw = m.group(1) if m else "unknown"
    cdp_ok = False
    try:
        result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://{gw}:9223/json/version", "--connect-timeout", "3"], capture_output=True, text=True, timeout=5)
        cdp_ok = result.stdout.strip() == "200"
    except:
        pass
    return {"aliexpress_cdp": cdp_ok, "banggood_auto": True, "gateway_ip": gw}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

# Servir frontend estático
STATIC_DIR = os.path.join(BASE, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
