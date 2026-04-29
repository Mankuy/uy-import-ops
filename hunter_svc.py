#!/usr/bin/env python3
"""Hunter Service v3 — Complete product sourcing & import calculator."""
import os, re, json, sqlite3, hashlib, math
from datetime import datetime
from urllib.parse import quote_plus

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx

app = FastAPI(title="UY Import Ops — Product Sourcing")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "hunter.db")
IMAGE_DIR = os.path.join(BASE, "static", "products")
os.makedirs(IMAGE_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

# ═══════════════ DB ═══════════════
def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, source_url TEXT, image_url TEXT,
            product_cost_usd REAL, shipping_est REAL,
            source TEXT, category TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS ml_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER, ml_url TEXT, ml_title TEXT,
            ml_price_uyu REAL, ml_price_usd REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        c.commit()
init_db()

# ═══════════════ NICHES ═══════════════
NICHES = [
    {"id":"tech","name":"Tecnología","subcategories":["auriculares bluetooth","smartwatch","cargador inalambrico","parlante portatil","power bank","lampara led","proyector","camara seguridad wifi","teclado mecanico","mouse gamer"],"demand":"alta","margin":"medio"},
    {"id":"hogar","name":"Hogar Inteligente","subcategories":["lampara led recargable","difusor aromas","aspiradora robot","organizador cocina","balanza digital","termo electrico","ventilador portatil","humidificador","tira led","enchufe inteligente"],"demand":"alta","margin":"alto"},
    {"id":"fitness","name":"Fitness","subcategories":["banda elastica","yoga mat","botella agua inteligente","masajeador muscular","cuerda saltar","reloj deportivo","pesas ajustables","rodillo abdominal"],"demand":"media","margin":"alto"},
    {"id":"accesorios","name":"Accesorios Móvil","subcategories":["funda iphone","cable usb c","cargador rapido","soporte auto","protector pantalla","ring holder","cargador auto","adaptador lightning","hub usb c"],"demand":"alta","margin":"alto"},
    {"id":"belleza","name":"Belleza","subcategories":["cepillo electrico","alisador pelo","secador pelo","depiladora laser","lampara uv uñas","espejo aumento","limpiador facial","rizador pestañas"],"demand":"alta","margin":"alto"},
    {"id":"mascotas","name":"Mascotas","subcategories":["bebedero automatico","comedero automatico","cama perro","collar gps","juguete interactivo","arnes reflectante"],"demand":"alta","margin":"medio"},
    {"id":"auto","name":"Acc. Auto","subcategories":["dash cam","soporte celular auto","aspiradora auto","inflador neumaticos","led interior","espejo retrovisor camara","cargador auto rapido"],"demand":"media","margin":"alto"}
]

# English translations for trending subcategories (Banggood is in English)
NICHES_EN = {
    "auriculares bluetooth": "bluetooth earphone",
    "smartwatch": "smart watch",
    "cargador inalambrico": "wireless charger",
    "parlante portatil": "portable speaker",
    "power bank": "power bank",
    "lampara led": "led lamp",
    "proyector": "projector",
    "camara seguridad wifi": "wifi security camera",
    "teclado mecanico": "mechanical keyboard",
    "mouse gamer": "gaming mouse",
    "lampara led recargable": "rechargeable led lamp",
    "difusor aromas": "aroma diffuser",
    "aspiradora robot": "robot vacuum",
    "organizador cocina": "kitchen organizer",
    "balanza digital": "digital scale",
    "termo electrico": "electric kettle",
    "ventilador portatil": "portable fan",
    "humidificador": "humidifier",
    "tira led": "led strip",
    "enchufe inteligente": "smart plug",
    "banda elastica": "resistance band",
    "yoga mat": "yoga mat",
    "botella agua inteligente": "smart water bottle",
    "masajeador muscular": "muscle massager",
    "cuerda saltar": "jump rope",
    "reloj deportivo": "sports watch",
    "pesas ajustables": "adjustable dumbbell",
    "rodillo abdominal": "ab roller",
    "funda iphone": "iphone case",
    "cable usb c": "usb c cable",
    "cargador rapido": "fast charger",
    "soporte auto": "car phone holder",
    "protector pantalla": "screen protector",
    "ring holder": "ring holder",
    "cargador auto": "car charger",
    "adaptador lightning": "lightning adapter",
    "hub usb c": "usb c hub",
    "cepillo electrico": "electric toothbrush",
    "alisador pelo": "hair straightener",
    "secador pelo": "hair dryer",
    "depiladora laser": "laser hair removal",
    "lampara uv uñas": "uv nail lamp",
    "espejo aumento": "magnifying mirror",
    "limpiador facial": "facial cleanser",
    "rizador pestañas": "eyelash curler",
    "bebedero automatico": "automatic water dispenser",
    "comedero automatico": "automatic feeder",
    "cama perro": "dog bed",
    "collar gps": "gps tracker",
    "juguete interactivo": "interactive toy",
    "arnes reflectante": "reflective harness",
    "dash cam": "dash cam",
    "soporte celular auto": "car phone mount",
    "aspiradora auto": "car vacuum",
    "inflador neumaticos": "tire inflator",
    "led interior": "interior led light",
    "espejo retrovisor camara": "rear view mirror camera",
    "cargador auto rapido": "fast car charger",
}

# ═══════════════ IMPORT CALC ═══════════════
RATES = {
    "tecnologia":{"tariff":0.02,"iva":0.22,"handling":15},
    "hogar":{"tariff":0.10,"iva":0.22,"handling":15},
    "belleza":{"tariff":0.14,"iva":0.22,"handling":15},
    "fitness":{"tariff":0.14,"iva":0.22,"handling":15},
    "mascotas":{"tariff":0.14,"iva":0.22,"handling":15},
    "auto":{"tariff":0.14,"iva":0.22,"handling":15},
    "accesorios":{"tariff":0.10,"iva":0.22,"handling":15},
    "default":{"tariff":0.14,"iva":0.22,"handling":15}
}

def calc_import(cost, ship=3, cat="default", qty=1, ship_total=0):
    r = RATES.get(cat, RATES["default"])
    tc = cost * qty
    s = ship_total if ship_total > 0 else ship * qty
    cif = tc + s + tc * 0.01
    tariff = cif * r["tariff"]
    iva = (cif + tariff) * r["iva"]
    handling = r["handling"]
    total = cif + tariff + iva + handling
    cpu = total / qty if qty else 0
    return {
        "cost_usd": round(cost,2), "quantity": qty,
        "cif_usd": round(cif,2), "tariff_usd": round(tariff,2),
        "iva_usd": round(iva,2), "handling_usd": handling,
        "shipping_usd": round(s,2), "total_usd": round(total,2),
        "cost_per_unit": round(cpu,2),
        "tariff_rate": f"{r['tariff']*100:.0f}%", "iva_rate": "22%",
        "usd_uyu": 43, "total_uyu": round(total*43), "cpu_uyu": round(cpu*43)
    }

# ═══════════════ SCRAPER ═══════════════
CAT_KW = {
    "tecnologia":["auricular","bluetooth","smartwatch","parlante","cargador","power bank","lampara","proyector","camara","teclado","mouse","gamer"],
    "hogar":["lampara","difusor","aspiradora","organizador","balanza","termo","ventilador","humidificador","enchufe","tira led"],
    "fitness":["ejercicio","yoga","botella","masajeador","cuerda","reloj","pesas","rodillo"],
    "belleza":["cepillo","alisador","secador","depiladora","lampara uv","espejo","facial","rizador"],
    "mascotas":["perro","gato","mascota","bebedero","comedero","collar","juguete","arnes"],
    "auto":["dash cam","soporte","inflador","retrovisor","auto"],
    "accesorios":["funda","cable","protector","popsocket","ring holder","adaptador","hub"]
}

def detect_cat(title):
    t = title.lower()
    for cat, kws in CAT_KW.items():
        if any(kw in t for kw in kws): return cat
    return "default"

async def scrape_bg(keywords, min_price=None, max_price=None, max_products=20):
    results = []
    q = quote_plus(keywords)
    url = f"https://www.banggood.com/search/{q}.html"
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30.0) as c:
        try:
            r = await c.get(url)
            html = r.text
        except Exception as e:
            return {"error": str(e), "products": [], "success": False}
        
        # Extract product links with titles
        links = re.findall(
            r'href="(https://(?:www\.)?banggood\.com/[^"]*-p-\d+[^"]*)"[^>]*title="([^"]+)"',
            html
        )
        if not links:
            links_raw = re.findall(r'href="(https://(?:www\.)?banggood\.com/[^"]*-p-\d+[^"]*)"', html)
            links = [(u, u.split("/")[-1].replace("-", " ").title()) for u in links_raw]
        
        for prod_url, title in links:
            if len(results) >= max_products: break
            
            prod_url = prod_url.split("?")[0]
            title = re.sub(r'<[^>]+>', '', title).strip()[:200]
            
            # Extract price from context - try multiple methods
            price = 0.0
            idx = html.find(prod_url)
            ctx = html[max(0,idx-4000):min(len(html),idx+4000)]
            
            # More aggressive price patterns
            price_pats = [
                r'US\$\s*(\d+\.?\d*)',
                r'\$\s*(\d+\.?\d{2})',
                r'"price":\s*"?(\d+\.?\d*)',
                r'data-price="(\d+\.?\d*)"',
                r'data-sale-price="(\d+\.?\d*)"',
                r'price.*?(\d+\.\d{2})',
                r'<span[^>]*class="[^"]*price[^"]*"[^>]*>[^<]*(\d+\.?\d*)',
            ]
            for pat in price_pats:
                m = re.search(pat, ctx, re.IGNORECASE)
                if m:
                    try:
                        pv = float(m.group(1))
                        if 0.01 < pv < 10000:  # Sanity check
                            price = pv; break
                    except: pass
            
            # Try product page as fallback (with better patterns)
            if price == 0.0:
                try:
                    pr = await c.get(prod_url, timeout=6.0)
                    for pat in [
                        r'US\$\s*(\d+\.?\d*)',
                        r'"price":\s*"?(\d+\.?\d*)',
                        r'"productPrice":\s*"?(\d+\.?\d*)',
                        r'"salePrice":\s*"?(\d+\.?\d*)',
                        r'"originalPrice":\s*"?\$?(\d+\.?\d*)',
                        r'<span[^>]*class="[^"]*price[^"]*"[^>]*>[^<]*\$\s*(\d+\.?\d*)',
                    ]:
                        m = re.search(pat, pr.text, re.IGNORECASE)
                        if m:
                            try:
                                pv = float(m.group(1))
                                if 0.01 < pv < 10000:
                                    price = pv; break
                            except: pass
                except: pass
            
            if min_price is not None and price < min_price: continue
            if max_price is not None and price > max_price: continue
            
            img = ""
            for p in [
                r'src="(https://[^"]*imgaz[^"]*\.(?:jpg|jpeg|png|webp))"',
                r'data-src="(https://[^"]*\.(?:jpg|jpeg|png|webp))"',
                r'src="(https://[^"]*\.(?:jpg|jpeg|png|webp))"',
                r'<img[^>]*src="(https://[^"]*\.(?:jpg|jpeg|png|webp))"',
            ]:
                m = re.search(p, ctx, re.IGNORECASE)
                if m:
                    candidate = m.group(1)
                    if 'icon' not in candidate.lower() and 'logo' not in candidate.lower():
                        img = candidate; break
            
            pid = re.search(r'-p-(\d+)', prod_url)
            
            results.append({
                "product_id": pid.group(1) if pid else "?",
                "url": prod_url, "title": title,
                "price_usd": round(price, 2), "image_url": img,
                "source": "banggood", "category": detect_cat(title)
            })
        
        # Save to DB
        with sqlite3.connect(DB_PATH) as conn:
            for p in results:
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO products (name,source_url,image_url,product_cost_usd,source,category,status,updated_at) VALUES (?,?,?,?,?,?,'hunter_new',?)",
                        (p["title"][:150], p["url"], p.get("image_url",""), p["price_usd"], p["source"], p["category"], datetime.utcnow().isoformat()))
                except: pass
            conn.commit()
        
        return {"added": len(results), "keywords": keywords, "source": "banggood", "products": results, "success": True}

# ═══════════════ API ═══════════════
@app.get("/api/health")
def health():
    with sqlite3.connect(DB_PATH) as c:
        total = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    return {"status":"ok","service":"hunter-v3","total_products":total,"time":datetime.utcnow().isoformat()}

@app.post("/api/hunter/search")
async def hunter_search(request: Request):
    try: body = await request.json()
    except: body = {}
    kw = body.get("keywords","").strip()
    import random
    
    # If no keywords, try up to 5 random trending keywords until we find products
    if not kw:
        all_subs = []
        for n in NICHES:
            all_subs.extend(n["subcategories"])
        random.shuffle(all_subs)
        candidates = all_subs[:10] if len(all_subs) >= 10 else all_subs
        
        for candidate in candidates[:3]:
            en_kw = NICHES_EN.get(candidate, candidate)
            result = await scrape_bg(en_kw, body.get("min_price"), body.get("max_price"), body.get("max_products",20))
            if result.get("added", 0) > 0:
                result["keywords"] = candidate
                result["searched_as"] = en_kw
                return result
        
        return {"added": 0, "keywords": "varios", "products": [], "success": True, "message": "No se encontraron productos en ese rango de precio. Amplia el rango o usa palabras clave en ingles."}
    
    # User provided keywords - try English first
    en_kw = NICHES_EN.get(kw, kw)
    result = await scrape_bg(en_kw, body.get("min_price"), body.get("max_price"), body.get("max_products",20))
    if result.get("added", 0) > 0:
        result["searched_as"] = en_kw
        return result
    # Try original Spanish
    if en_kw != kw:
        result = await scrape_bg(kw, body.get("min_price"), body.get("max_price"), body.get("max_products",20))
        result["searched_as"] = kw
        return result
    result["searched_as"] = en_kw
    return result

@app.get("/api/products")
def products(limit:int=50, offset:int=0, source:str=None, category:str=None):
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        q = "SELECT * FROM products WHERE 1=1"
        params = []
        if source: q += " AND source=?"; params.append(source)
        if category: q += " AND category=?"; params.append(category)
        q += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in c.execute(q, params).fetchall()]

@app.get("/api/stats")
def stats():
    with sqlite3.connect(DB_PATH) as c:
        total = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        avg = c.execute("SELECT AVG(product_cost_usd) FROM products WHERE product_cost_usd>0").fetchone()[0] or 0
        src = {r[0]:r[1] for r in c.execute("SELECT source,COUNT(*) FROM products GROUP BY source")}
        cat = {r[0]:r[1] for r in c.execute("SELECT category,COUNT(*) FROM products GROUP BY category")}
        recent = c.execute("SELECT COUNT(*) FROM products WHERE created_at>datetime('now','-7 days')").fetchone()[0]
        return {"total_products":total,"avg_price_usd":round(avg,2),"by_source":src,"by_category":cat,"recent_7d":recent}

@app.get("/api/hunter/niches")
def niches(): return {"niches":NICHES, "total":len(NICHES)}

@app.get("/api/hunter/trending")
def trending(limit:int=10):
    return {"products":[],"count":0,"message":"Usá POST /api/hunter/search para buscar"}

@app.post("/api/calculate")
async def calculate(request: Request):
    try: body = await request.json()
    except: body = {}
    r = calc_import(
        float(body.get("product_cost",0)),
        float(body.get("shipping",3)),
        body.get("category","default"),
        int(body.get("quantity",1)),
        float(body.get("shipping_total",0))
    )
    return {"success":True, **r}

@app.get("/api/categories")
def cats():
    return [{"id":k,"name":v["name"] if "name" in v else k,"tariff":f"{RATES.get(k,RATES['default'])['tariff']*100:.0f}%"} 
            for k,v in {"tecnologia":{"name":"Tecnología"},"hogar":{"name":"Hogar"},"belleza":{"name":"Belleza"},"fitness":{"name":"Fitness"},"mascotas":{"name":"Mascotas"},"auto":{"name":"Auto"},"accesorios":{"name":"Accesorios"},"default":{"name":"General"}}.items()]

@app.post("/api/ml-search")
async def ml_search(request: Request):
    try: body = await request.json()
    except: body = {}
    kw = body.get("keywords","")
    if not kw: return JSONResponse({"error":"keywords required","success":False}, 400)
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15.0) as c:
            r = await c.get(f"https://listado.mercadolibre.com.uy/{quote_plus(kw)}")
            titles = re.findall(r'<h2[^>]*>(.*?)</h2>', r.text, re.DOTALL)
            prices = re.findall(r'(\d[\d.,]*)\s*(?:pesos|USD|US\$|\$)', r.text)
            prods = []
            for i,t in enumerate(titles[:10]):
                tc = re.sub(r'<[^>]+>','',t).strip()
                p = prices[i] if i<len(prices) else "?"
                prods.append({"title":tc[:100],"price_uyu":p,"url":f"https://listado.mercadolibre.com.uy/{quote_plus(kw)}"})
            return {"success":True,"source":"ml-uy","products":prods,"note":"Resultados aproximados. Para precisión total, buscá en ML directamente."}
    except Exception as e:
        return {"success":False,"error":str(e),"ml_url":f"https://listado.mercadolibre.com.uy/{quote_plus(kw)}"}

# ═══════════════ STATIC ═══════════════
STATIC_DIR = os.path.join(BASE, "static")
if os.path.exists(os.path.join(STATIC_DIR, "index.html")):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
