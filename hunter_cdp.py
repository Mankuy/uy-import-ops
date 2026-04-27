import asyncio, subprocess, re, json, os, sqlite3
from datetime import datetime
from urllib.parse import quote_plus

# --- Config ---
r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
m = re.search(r"via\s+([\d.]+)", r.stdout)
GW = m.group(1) if m else "172.23.32.1"
CDP_PORT = 9223
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "backend", "research.db")
JSON_OUT = os.path.join(BASE, "hunter_products.json")
UYU_TO_USD = 40
PLATFORMS = ["aliexpress", "banggood"]

def insert_db(product):
    """Inserta o actualiza producto en research.db."""
    try:
        conn = sqlite3.connect(DB)
        now = datetime.utcnow().isoformat()
        title = product["title"][:150]
        url = product["url"]
        img = product.get("image_url", "")
        price = product["price_usd"]
        platform = product.get("platform", "unknown")
        existing = conn.execute("SELECT id FROM products WHERE source_url=?", (url,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE products SET name=?, image_url=?, product_cost_usd=?, updated_at=? WHERE id=?",
                (title, img, price, now, existing[0])
            )
        else:
            conn.execute(
                "INSERT INTO products (name,source_url,image_url,product_cost_usd,status,demand_score,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (title, url, img, price, f"hunter_{platform}", 50, now, now)
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  DB ERROR: {e}")
        return False

# ===================================================================
# ALIEXPRESS - CDP semi-automatico (usa Chrome real de Facu)
# ===================================================================
async def hunt_aliexpress(keywords, min_price=None, max_price=None):
    """Extrae productos de pestanas abiertas en Chrome real."""
    from playwright.async_api import async_playwright
    
    results = []
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://{GW}:{CDP_PORT}")
        except Exception as e:
            print(f"  [AE] No se pudo conectar a Chrome CDP: {e}")
            return results
        
        for ctx in browser.contexts:
            for pg in ctx.pages:
                url = pg.url
                # Solo paginas de producto
                if "/item/" not in url:
                    # Si es una pestana de search, abrir los primeros productos
                    if "aliexpress.com/w/" in url or "aliexpress.com/wholesale" in url:
                        print(f"  [AE] Busqueda detectada, abriendo productos...")
                        links = await pg.evaluate("""() => {
                            return Array.from(document.querySelectorAll('a[href*="/item/"]'))
                                .slice(0, 10)
                                .map(a => a.href);
                        }""")
                        for link in links:
                            try:
                                new_pg = await ctx.new_page()
                                await new_pg.goto(link, timeout=15000, wait_until="domcontentloaded")
                                await new_pg.wait_for_timeout(2000)
                                data = await _extract_ae_product(new_pg)
                                if data:
                                    data["platform"] = "aliexpress"
                                    results.append(data)
                                    ok = insert_db(data)
                                    print(f"  [AE] ${data['price_usd']:<8.2f} {'DB' if ok else '!!'} | {data['title'][:55]}")
                                await new_pg.close()
                            except:
                                continue
                    continue
                
                data = await _extract_ae_product(pg)
                if data:
                    data["platform"] = "aliexpress"
                    results.append(data)
                    ok = insert_db(data)
                    print(f"  [AE] ${data['price_usd']:<8.2f} {'DB' if ok else '!!'} | {data['title'][:55]}")
    
    return results

async def _extract_ae_product(pg):
    """Extrae datos de una pagina de producto AliExpress."""
    data = await pg.evaluate("""() => {
        const ld = document.querySelector('script[type="application/ld+json"]');
        if (ld) {
            try {
                const obj = JSON.parse(ld.textContent);
                if (obj && obj["@type"] === "Product") {
                    const offers = obj.offers;
                    let price = 0;
                    if (offers) {
                        const o = Array.isArray(offers) ? offers[0] : offers;
                        price = parseFloat(o.price) || 0;
                    }
                    let img = "";
                    if (Array.isArray(obj.image)) img = obj.image[0];
                    else if (typeof obj.image === "string") img = obj.image;
                    return {title: obj.name||"", price: price, image: img, source: "json-ld"};
                }
            } catch(e) {}
        }
        const ogT = document.querySelector('meta[property="og:title"]')?.content;
        const ogP = document.querySelector('meta[property="og:price:amount"], meta[property="product:price:amount"]')?.content;
        const ogI = document.querySelector('meta[property="og:image"]')?.content;
        if (ogT && ogP) {
            return {title: ogT, price: parseFloat(ogP.replace(/,/g,"")), image: ogI||"", source: "meta"};
        }
        const all = document.querySelectorAll("*");
        let best = ""; let bestY = 9999;
        for (const el of all) {
            if (el.childNodes.length !== 1 || el.childNodes[0].nodeType !== 3) continue;
            const txt = el.textContent.trim();
            const m = txt.match(/^UYU\s*([\d,.]+)/);
            if (m) {
                const rect = el.getBoundingClientRect();
                if (rect.top > 100 && rect.top < 400 && rect.top < bestY) {
                    best = m[1]; bestY = rect.top;
                }
            }
        }
        const h1 = document.querySelector("h1");
        const img = document.querySelector('meta[property="og:image"]')?.content || "";
        if (h1 && best) {
            return {title: h1.textContent.trim().substring(0,200), price: parseFloat(best.replace(/,/g,"")), image: img, source: "dom-uyu"};
        }
        if (h1) {
            return {title: h1.textContent.trim().substring(0,200), price: 0, image: img, source: "dom-title"};
        }
        return null;
    }""")
    if not data or not data.get("title"):
        return None
    pid = re.search(r"/item/(\d+)", pg.url)
    price = data["price"]
    src = data.get("source", "")
    if src == "dom-uyu" or price > 100:
        price = round(price / UYU_TO_USD, 2)
    return {
        "product_id": pid.group(1) if pid else "?",
        "url": pg.url.split("?")[0],
        "title": data["title"][:150],
        "price_usd": price,
        "image_url": data.get("image", ""),
        "source": src,
    }

# ===================================================================
# BANGGOOD - Automatico (sin CDP, headless)
# ===================================================================
async def hunt_banggood(keywords, min_price=None, max_price=None, max_products=20):
    """Scrapea Banggood automaticamente con Playwright headless."""
    from playwright.async_api import async_playwright
    
    results = []
    query = quote_plus(keywords)
    url = f"https://www.banggood.com/search/{query}.html"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )
        page = await ctx.new_page()
        
        print(f"  [BG] Buscando: {url}")
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        
        # Extraer productos de la pagina de busqueda
        products = await page.evaluate("""() => {
            const prices = document.querySelectorAll('span.price');
            const results = [];
            for (const priceEl of prices) {
                const priceText = priceEl.textContent.trim();
                const priceMatch = priceText.match(/[\d,.]+/);
                if (!priceMatch) continue;
                
                // Subir para encontrar link y titulo
                let container = priceEl;
                let link = null;
                let titleEl = null;
                let imgEl = null;
                for (let i = 0; i < 15; i++) {
                    container = container.parentElement;
                    if (!container) break;
                    if (!link) {
                        const a = container.querySelector('a[href]');
                        if (a && a.href.includes('banggood.com') && !a.href.includes('/search')) link = a;
                    }
                    if (!titleEl) {
                        const t = container.querySelector('a[title]');
                        if (t) titleEl = t;
                    }
                    if (!imgEl) {
                        const img = container.querySelector('img[src*="imgaz"]');
                        if (img) imgEl = img;
                    }
                }
                
                if (link) {
                    results.push({
                        url: link.href.split('?')[0],
                        title: titleEl ? titleEl.getAttribute('title') : (link.textContent.trim().substring(0, 150) || link.href),
                        price: parseFloat(priceMatch[0].replace(/,/g, '')),
                        image: imgEl ? imgEl.src : ''
                    });
                }
            }
            return results;
        }""")
        
        print(f"  [BG] Encontrados {len(products)} productos en busqueda")
        
        # Filtrar por precio si se especifica
        if min_price is not None:
            products = [p for p in products if p["price"] >= min_price]
        if max_price is not None:
            products = [p for p in products if p["price"] <= max_price]
        
        # Limitar
        products = products[:max_products]
        
        for prod in products:
            result = {
                "product_id": re.search(r"/p-([\d]+)", prod["url"]).group(1) if re.search(r"/p-([\d]+)", prod["url"]) else "?",
                "url": prod["url"],
                "title": prod["title"][:150],
                "price_usd": prod["price"],
                "image_url": prod.get("image", ""),
                "source": "banggood-search",
                "platform": "banggood",
            }
            results.append(result)
            ok = insert_db(result)
            print(f"  [BG] ${result['price_usd']:<8.2f} {'DB' if ok else '!!'} | {result['title'][:55]}")
        
        await ctx.close()
        await browser.close()
    
    return results

# ===================================================================
# MAIN
# ===================================================================
async def main():
    import sys
    platform = sys.argv[1] if len(sys.argv) > 1 else "all"
    keywords = sys.argv[2] if len(sys.argv) > 2 else ""
    min_p = float(sys.argv[3]) if len(sys.argv) > 3 else None
    max_p = float(sys.argv[4]) if len(sys.argv) > 4 else None
    
    all_results = []
    
    if platform in ("aliexpress", "ae", "all"):
        print("=== AliExpress (CDP) ===")
        r = await hunt_aliexpress(keywords, min_p, max_p)
        all_results.extend(r)
    
    if platform in ("banggood", "bg", "all"):
        print("=== Banggood (Headless) ===")
        r = await hunt_banggood(keywords, min_p, max_p)
        all_results.extend(r)
    
    if all_results:
        with open(JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\n=== {len(all_results)} productos guardados en {JSON_OUT} ===")
    else:
        print("\n=== 0 productos encontrados ===")
    
    return len(all_results) > 0

if __name__ == "__main__":
    import sys
    print("Uso: python hunter_cdp.py [aliexpress|banggood|all] [keywords] [min_price] [max_price]")
    print("Ejemplo: python hunter_cdp.py banggood 'phone case' 1 10")
    print("         python hunter_cdp.py aliexpress  # extrae de pestanas abiertas")
    sys.exit(0 if asyncio.run(main()) else 1)
