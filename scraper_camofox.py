"""
scraper_camofox.py — AliExpress scraping via Camofox Browser REST API.

Camofox runs as a local sidecar (http://localhost:9377) and handles all
anti-bot evasion at the C++ level. This module talks to it via REST.

Usage:
    from scraper_camofox import scrape_aliexpress
    result = await scrape_aliexpress("bluetooth earphone", max_products=20)
"""
import os, re, logging, asyncio, sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from urllib.parse import quote_plus

import httpx

log = logging.getLogger("hunter.camofox")

CAMOFOX_URL = os.environ.get("CAMOFOX_URL", "http://localhost:9377")
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "hunter.db")

# Category detection (shared with hunter_svc)
CAT_KW = {
    "tecnologia": ["auricular", "bluetooth", "smartwatch", "parlante", "cargador",
                    "power bank", "lampara", "proyector", "camara", "teclado", "mouse", "gamer",
                    "earphone", "speaker", "charger", "projector", "camera", "keyboard"],
    "hogar": ["lampara", "difusor", "aspiradora", "organizador", "balanza", "termo",
              "ventilador", "humidificador", "enchufe", "tira led",
              "lamp", "diffuser", "vacuum", "organizer", "scale", "fan", "humidifier", "led strip"],
    "fitness": ["ejercicio", "yoga", "botella", "masajeador", "cuerda", "reloj", "pesas", "rodillo",
                "exercise", "bottle", "massager", "rope", "watch", "dumbbell", "roller"],
    "belleza": ["cepillo", "alisador", "secador", "depiladora", "lampara uv", "espejo", "facial", "rizador",
                "brush", "straightener", "dryer", "removal", "mirror", "curler"],
    "mascotas": ["perro", "gato", "mascota", "bebedero", "comedero", "collar", "juguete", "arnes",
                 "dog", "cat", "pet", "feeder", "collar", "toy", "harness"],
    "auto": ["dash cam", "soporte", "inflador", "retrovisor", "auto",
             "car", "mount", "inflator", "mirror"],
    "accesorios": ["funda", "cable", "protector", "popsocket", "ring holder", "adaptador", "hub",
                   "case", "cable", "protector", "adapter", "hub"],
}


def _detect_cat(title: str) -> str:
    t = title.lower()
    for cat, kws in CAT_KW.items():
        if any(kw in t for kw in kws):
            return cat
    return "default"


def _save_to_db(products: List[Dict]):
    """Save products to hunter.db."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            for p in products:
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO products "
                        "(name, source_url, image_url, product_cost_usd, source, category, status, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (
                            p["title"][:150],
                            p["url"],
                            p.get("image_url", ""),
                            p["price_usd"],
                            p["source"],
                            p["category"],
                            "hunter_new",
                            datetime.utcnow().isoformat(),
                        ),
                    )
                except Exception as e:
                    log.warning(f"[DB] Skip: {e}")
            conn.commit()
    except Exception as e:
        log.error(f"[DB] Error: {e}")


async def _camofox_health() -> bool:
    """Check if Camofox is running."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{CAMOFOX_URL}/health")
            return r.status_code == 200
    except Exception:
        return False


async def _create_tab(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Create a new Camofox tab and navigate to url. Returns tabId."""
    try:
        r = await client.post(f"{CAMOFOX_URL}/tabs", json={"url": url}, timeout=30.0)
        if r.status_code in (200, 201):
            data = r.json()
            return data.get("tabId") or data.get("tab_id") or data.get("id")
    except Exception as e:
        log.warning(f"[TAB] Create error: {e}")
    return None


async def _snapshot(client: httpx.AsyncClient, tab_id: str) -> Optional[str]:
    """Get accessibility snapshot of tab (much smaller than HTML)."""
    try:
        r = await client.get(f"{CAMOFOX_URL}/tabs/{tab_id}/snapshot", timeout=15.0)
        if r.status_code == 200:
            data = r.json()
            return data.get("snapshot") or data.get("content") or str(data)
    except Exception as e:
        log.warning(f"[SNAP] Error: {e}")
    return None


async def _close_tab(client: httpx.AsyncClient, tab_id: str):
    """Close a Camofox tab."""
    try:
        await client.delete(f"{CAMOFOX_URL}/tabs/{tab_id}", timeout=5.0)
    except Exception:
        pass


async def _extract_product_from_snapshot(snapshot: str, url: str) -> Optional[Dict]:
    """Parse product data from accessibility snapshot text."""
    if not snapshot:
        return None

    title = ""
    price = 0.0
    image_url = ""

    # Try to find title — usually the first prominent heading
    # Snapshots use indented text with role annotations
    lines = snapshot.split("\n")

    for line in lines:
        stripped = line.strip()
        # Title: look for heading or main product name
        if not title and ("heading" in stripped.lower() or len(stripped) > 20):
            # Clean role annotations
            clean = re.sub(r'\[.*?\]', '', stripped).strip()
            clean = re.sub(r'^[-·•]\s*', '', clean).strip()
            if len(clean) > 10 and not any(x in clean.lower() for x in ["aliexpress", "sign in", "shipping", "return"]):
                title = clean[:200]

        # Price: look for USD amounts
        price_match = re.search(r'(?:US\s*\$|USD\s*)\s*([\d,.]+)', stripped)
        if not price_match:
            price_match = re.search(r'\$\s*([\d,.]+)', stripped)
        if price_match and price == 0.0:
            try:
                pv = float(price_match.group(1).replace(",", ""))
                if 0.01 < pv < 10000:
                    price = pv
            except ValueError:
                pass

        # Image URLs
        img_match = re.search(r'(https?://[^\s"\']+\.(?:jpg|jpeg|png|webp))', stripped, re.IGNORECASE)
        if img_match and not image_url:
            candidate = img_match.group(1)
            if "aliexpress" in candidate or "alicdn" in candidate:
                image_url = candidate

    if not title or price <= 0:
        return None

    pid = re.search(r'/item/(\d+)', url)
    return {
        "product_id": pid.group(1) if pid else "?",
        "url": url.split("?")[0],
        "title": title,
        "price_usd": round(price, 2),
        "image_url": image_url,
        "source": "aliexpress",
        "category": _detect_cat(title),
    }


async def _search_aliexpress_urls(client: httpx.AsyncClient, keywords: str, limit: int = 20) -> List[str]:
    """Use Camofox to search AliExpress and extract product URLs."""
    search_url = f"https://www.aliexpress.com/wholesale?SearchText={quote_plus(keywords)}&g=y"
    log.info(f"[AE SEARCH] {search_url}")

    tab_id = await _create_tab(client, search_url)
    if not tab_id:
        log.warning("[AE SEARCH] Could not create tab")
        return []

    # Wait for page to load
    await asyncio.sleep(5)

    snap = await _snapshot(client, tab_id)
    await _close_tab(client, tab_id)

    if not snap:
        return []

    # Extract product URLs from snapshot
    urls = re.findall(r'https?://(?:www\.)?aliexpress\.com/item/(\d+)\.html', snap)
    unique = list(dict.fromkeys(urls))  # dedupe preserving order
    result = [f"https://www.aliexpress.com/item/{pid}.html" for pid in unique[:limit]]
    log.info(f"[AE SEARCH] Found {len(result)} product URLs")
    return result


async def scrape_aliexpress(
    keywords: str,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    max_products: int = 20,
) -> Dict:
    """
    Scrape AliExpress products using Camofox browser.
    Returns dict compatible with hunter_svc response format.
    """
    # Check camofox is alive
    alive = await _camofox_health()
    if not alive:
        log.warning("[CAMOFOX] Not running — skipping AliExpress")
        return {
            "added": 0,
            "keywords": keywords,
            "source": "aliexpress",
            "products": [],
            "success": False,
            "error": "Camofox no está corriendo. Inicialo con: cd camofox-browser && npm start",
            "camofox_status": "offline",
        }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Search for product URLs
        product_urls = await _search_aliexpress_urls(client, keywords, limit=max_products * 2)

        if not product_urls:
            return {
                "added": 0,
                "keywords": keywords,
                "source": "aliexpress",
                "products": [],
                "success": True,
                "message": "No se encontraron productos en AliExpress para esas palabras clave.",
                "camofox_status": "online",
            }

        # Step 2: Visit each product page and extract data
        results = []
        for url in product_urls:
            if len(results) >= max_products:
                break

            log.info(f"[AE PRODUCT] Visiting {url}")
            tab_id = await _create_tab(client, url)
            if not tab_id:
                continue

            await asyncio.sleep(3)  # Let page render
            snap = await _snapshot(client, tab_id)
            await _close_tab(client, tab_id)

            product = await _extract_product_from_snapshot(snap, url)
            if not product:
                log.warning(f"[AE PRODUCT] Could not extract data from {url}")
                continue

            # Price filter
            if min_price is not None and product["price_usd"] < min_price:
                continue
            if max_price is not None and product["price_usd"] > max_price:
                continue

            results.append(product)
            log.info(f"[AE OK] ${product['price_usd']:.2f} | {product['title'][:60]}")

            # Small delay between products
            await asyncio.sleep(1)

        # Step 3: Save to DB
        if results:
            _save_to_db(results)

        return {
            "added": len(results),
            "keywords": keywords,
            "source": "aliexpress",
            "products": results,
            "success": True,
            "camofox_status": "online",
        }


async def check_camofox_status() -> Dict:
    """Return Camofox status for the health endpoint."""
    alive = await _camofox_health()
    return {
        "camofox": "online" if alive else "offline",
        "camofox_url": CAMOFOX_URL,
    }
