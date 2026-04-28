import json, re, asyncio, random, time, logging, yaml, hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
from sqlalchemy import create_engine, text
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

print(f"\n{'='*60}")
print(f"[INIT] scrapers.py cargado desde: {__file__}")
print(f"{'='*60}\n")

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "scraper_config.yaml"
STATIC_DIR = BASE_DIR / "static" / "products"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    CFG = yaml.safe_load(f)

MIN_PRICE = float(CFG.get("min_price", 1.0))
MAX_PRICE = float(CFG.get("max_price", 100.0))
DELAY_MIN = float(CFG.get("delay_min", 2))
DELAY_MAX = float(CFG.get("delay_max", 3))
RETRY_ATTEMPTS = int(CFG.get("retry_attempts", 2))
CONCURRENCY = int(CFG.get("concurrency", 1))
COOKIES = CFG.get("cookies", [])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(BASE_DIR / "hunter.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("hunter")

DB_PATH = BASE_DIR / "research.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
INSERT_SQL = text("""INSERT OR IGNORE INTO products (source_url, image_url, product_cost_usd, status, created_at, updated_at)
                     VALUES (:source_url, :image_url, :product_cost_usd, 'hunter_new', datetime('now'), datetime('now'))""")
ITEM_URL_RE = re.compile(r"https?://(?:www\.)?aliexpress\.com/item/(\d+)\.html")

def _validate_product_url(url: str) -> bool:
    return bool(ITEM_URL_RE.search(url))

def _clean_price(val) -> float:
    if val is None: return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).replace(",", "").replace("$", "").strip()
    try: return float(s)
    except: return 0.0

async def _download_image(session: aiohttp.ClientSession, url: str, product_id: str) -> Tuple[bool, str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200: return False, f"HTTP {resp.status}"
            ct = resp.headers.get("Content-Type", "")
            if not ct.startswith("image/"): return False, f"CT {ct}"
            content = await resp.read()
            img_hash = hashlib.md5(content).hexdigest()[:8]
            ext = ct.split("/")[-1].lower()
            if ext not in ("jpg", "jpeg", "png", "webp"): ext = "jpg"
            filename = f"{product_id}_{img_hash}.{ext}"
            rel_path = f"products/{filename}"
            abs_path = STATIC_DIR / filename
            with open(abs_path, "wb") as f: f.write(content)
            log.info(f"[IMAGE] Descargada: {rel_path}")
            return True, rel_path
    except Exception as e:
        log.warning(f"[IMAGE] Error: {e}")
        return False, str(e)

def _parse_api_json(data: dict, product_id: str) -> Optional[Dict]:
    try:
        def find(keys, obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.lower() in keys: return v
                    deeper = find(keys, v)
                    if deeper is not None: return deeper
            elif isinstance(obj, list):
                for item in obj:
                    found = find(keys, item)
                    if found is not None: return found
            return None
        result = data.get("result") or data.get("data") or data
        title = find(["title","productname","name","subject"], result)
        price = find(["price","salePrice","currentPrice","amount","minPrice"], result)
        image = find(["image","mainimage","imageUrl","pic","imagePath"], result)
        if not title or not price: return None
        p_val = _clean_price(price)
        if p_val <= 0: return None
        return {"title": str(title).strip()[:300], "price_usd": p_val, "image_url": str(image or "").strip()}
    except Exception as e:
        log.debug(f"[API PARSE] {product_id}: {e}")
        return None

async def _capture_debug(page, product_id: str):
    try:
        screenshot_path = BASE_DIR / f"fail_{product_id}.jpg"
        html_path = BASE_DIR / f"fail_{product_id}.html"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(await page.content())
        log.warning(f"[DEBUG] fail_{product_id}.jpg + .html guardados")
    except Exception as e:
        log.debug(f"[DEBUG] error: {e}")

async def _extract_from_html(page) -> Optional[Dict]:
    try:
        data = await page.evaluate("""() => {
            const ld = document.querySelector('script[type="application/ld+json"]');
            if (ld) {
                try {
                    const d = JSON.parse(ld.textContent);
                    if (d && d.offers && d.offers.price) {
                        return { t: d.name || "", p: d.offers.price, i: d.image || "", ok: 1 };
                    }
                } catch(e) {}
            }
            const ogT = document.querySelector('meta[property="og:title"]');
            const ogP = document.querySelector('meta[property="og:price:amount"], meta[property="product:price:amount"]');
            const ogI = document.querySelector('meta[property="og:image"]');
            if (ogT && ogP) {
                return { t: (ogT.content||"").trim(), p: parseFloat((ogP.content||"0").replace(/,/g,"")), i: (ogI?ogI.content:""), ok: 1 };
            }
            const h1 = document.querySelector('h1, .product-title, [data-auto-id="product-title"]');
            const pe = document.querySelector('.price-current, .current-price, [data-price], [data-current-price]');
            const img = document.querySelector('img[src*="_250x250"], img[src*="_640x640"], .product-img img, .image-view-magnifier-wrap img');
            let pr = 0;
            if (pe) { const m = pe.textContent.match(/[\d,.]+/); if (m) pr = parseFloat(m[0].replace(/,/g,"")); }
            return { t: (h1 ? h1.textContent.trim() : document.title.split('|')[0].trim()), p: pr, i: (img?img.src:""), ok: h1 && pr>0 ? 1 : 0 };
        }""")
        if data.get("ok"):
            return {"title": (data.get("t") or "").strip()[:300], "price_usd": float(data.get("p",0)), "image_url": (data.get("i") or "").strip()}
        return None
    except Exception as e:
        log.debug(f"[HTML PARSE] error: {e}")
        return None

async def scrape_product_url(
    url: str,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    between_delay: float = 0,
    headed: bool = False,
) -> Optional[Dict]:
    """Visita URL, intercepta API JSON, extrae datos, descarga imagen, inserta DB."""
    async with semaphore:
        if not _validate_product_url(url):
            log.warning(f"[SKIP] URL inválida: {url}")
            return None

        product_id = ITEM_URL_RE.search(url).group(1)
        log.info(f"[SCRAPE] Iniciando: product_id={product_id}")
        log.debug(f"[CONFIG] cookies_config_present={bool(COOKIES)} count={len(COOKIES) if COOKIES else 0}")

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            browser = None
            try:
                async with async_playwright() as p:
                    # === PERFIL PERSISTENTE: browser indistinguible de Chrome real ===
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir="/home/facajgs/uy-import-ops/research-dashboard/chrome_profile",
                        headless=not headed,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-features=IsolateOrigins,site-per-process",
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-infobars",
                            "--disable-dev-shm-usage",
                            "--window-size=1920,1080",
                            "--disable-gpu",
                        ],
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080},
                        locale="en-US",
                        timezone_id="America/New_York",
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                            "sec-ch-ua-mobile": "?0",
                            "sec-ch-ua-platform": '"Windows"',
                        },
                    )
                    # Inject cookies en el contexto persistente
                    if COOKIES:
                        await context.add_cookies(COOKIES)
                        log.debug(f"[COOKIES] {len(COOKIES)} cookies inyectadas en perfil persistente")
                    
                    page = await context.new_page()
                    page.set_default_timeout(30000)
                    
                    # === STEALTH: ocultar fingerprints de automatizacion ===
                    await page.add_init_script("""
                        // 1. Ocultar navigator.webdriver
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                        // 2. Simular chrome.runtime
                        window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};
                        // 3. Plugins falsos (los browsers reales tienen varios)
                        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                        // 4. Lenguajes
                        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'es']});
                        // 5. Permisos
                        const originalQuery = window.navigator.permissions.query;
                        window.navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' ?
                            Promise.resolve({state: Notification.permission}) :
                            originalQuery(parameters)
                        );
                        // 6. Headless detection evasion
                        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                    """)
                    # === END STEALTH ===
                    api_responses = []
                    def on_response(response):
                        try:
                            if (product_id in response.url and 
                                response.headers.get('content-type','').startswith('application/json')):
                                api_responses.append(response)
                        except: pass
                    page.on("response", on_response)
                    
                    await page.route("**/*", lambda route, req: route.abort()
                        if req.resource_type in ["image","media","font"]
                        else route.continue_()
                    )
                    
                    log.info(f"[NAV] {product_id}: goto {url}")
                    await page.goto(url, timeout=30000, wait_until="load")
                    
                    # Anti-bot detection — estrategia mejorada
                    html_check = await page.content()
                    blocked_markers = ["aplus-waiting", "Please verify", "Checking your browser"]
                    if any(x in html_check for x in blocked_markers):
                        log.warning(f"[ANTIBOT] {product_id}: challenge detectado — pausa y recarga...")
                        
                        # Estrategia en 3 fases:
                        for phase in range(1, 4):
                            wait = 5 * phase  # 5s, 10s, 15s
                            log.info(f"[ANTIBOT] {product_id}: fase {phase} — esperando {wait}s...")
                            await asyncio.sleep(wait)
                            
                            # Recargar con clean state
                            await page.reload(timeout=30000, wait_until="load")
                            html_after = await page.content()
                            
                            if not any(x in html_after for x in blocked_markers):
                                log.info(f"[ANTIBOT] {product_id}: challenge SUPERADO en fase {phase}")
                                # Reiniciar listeners para la nueva carga
                                api_responses = []
                                page.remove_listener("response", on_response)
                                def on_response_reloaded(response):
                                    if (product_id in response.url and 
                                        response.headers.get('content-type','').startswith('application/json')):
                                        api_responses.append(response)
                                page.on("response", on_response_reloaded)
                                break
                        else:
                            # Las 3 fases fallaron
                            log.error(f"[ANTIBOT] {product_id}: bloqueo PERSISTENTE tras 3 fases")
                            await _capture_debug(page, product_id)
                            # browser.close() not needed with persistent_context
                            return None
                    
                    # Esperar selector de precio
                    try:
                        await page.wait_for_selector('.price-current, .current-price, [data-price], [data-current-price], meta[property="og:price:amount"]', timeout=15000)
                        log.info(f"[DATA] {product_id}: selector precio encontrado")
                    except: pass
                    
                    # Intentar extraer desde API interceptada
                    product_data = None
                    for resp in api_responses:
                        try:
                            json_data = await resp.json()
                            parsed = _parse_api_json(json_data, product_id)
                            if parsed:
                                product_data = parsed
                                log.info(f"[API] {product_id}: datos extraídos de API")
                                break
                        except: continue
                    
                    # Fallback a HTML parsing
                    if not product_data:
                        log.info(f"[FALLBACK] {product_id}: intentando HTML parsing...")
                        product_data = await _extract_from_html(page)
                    
                    # browser.close() not needed with persistent_context
                    
                    if not product_data:
                        await _capture_debug(page, product_id)
                        log.warning(f"[EXTRACT] No se pudo extraer datos de {product_id}")
                        return None
                    
                    # Filtro precio
                    price = product_data["price_usd"]
                    if not (MIN_PRICE <= price <= MAX_PRICE):
                        log.info(f"[FILTER] Precio ${price:.2f} fuera de rango — {product_id}")
                        return None
                    
                    # Descarga imagen
                    img_url = product_data.get("image_url", "")
                    img_ok, img_result = await _download_image(session, img_url, product_id)
                    image_path = img_result if img_ok else ""
                    
                    # DB insert
                    insert_ok = False
                    try:
                        with engine.begin() as conn:
                            conn.execute(INSERT_SQL, {
                                "source_url": url,
                                "image_url": image_path,
                                "product_cost_usd": price,
                            })
                        insert_ok = True
                    except Exception as e:
                        log.error(f"[DB] Error insertando {product_id}: {e}")
                    
                    log.info(f"[OK] ✓ {product_id} — ${price:.2f} — img={'OK' if img_ok else 'FAIL'} — db={'OK' if insert_ok else 'FAIL'}")
                    return {
                        "product_url": url,
                        "product_id": product_id,
                        "title": product_data["title"],
                        "price_usd": price,
                        "image_url": img_url,
                        "image_downloaded": img_ok,
                        "image_local_path": image_path,
                        "inserted": insert_ok,
                        "attempts": attempt,
                    }

            except asyncio.TimeoutError:
                log.warning(f"[TIMEOUT] {product_id} — intento {attempt}")
                # browser.close() not needed with persistent_context
                if attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(2**attempt + random.uniform(0,2))
                    continue
                return None
            except Exception as e:
                log.error(f"[ERROR] {product_id} attempt {attempt}: {type(e).__name__}: {e}")
                # browser.close() not needed with persistent_context
                if attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(2**attempt + random.uniform(0,2))
                else: return None

        return None

async def scrape_multiple_urls(
    urls: List[str],
    concurrency: int = CONCURRENCY,
    between_delay: float = 0,
    headed: bool = False,
) -> Dict:
    semaphore = asyncio.Semaphore(concurrency)
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = []
        for url in urls:
            result = await scrape_product_url(url, session, semaphore, between_delay=between_delay, headed=headed)
            results.append(result)
            if between_delay > 0:
                await asyncio.sleep(between_delay)
    valid = [r for r in results if r is not None]
    inserted = sum(1 for r in valid if r.get("inserted"))
    return {"total_raw": len(urls), "products_found": len(valid), "products_inserted": inserted, "products": valid}

class AliExpressExtractor:
    BASE_URL = "https://www.aliexpress.com"
    async def search_products(self, query: str, limit: int = 10, **kwargs) -> List[str]:
        search_url = f"{self.BASE_URL}/wholesale?SearchText={query.replace(' ', '+')}&g=y"
        log.info(f"[SEARCH] Query='{query}' → {search_url}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}, locale="en-US",
            )
            page = await context.new_page()
            await page.route("**/*", lambda route, req: route.abort() if req.resource_type in ["image","media","font"] else route.continue_())
            try:
                await page.goto(search_url, timeout=30000, wait_until="load")
            except PlaywrightTimeout:
                log.error(f"[SEARCH] Timeout en búsqueda '{query}'")
                await browser.close()
                return []
            try:
                await page.wait_for_selector('[data-offer-id], .offer-item, .common-offer-card, .product-card', timeout=8000)
            except PlaywrightTimeout:
                html = await page.content()
                await browser.close()
                if "captcha" in html.lower():
                    log.warning("[SEARCH] CAPTCHA")
                else:
                    log.warning("[SEARCH] No se encontraron tarjetas")
                return []
            items = await page.query_selector_all('a[href*="/item/"]')
            urls = []
            for a in items:
                href = await a.get_attribute("href")
                if href and "/item/" in href and _validate_product_url(href):
                    if href.startswith("//"): href = "https:" + href
                    elif href.startswith("/"): href = self.BASE_URL + href
                    urls.append(href)
                if len(urls) >= limit: break
            await browser.close()
            log.info(f"[SEARCH] {len(urls)} URLs extraídas")
            return urls

async def hunt_products(
    query: str,
    limit: int = 10,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    headed: bool = False,
) -> Dict:
    min_price = min_price if min_price is not None else MIN_PRICE
    max_price = max_price if max_price is not None else MAX_PRICE
    log.info(f"[HUNT] Iniciando: query='{query}', limit={limit}")
    extractor = AliExpressExtractor()
    item_urls = await extractor.search_products(query=query, limit=limit)
    if not item_urls:
        return {"query": query, "total_raw": 0, "products_found": 0, "products_inserted": 0, "products": [], "duration_seconds": 0}
    start = time.time()
    result = await scrape_multiple_urls(item_urls, concurrency=1, between_delay=DELAY_MIN, headed=headed)
    result["query"] = query
    result["duration_seconds"] = time.time() - start
    return result

async def run_test_mode(headed: bool = False) -> Dict:
    test_path = BASE_DIR / "test_products.json"
    if not test_path.exists():
        log.error("[TEST] test_products.json no encontrado")
        return {}
    with open(test_path) as f:
        test_data = json.load(f)
        test_urls = test_data.get("products", [])
    log.info(f"[TEST] Probando {len(test_urls)} URLs (headed={headed})")
    start = time.time()
    result = await scrape_multiple_urls(test_urls, concurrency=1, between_delay=0.5, headed=headed)
    result["query"] = "TEST"
    result["duration_seconds"] = time.time() - start
    result["test_urls"] = test_urls
    total_inserted = result["products_inserted"]
    log.info(f"[TEST SUMMARY] inserted={total_inserted}/{len(test_urls)} expected={test_data.get('expected_valid','N/A')}")
    return result

if __name__ == "__main__":
    import sys
    async def main():
        headed = "--headed" in sys.argv
        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        if len(args) > 0 and args[0] != '--test':
            query = args[0]
            limit = int(args[1]) if len(args) > 1 else 10
            print(f"[RUNNER] Ejecutando hunter: query='{query}', limit={limit} (headed={headed})\n")
            result = await hunt_products(query=query, limit=limit, headed=headed)
        else:
            print(f"[RUNNER] Modo TEST con test_products.json (headed={headed})\n")
            result = await run_test_mode(headed=headed)
        print("\n" + "="*60)
        print(f"QUERY:       {result.get('query', 'TEST')}")
        print(f"RAW encontrados: {result['total_raw']}")
        print(f"Válidos:        {result['products_found']}")
        print(f"Insertados DB:  {result['products_inserted']}")
        print(f"Duración:       {result.get('duration_seconds', 0):.1f}s")
        print("="*60)
        errors = []; warnings = []
        for idx, p in enumerate(result.get('products', []), 1):
            if not _validate_product_url(p.get('product_url','')): errors.append(f"Prod {idx}: URL inválida")
            if not p.get('image_downloaded'): warnings.append(f"Prod {idx}: imagen NO descargada")
            if p.get('price_usd',0) <= 0: errors.append(f"Prod {idx}: precio inválido")
        print(f"\n[VALIDATION] Errores: {len(errors)} | Warnings: {len(warnings)}")
        if errors:
            print("ERRORES:");
            for e in errors: print(f"  ✗ {e}")
        if warnings:
            print("WARNINGS:");
            for w in warnings: print(f"  ⚠ {w}")
        if not errors and not warnings:
            print("✓ TODOS los productos cumplen requisitos")
        report_path = BASE_DIR / "hunter_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": {
                    "query": result.get('query'),
                    "total_raw": result['total_raw'],
                    "products_found": result['products_found'],
                    "products_inserted": result['products_inserted'],
                    "duration_seconds": result.get('duration_seconds'),
                    "errors": errors, "warnings": warnings,
                },
                "products": [
                    {
                        "url": p.get('product_url'),
                        "price": p.get('price_usd'),
                        "image_downloaded": p.get('image_downloaded'),
                        "image_local": p.get('image_local_path'),
                        "title": p.get('title', '')[:80],
                    }
                    for p in result.get('products', [])
                ],
            }, f, indent=2, ensure_ascii=False)
        print(f"\n[REPORT] hunter_report.json generado")
    asyncio.run(main())


# --- Stubs for dashboard compatibility ---
class ProductHunter:
    def __init__(self, *args, **kwargs): pass
    def hunt(self, *args, **kwargs): return []

TRENDING_NICHES_DATA = []

async def search_bing_shopping(*args, **kwargs):
    return []

async def search_bing_web_products(*args, **kwargs):
    return []

async def generate_mock_sourcing_data(*args, **kwargs):
    return []
