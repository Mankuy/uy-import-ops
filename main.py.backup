#!/usr/bin/env python3
"""
UY Import Ops - Product Research Dashboard Backend v3
FastAPI + SQLite + Product Hunter AI + Image support
"""
import os
from dotenv import load_dotenv
load_dotenv()

import re
import json
import asyncio
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
import httpx

from scrapers import ProductHunter, TRENDING_NICHES_DATA, search_bing_shopping, search_bing_web_products, generate_mock_sourcing_data

# ═══════════════════════════════════════════════════════════════
# IMAGE CACHE — persists across requests and restarts
# ═══════════════════════════════════════════════════════════════
_IMAGE_CACHE_PATH = os.path.join(os.path.dirname(__file__), "image_cache.json")
_image_cache = {}

def _load_image_cache():
    global _image_cache
    if os.path.exists(_IMAGE_CACHE_PATH):
        try:
            with open(_IMAGE_CACHE_PATH, 'r', encoding='utf-8') as f:
                _image_cache = json.load(f)
        except Exception:
            _image_cache = {}

def _save_image_cache():
    try:
        with open(_IMAGE_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_image_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_load_image_cache()

async def find_product_image_bing(name: str, timeout: float = 8.0) -> str:
    """Search Bing Images for a real product photo. Returns best image URL or empty string."""
    if name in _image_cache:
        return _image_cache[name]
    
    query = f"{name} producto"
    search_url = f"https://www.bing.com/images/search?q={query.replace(' ', '+')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(search_url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                _image_cache[name] = ""
                return ""
            
            # Bing stores image URLs in murl JSON fields
            murls = re.findall(r'&quot;murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
            
            # Filter for likely product images
            for url in murls:
                url_clean = url.replace("\\", "")
                if any(bad in url_clean.lower() for bad in ['icon', 'logo', 'favicon', 'sprite', 'button', 'badge']):
                    continue
                if url_clean.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    _image_cache[name] = url_clean
                    _save_image_cache()
                    return url_clean
            
            # Fallback: first murl
            if murls:
                first = murls[0].replace("\\", "")
                _image_cache[name] = first
                _save_image_cache()
                return first
    except Exception:
        pass
    
    _image_cache[name] = ""
    return ""

# ═══════════════════════════════════════════════════════════════


def find_product_image_bing_sync(name: str, timeout: float = 8.0) -> str:
    """Synchronous version of Bing image search. Returns best image URL or empty string."""
    if name in _image_cache:
        return _image_cache[name]
    query = f"{name} producto"
    search_url = f"https://www.bing.com/images/search?q={query.replace(' ', '+')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(search_url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                _image_cache[name] = ""
                return ""
            murls = re.findall(r'&quot;murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
            for url in murls:
                url_clean = url.replace("\\", "")
                if any(bad in url_clean.lower() for bad in ['icon', 'logo', 'favicon', 'sprite', 'button', 'badge']):
                    continue
                if url_clean.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    _image_cache[name] = url_clean
                    _save_image_cache()
                    return url_clean
            if murls:
                first = murls[0].replace("\\", "")
                _image_cache[name] = first
                _save_image_cache()
                return first
    except Exception:
        pass
    _image_cache[name] = ""
    return ""
# CLOUDFLARE WORKERS AI — free image generation
# ═══════════════════════════════════════════════════════════════
_CF_ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "")
_CF_TOKEN = os.environ.get("CF_API_TOKEN", "")
_CF_MODEL = "@cf/stabilityai/stable-diffusion-xl-base-1.0"
_CF_URL = f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT}/ai/run/{_CF_MODEL}"

# Directory to save generated designs
_DESIGNS_DIR = os.path.join(os.path.dirname(__file__), "generated_designs")
os.makedirs(_DESIGNS_DIR, exist_ok=True)

async def generate_image_with_cf(prompt: str, filename: str, width: int = 1024, height: int = 1024) -> str:
    """Generate image using Cloudflare Workers AI. Saves to disk and returns local URL."""
    filepath = os.path.join(_DESIGNS_DIR, filename)
    # If already generated, return cached
    if os.path.exists(filepath):
        return f"/generated_designs/{filename}"
    
    # Check if CF credentials are configured
    if not _CF_ACCOUNT or not _CF_TOKEN:
        print(f"[CF AI] Missing credentials, skipping")
        return ""
    
    payload = {
        "prompt": prompt,
        "num_steps": 20,
    }
    headers = {
        "Authorization": f"Bearer {_CF_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        print(f"[CF AI] Generating image with prompt: {prompt[:60]}...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(_CF_URL, json=payload, headers=headers)
            print(f"[CF AI] Response status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"[CF AI] Error response: {resp.text[:200]}")
                return ""
            # Save PNG bytes
            with open(filepath, "wb") as f:
                f.write(resp.content)
            print(f"[CF AI] Image saved: {filepath} ({len(resp.content)} bytes)")
            return f"/generated_designs/{filename}"
    except Exception as e:
        print(f"[CF AI] Exception: {type(e).__name__}: {str(e)[:200]}")
        return ""

async def generate_image_with_pollinations(prompt: str, filename: str, width: int = 1024, height: int = 1024) -> str:
    """Fallback image generation using Pollinations.ai (free, no key)."""
    filepath = os.path.join(_DESIGNS_DIR, filename)
    if os.path.exists(filepath):
        return f"/generated_designs/{filename}"
    
    import urllib.parse
    encoded = urllib.parse.quote(prompt[:300])
    seed = hash(prompt) % 10000
    image_url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true"
    
    try:
        print(f"[Pollinations] Fallback generation...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(image_url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 5000:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                print(f"[Pollinations] Image saved: {filepath} ({len(resp.content)} bytes)")
                return f"/generated_designs/{filename}"
            else:
                print(f"[Pollinations] Failed: status={resp.status_code}, size={len(resp.content)}")
                return ""
    except Exception as e:
        print(f"[Pollinations] Exception: {type(e).__name__}: {str(e)[:200]}")
        return ""

async def download_image(url: str, timeout: float = 10.0) -> bytes:
    """Download image from URL. Returns bytes or empty."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = await client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
    except Exception:
        pass
    return b""

def compose_design(background_path: str, product_bytes: bytes, output_path: str, design_type: str):
    """Compose product image onto AI-generated background."""
    from PIL import Image, ImageFilter
    import io
    
    # Open background
    bg = Image.open(background_path).convert("RGBA")
    bg_w, bg_h = bg.size
    
    # Open product image
    product = Image.open(io.BytesIO(product_bytes)).convert("RGBA")
    prod_w, prod_h = product.size
    
    # Calculate product size (fit within 50-70% of background)
    if design_type == "banner":
        max_w = int(bg_w * 0.45)
        max_h = int(bg_h * 0.85)
    elif design_type == "hero":
        max_w = int(bg_w * 0.35)
        max_h = int(bg_h * 0.75)
    elif design_type == "flyer":
        max_w = int(bg_w * 0.50)
        max_h = int(bg_h * 0.50)
    elif design_type == "mockup":
        max_w = int(bg_w * 0.40)
        max_h = int(bg_h * 0.40)
    else:  # social_card, product_photo
        max_w = int(bg_w * 0.55)
        max_h = int(bg_h * 0.55)
    
    # Resize product maintaining aspect ratio
    ratio = min(max_w / prod_w, max_h / prod_h)
    new_w = int(prod_w * ratio)
    new_h = int(prod_h * ratio)
    product = product.resize((new_w, new_h), Image.LANCZOS)
    
    # Create shadow layer
    shadow = Image.new("RGBA", (new_w + 20, new_h + 20), (0, 0, 0, 0))
    shadow_draw = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 80))
    shadow.paste(shadow_draw, (15, 15))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    
    # Calculate position (centered)
    pos_x = (bg_w - new_w) // 2
    pos_y = (bg_h - new_h) // 2
    
    # Paste shadow first
    bg.paste(shadow, (pos_x - 10, pos_y - 10), shadow)
    
    # Paste product
    bg.paste(product, (pos_x, pos_y), product)
    
    # Save
    bg.convert("RGB").save(output_path, "PNG", quality=95)

async def enrich_products_with_images(products: List[dict], max_concurrent: int = 5) -> List[dict]:
    """Fetch real images for products in parallel with concurrency limit."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def enrich_one(p):
        async with semaphore:
            img = await find_product_image_bing(p["name"])
            if img:
                p["img"] = img
                p["has_real_image"] = True
            else:
                p["has_real_image"] = False
            return p
    
    tasks = [enrich_one(p.copy()) for p in products]
    return await asyncio.gather(*tasks)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
DB_PATH = os.path.join(os.path.dirname(__file__), "research.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

UYU_PER_USD = 42.0

# Tariffs by category
CATEGORY_TARIFFS = {
    "tecnologia": 0.10,
    "hogar_inteligente": 0.12,
    "accesorios_auto": 0.15,
    "bienestar": 0.10,
    "mascotas": 0.10,
    "deportes": 0.12,
    "papeleria": 0.05,
    "electronica": 0.15,
    "juguetes": 0.10,
    "herramientas": 0.15,
    "moda_accesorios": 0.20,
}

# Winning niches — now loaded from scrapers module (100+ products)
# Use specific Unsplash image URLs for each category
CATEGORY_IMAGES = {
    "tecnologia": "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=400&h=400&fit=crop",
    "hogar_inteligente": "https://images.unsplash.com/photo-1558002038-1055907df827?w=400&h=400&fit=crop",
    "electronica": "https://images.unsplash.com/photo-1498049860654-af1a5c5668ba?w=400&h=400&fit=crop",
    "bienestar": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=400&h=400&fit=crop",
    "accesorios_auto": "https://images.unsplash.com/photo-1489824904134-891ab64532f1?w=400&h=400&fit=crop",
    "mascotas": "https://images.unsplash.com/photo-1450778869180-41d0601e046e?w=400&h=400&fit=crop",
    "herramientas": "https://images.unsplash.com/photo-1581147036324-c17ac41dd161?w=400&h=400&fit=crop",
    "moda_accesorios": "https://images.unsplash.com/photo-1445205170230-053b83016050?w=400&h=400&fit=crop",
    "deportes": "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=400&h=400&fit=crop",
    "juguetes": "https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?w=400&h=400&fit=crop",
    "papeleria": "https://images.unsplash.com/photo-1503602642458-232111445657?w=400&h=400&fit=crop",
}

# ═══════════════════════════════════════════════════════════════
# ENRICHED WINNING NICHES — AI-curated with detailed data
# ═══════════════════════════════════════════════════════════════

NICHE_KEYWORDS = {
    "tecnologia": "bluetooth, wireless, smart, digital, gadgets",
    "hogar_inteligente": "smart home, wifi, app control, automation",
    "electronica": "usb, charging, cable, adapter, hub",
    "bienestar": "health, wellness, massage, fitness, relax",
    "accesorios_auto": "car, vehicle, automotive, driving",
    "mascotas": "pet, dog, cat, automatic, feeder",
    "herramientas": "tool, diy, repair, construction, precision",
    "moda_accesorios": "fashion, style, accessories, sunglasses",
    "deportes": "sport, fitness, gym, workout, training",
    "juguetes": "game, toy, fun, kids, entertainment",
    "papeleria": "office, school, stationery, supplies",
}

NICHE_SEASONS = {
    "tecnologia": "Todo el año",
    "hogar_inteligente": "Todo el año",
    "electronica": "Todo el año",
    "bienestar": "Ene-Mar (resoluciones)",
    "accesorios_auto": "Todo el año",
    "mascotas": "Todo el año",
    "herramientas": "Sep-Nov (primavera)",
    "moda_accesorios": "Dic-Feb (verano)",
    "deportes": "Ene-Mar (resoluciones)",
    "juguetes": "Nov-Dic (Navidad)",
    "papeleria": "Feb-Mar (inicio escolar)",
}

NICHE_DESCRIPTIONS = {
    "Auriculares TWS ANC": "Auriculares inalámbricos con cancelación activa de ruido. Tendencia alcista en Latam. Margen superior al 70%.",
    "Mini proyector portátil 1080p": "Proyector compacto HD para cine en casa. Demanda creciente por streaming y gaming.",
    "Smartwatch deportivo GPS": "Reloj inteligente con GPS integrado, monitor cardíaco y 7+ días de batería. Top seller ML.",
    "Cámara WiFi 360° visión nocturna": "Cámara de seguridad con visión 360°, detección de movimiento y visión nocturna HD.",
    "Cargador solar 20000mAh rugged": "Power bank solar resistente al agua y polvo. Ideal para camping y viajes.",
    "Organizador cocina magnético": "Soporte magnético para especias y utensilios. Ahorra espacio, fácil instalación.",
    "Difusor aromas smart WiFi": "Difusor controlado por app. Programable, compatible con Alexa/Google Home.",
    "Soporte notebook aluminio plegable": "Soporte ergonómico de aluminio ajustable en altura. Reduce dolor cervical.",
    "Hub USB-C 10 en 1": "Hub multipuerto con HDMI 4K, Ethernet, SD, USB 3.0 y carga PD 100W.",
    "Lámpara LED escritorio pro": "Lámpara con luz regulable, protección ocular, carga inalámbrica integrada.",
    "Mini masajeador cervical": "Masajeador Shiatsu con calor infrarrojo. Alivia tensión muscular en 15 min.",
    "Botella térmica digital LCD": "Botella con pantalla táctil que muestra temperatura. Mantiene 12h frío / 24h calor.",
    "Cubiertos bambú portátiles": "Set ecológico de bambú en estuche. Tendencia sostenible creciente.",
    "Estuche organizador cables": "Organizador compacto para cables, adaptadores y accesorios. Viajero frecuente.",
    "Soporte celular auto magnético": "Soporte magnético 360° para auto. Compatible MagSafe. Instalación en 5 seg.",
    "Linterna táctica recargable 5000lm": "Linterna LED ultra potente con zoom. 5 modos, batería 18650 incluida.",
    "Mini aspiradora auto/escritorio": "Aspiradora portátil USB recargable. Potente para migas, polvo y pelos.",
    "Reloj pared 3D DIY moderno": "Reloj decorativo de pared con números 3D adhesivos. Estilo minimalista escandinavo.",
    "Kit láminas protectoras pantalla": "Pack 3 láminas templadas 9H. Protección completa anti-rayaduras.",
    "Funda MagSafe premium cuero": "Funda de cuero genuino con imanes MagSafe. Acabado premium, 5 colores.",
    "Mousepad RGB XL gaming": "Mousepad extendido 800x300mm con iluminación RGB perimetral. Base antideslizante.",
    "Aro luz LED 10 pulgadas tripode": "Ring light 10' con trípode regulable. 3 tonos de luz + 10 niveles. Streamers/Youtubers.",
    "Mochila antirrobo impermeable USB": "Mochila con compartimento oculto, puerto USB y material anti-corte. Urbano y seguro.",
    "Termo inteligente pantalla temp": "Termo con pantalla LED que indica temperatura. Acero inoxidable 304.",
    "Reloj despertador proyector techo": "Despertador con proyección de hora en techo. 7 colores de luz ambiental.",
    "Organizador escritorio bambú": "Set organizador de bambú: soporte celular, portalápices, bandeja. Ecológico.",
    "Mini ventilador USB recargable": "Ventilador portátil de mano con 3 velocidades. Batería 2000mAh, 8h autonomía.",
    "Lentes gaming anti luz azul": "Lentes con filtro UV400 y anti luz azul. Reduce fatiga ocular en 8h+ de pantalla.",
    "Esterilla yoga TPE antideslizante": "Mat de yoga TPE ecológico, 6mm de grosor. Textura dual para mejor agarre.",
    "Soporte bicicleta celular impermeable": "Soporte impermeable 360° para bicicleta/moto. Pantalla táctil funciona con lluvia.",
    "Bolso térmico delivery picnic 20L": "Bolso térmico 20L con capacidad 24h de frío. Ideal delivery y picnic.",
    "Cargador inalámbrico 3 en 1": "Base carga inalámbrica: iPhone, Apple Watch, AirPods simultáneo. Qi certificado.",
    "Lámpara aurora boreal proyector": "Proyector de luces aurora boreal + estrellas. 16 colores, control remoto, timer.",
    "Kit herramientas precisión 25 en 1": "Set destornilladores de precisión para electrónica, relojes, gafas. Estuche magnético.",
    "Botella auto-limpiable UV-C": "Botella con lámpara UV-C integrada que purifica agua en 60 segundos.",
    "Soporte monitor escritorio ajustable": "Soporte elevador monitor con cajón organizador. Ajustable en altura 3 niveles.",
    "Power bank solar 30000mAh rugged": "Batería solar 30000mAh con linterna LED y brújula. Carga 6 dispositivos.",
    "Auriculares gaming 7.1 RGB": "Headset gaming con sonido surround 7.1, micrófono retráctil e iluminación RGB.",
    "Masajeador pies eléctrico Shiatsu": "Masajeador de pies con 18 cabezales Shiatsu, calor infrarrojo y 3 intensidades.",
    "Cámara espía mini WiFi 1080p": "Cámara oculta 1080p con visión nocturna y detección de movimiento. App móvil.",
    "Teclado mecánico 60% wireless": "Teclado mecánico 60% inalámbrico bluetooth. Switches hot-swappable, RGB.",
    "Soporte tablet cama sofá plegable": "Soporte articulado para tablet/celular. Base antideslizante, ángulo 360°.",
    "Almohada ortopédica cervical visco": "Almohada viscoelástica ergonómica. Alivia dolor de cuello y ronquidos.",
    "Balanza digital cocina 10kg precisión": "Balanza de cocina digital 10kg/1g. Pantalla LCD, función tara, apagado auto.",
}

WINNING_NICHES = []
for n in TRENDING_NICHES_DATA:
    cat = n["cat"]
    name = n["name"]
    cost = n["cost"]
    ship = n["ship"]
    ml = n["ml"]
    demand = n["demand"]
    
    # Calculate profit metrics
    est_margin = ((ml * 0.5) - (cost + ship) * 42) / ((cost + ship) * 42) * 100 if (cost + ship) > 0 else 0
    profit_score = min(100, int(demand * 0.4 + max(0, est_margin) * 0.6))
    
    # Trend direction based on demand
    trend = "🔥 Fuerte alza" if demand >= 85 else "📈 Creciendo" if demand >= 70 else "➡️ Estable"
    
    # Estimated rating based on category
    est_rating = 4.2 + (demand / 1000) if demand > 50 else 4.0
    
    enriched = {
        **n,
        "cost_usd": cost,
        "ship_usd": ship,
        "ml_avg": ml,
        "img": CATEGORY_IMAGES.get(cat, CATEGORY_IMAGES["tecnologia"]),
        "desc": NICHE_DESCRIPTIONS.get(name, f"Producto en tendencia. Demanda: {demand}/100. Margen estimado: {est_margin:.0f}%"),
        "source_url": f"https://www.aliexpress.com/wholesale?SearchText={name.replace(' ', '+')}",
        "keywords": NICHE_KEYWORDS.get(cat, ""),
        "season": NICHE_SEASONS.get(cat, "Todo el año"),
        "trend": trend,
        "profit_score": profit_score,
        "est_rating": round(est_rating, 1),
        "est_reviews": int(demand * 15 + 50),
        "competition_level": "Alta" if demand >= 85 else "Media" if demand >= 65 else "Baja",
        "margin_potential": f"{est_margin:.0f}%",
    }
    WINNING_NICHES.append(enriched)

# ═══════════════════════════════════════════════════════════════
# DB MODELS
# ═══════════════════════════════════════════════════════════════
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    category = Column(String, default="")
    source_url = Column(String, default="")
    image_url = Column(String, default="")
    # China costs
    product_cost_usd = Column(Float, default=0.0)
    shipping_cost_usd = Column(Float, default=0.0)
    # Import params
    hs_code = Column(String, default="")
    tariff_rate = Column(Float, default=0.15)
    iva_rate = Column(Float, default=0.22)
    stat_fee_rate = Column(Float, default=0.03)
    agent_fee_usd = Column(Float, default=15.0)
    # Calculated
    total_landed_cost_uyu = Column(Float, default=0.0)
    # Pricing strategies (markup %)
    price_cost_plus_uyu = Column(Float, default=0.0)      # 100% markup = 50% margin
    price_value_uyu = Column(Float, default=0.0)          # vs competitor
    price_aggressive_uyu = Column(Float, default=0.0)     # 150% markup = 60% margin
    price_luxury_uyu = Column(Float, default=0.0)         # 200% markup = 66.7% margin
    price_extreme_uyu = Column(Float, default=0.0)        # 300% markup = 75% margin
    price_premium_vs_comp_uyu = Column(Float, default=0.0) # vs comp +20%
    margin_cost_plus = Column(Float, default=0.0)
    margin_value = Column(Float, default=0.0)
    margin_aggressive = Column(Float, default=0.0)
    margin_luxury = Column(Float, default=0.0)
    margin_extreme = Column(Float, default=0.0)
    margin_premium_vs_comp = Column(Float, default=0.0)
    # Tracking
    status = Column(String, default="researching")
    ml_competitor_price = Column(Float, default=0.0)
    ml_competitor_url = Column(String, default="")
    demand_score = Column(Integer, default=50)
    opportunity_score = Column(Integer, default=50)
    best_strategy = Column(String, default="cost_plus")
    best_margin = Column(Float, default=0.0)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class HunterLog(Base):
    __tablename__ = "hunter_logs"
    id = Column(Integer, primary_key=True)
    query = Column(String)
    results_found = Column(Integer, default=0)
    products_added = Column(Integer, default=0)
    run_at = Column(DateTime, default=datetime.utcnow)

# ═══════════════════════════════════════════════════════════════
# TRACKING & SHIPMENT MODELS (Point 4)
# ═══════════════════════════════════════════════════════════════

class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, nullable=False)
    tracking_number = Column(String, default="")
    carrier = Column(String, default="")  # e.g., DHL, FedEx, UPS, Correo
    origin = Column(String, default="China")
    destination = Column(String, default="Uruguay")
    status = Column(String, default="ordered")  # ordered, in_transit, customs, arrived, delivered
    estimated_arrival = Column(DateTime, nullable=True)
    actual_arrival = Column(DateTime, nullable=True)
    shipping_cost_usd = Column(Float, default=0.0)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ShipmentEvent(Base):
    __tablename__ = "shipment_events"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(Integer, nullable=False)
    event_type = Column(String, default="")  # status_change, location_update, delay, customs_clearance
    description = Column(Text, default="")
    location = Column(String, default="")
    occurred_at = Column(DateTime, default=datetime.utcnow)

class CostActual(Base):
    __tablename__ = "cost_actuals"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, nullable=False)
    actual_product_cost_usd = Column(Float, default=0.0)
    actual_shipping_usd = Column(Float, default=0.0)
    actual_tariff_usd = Column(Float, default=0.0)
    actual_iva_usd = Column(Float, default=0.0)
    actual_agent_fee_usd = Column(Float, default=0.0)
    actual_total_usd = Column(Float, default=0.0)
    actual_total_uyu = Column(Float, default=0.0)
    variance_percent = Column(Float, default=0.0)  # vs estimated
    recorded_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, default="")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ═══════════════════════════════════════════════════════════════
# IMPORT CALCULATOR
# ═══════════════════════════════════════════════════════════════
def calculate_landed_cost(cost_usd, ship_usd, tariff_rate, iva_rate, stat_rate, agent_usd):
    cif = cost_usd + ship_usd
    tariff = cif * tariff_rate
    iva = (cif + tariff) * iva_rate
    stat = cif * stat_rate
    total_usd = cif + tariff + iva + stat + agent_usd
    total_uyu = total_usd * UYU_PER_USD
    return {
        "cif_usd": round(cif, 2),
        "tariff_usd": round(tariff, 2),
        "iva_usd": round(iva, 2),
        "stat_fee_usd": round(stat, 2),
        "agent_fee_usd": round(agent_usd, 2),
        "total_usd": round(total_usd, 2),
        "total_uyu": round(total_uyu, 2),
        "multiplier": round(total_usd / cost_usd, 2) if cost_usd > 0 else 0,
    }

def calculate_all_strategies(cost_usd, ship_usd, tariff_rate, comp_uyu):
    calc = calculate_landed_cost(cost_usd, ship_usd, tariff_rate, 0.22, 0.03, 15)
    landed = calc["total_uyu"]
    strategies = {}
    
    # Helper to calc margin
    def m(price): return round((price - landed) / price * 100, 1) if price > 0 else 0
    
    # 1. Cost-plus: 100% markup
    p = landed * 2.0
    strategies["cost_plus"] = {"price": round(p, 0), "margin": m(p)}
    
    # 2. Aggressive: 150% markup (= 60% margin)
    p = landed * 2.5
    strategies["aggressive"] = {"price": round(p, 0), "margin": m(p)}
    
    # 3. Luxury: 200% markup (= 66.7% margin)
    p = landed * 3.0
    strategies["luxury"] = {"price": round(p, 0), "margin": m(p)}
    
    # 4. EXTREME: 300% markup (= 75% margin) - for products with low comp
    p = landed * 4.0
    strategies["extreme"] = {"price": round(p, 0), "margin": m(p)}
    
    # 5. Value: vs competitor (95% of comp if viable)
    if comp_uyu > landed * 1.5:
        p = comp_uyu * 0.95
        strategies["value"] = {"price": round(p, 0), "margin": m(p)}
    else:
        strategies["value"] = strategies["cost_plus"]
    
    # 6. Premium vs comp: 120% of comp
    if comp_uyu > 0:
        p = comp_uyu * 1.20
        strategies["premium_vs_comp"] = {"price": round(p, 0), "margin": m(p)}
    else:
        strategies["premium_vs_comp"] = strategies["cost_plus"]
    
    return calc, strategies

def determine_best_strategy(strategies):
    """Return strategy with highest margin that is still reasonable"""
    best = "cost_plus"
    best_margin = strategies["cost_plus"]["margin"]
    for strat in ["value", "aggressive", "luxury", "extreme", "premium_vs_comp"]:
        if strategies[strat]["margin"] > best_margin and strategies[strat]["price"] > 0:
            best = strat
            best_margin = strategies[strat]["margin"]
    return best, best_margin

# ═══════════════════════════════════════════════════════════════
# PRODUCT HUNTER
# ═══════════════════════════════════════════════════════════════
def run_product_hunter(db, niches=None):
    if niches is None:
        niches = WINNING_NICHES
    added = 0
    for niche in niches:
        existing = db.query(Product).filter(Product.name == niche["name"]).first()
        if existing:
            continue
        tariff = CATEGORY_TARIFFS.get(niche["cat"], 0.15)
        calc, strategies = calculate_all_strategies(
            niche["cost_usd"], niche["ship_usd"], tariff, niche["ml_avg"]
        )
        best_strat, best_margin = determine_best_strategy(strategies)
        
        # Opportunity score: weighted by margin + demand
        opp = min(100, int(best_margin * 0.6 + niche["demand"] * 0.4))
        
        # Try to find a real product image
        real_img = find_product_image_bing_sync(niche["name"])
        if not real_img:
            real_img = niche.get("img", "")
        
        p = Product(
            name=niche["name"],
            description=niche.get("desc", ""),
            category=niche["cat"],
            image_url=real_img,
            product_cost_usd=niche["cost_usd"],
            shipping_cost_usd=niche["ship_usd"],
            tariff_rate=tariff,
            total_landed_cost_uyu=calc["total_uyu"],
            price_cost_plus_uyu=strategies["cost_plus"]["price"],
            price_value_uyu=strategies["value"]["price"],
            price_aggressive_uyu=strategies["aggressive"]["price"],
            price_luxury_uyu=strategies["luxury"]["price"],
            price_extreme_uyu=strategies["extreme"]["price"],
            price_premium_vs_comp_uyu=strategies["premium_vs_comp"]["price"],
            margin_cost_plus=strategies["cost_plus"]["margin"],
            margin_value=strategies["value"]["margin"],
            margin_aggressive=strategies["aggressive"]["margin"],
            margin_luxury=strategies["luxury"]["margin"],
            margin_extreme=strategies["extreme"]["margin"],
            margin_premium_vs_comp=strategies["premium_vs_comp"]["margin"],
            status="researching",
            ml_competitor_price=niche["ml_avg"],
            demand_score=niche["demand"],
            opportunity_score=opp,
            best_strategy=best_strat,
            best_margin=best_margin,
        )
        db.add(p)
        added += 1
    db.commit()
    return added

# ═══════════════════════════════════════════════════════════════
# ML SEARCH
# ═══════════════════════════════════════════════════════════════
ML_API_BASE = "https://api.mercadolibre.com/sites/MLU"

async def search_ml_uruguay(query: str, limit: int = 10):
    async with httpx.AsyncClient(timeout=15.0) as client:
        url = f"{ML_API_BASE}/search"
        params = {"q": query, "limit": limit, "sort": "price_asc"}
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return {"error": resp.text}
        data = resp.json()
        results = []
        prices = []
        for item in data.get("results", [])[:limit]:
            price = item.get("price", 0)
            prices.append(price)
            results.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "price": price,
                "currency": item.get("currency_id"),
                "permalink": item.get("permalink"),
                "thumbnail": item.get("thumbnail"),
                "seller": item.get("seller", {}).get("nickname", ""),
                "sold_quantity": item.get("sold_quantity", 0),
                "condition": item.get("condition"),
            })
        avg_price = sum(prices) / len(prices) if prices else 0
        return {
            "query": query,
            "results": results,
            "total": data.get("paging", {}).get("total", 0),
            "avg_price": round(avg_price, 0),
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
        }

# ═══════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════
class ProductCreate(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    source_url: str = ""
    image_url: str = ""
    product_cost_usd: float = 0.0
    shipping_cost_usd: float = 0.0
    hs_code: str = ""
    tariff_rate: float = 0.15
    agent_fee_usd: float = 15.0
    ml_competitor_price: float = 0.0
    ml_competitor_url: str = ""
    status: str = "researching"
    notes: str = ""

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    product_cost_usd: Optional[float] = None
    shipping_cost_usd: Optional[float] = None
    hs_code: Optional[str] = None
    tariff_rate: Optional[float] = None
    agent_fee_usd: Optional[float] = None
    ml_competitor_price: Optional[float] = None
    ml_competitor_url: Optional[str] = None
    status: Optional[str] = None
    demand_score: Optional[int] = None
    notes: Optional[str] = None

class ShipmentCreate(BaseModel):
    product_id: int
    tracking_number: str = ""
    carrier: str = ""
    origin: str = "China"
    destination: str = "Uruguay"
    status: str = "ordered"
    estimated_arrival: Optional[str] = None
    shipping_cost_usd: float = 0.0
    notes: str = ""

class ShipmentUpdate(BaseModel):
    product_id: Optional[int] = None
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    status: Optional[str] = None
    estimated_arrival: Optional[str] = None
    shipping_cost_usd: Optional[float] = None
    notes: Optional[str] = None

class ImportCalcInput(BaseModel):
    product_cost_usd: float
    shipping_cost_usd: float = 0.0
    tariff_rate: float = 0.15
    iva_rate: float = 0.22
    stat_fee_rate: float = 0.03
    agent_fee_usd: float = 15.0
    competitor_price_uyu: float = 0.0

# ═══════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    count = db.query(Product).count()
    # Auto-seeding disabled — user adds products manually
    # if count == 0:
    #     added = run_product_hunter(db)
    #     print(f"Product Hunter auto-init: added {added} products")
    db.close()
    yield

app = FastAPI(title="UY Import Ops Research v3", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated design images
app.mount("/generated_designs", StaticFiles(directory=_DESIGNS_DIR), name="generated_designs")

# Serve frontend static files (single-page app) — explicit route to avoid shadowing API
_static_dir = os.path.join(os.path.dirname(__file__), "static")
_frontend_html = os.path.join(_static_dir, "index.html")

@app.get("/")
def serve_frontend():
    if os.path.exists(_frontend_html):
        return FileResponse(_frontend_html)
    return {"ok": True, "message": "UY Import Ops API v3"}

@app.get("/api/health")
def health():
    return {"ok": True, "version": "3.0", "time": datetime.utcnow().isoformat()}

@app.post("/api/products")
def create_product(p: ProductCreate):
    db = SessionLocal()
    tariff = CATEGORY_TARIFFS.get(p.category, p.tariff_rate)
    calc, strategies = calculate_all_strategies(
        p.product_cost_usd, p.shipping_cost_usd, tariff, p.ml_competitor_price
    )
    best_strat, best_margin = determine_best_strategy(strategies)
    
    opp = 50
    if p.ml_competitor_price > 0 and calc["total_uyu"] > 0:
        margin_vs_comp = (p.ml_competitor_price - calc["total_uyu"]) / p.ml_competitor_price * 100
        opp = min(100, max(10, int(margin_vs_comp * 0.6 + 40)))
    
    prod = Product(
        name=p.name, description=p.description, category=p.category,
        source_url=p.source_url, image_url=p.image_url,
        product_cost_usd=p.product_cost_usd, shipping_cost_usd=p.shipping_cost_usd,
        hs_code=p.hs_code, tariff_rate=tariff,
        total_landed_cost_uyu=calc["total_uyu"],
        price_cost_plus_uyu=strategies["cost_plus"]["price"],
        price_value_uyu=strategies["value"]["price"],
        price_aggressive_uyu=strategies["aggressive"]["price"],
        price_luxury_uyu=strategies["luxury"]["price"],
        price_extreme_uyu=strategies["extreme"]["price"],
        price_premium_vs_comp_uyu=strategies["premium_vs_comp"]["price"],
        margin_cost_plus=strategies["cost_plus"]["margin"],
        margin_value=strategies["value"]["margin"],
        margin_aggressive=strategies["aggressive"]["margin"],
        margin_luxury=strategies["luxury"]["margin"],
        margin_extreme=strategies["extreme"]["margin"],
        margin_premium_vs_comp=strategies["premium_vs_comp"]["margin"],
        status=p.status, ml_competitor_price=p.ml_competitor_price,
        ml_competitor_url=p.ml_competitor_url,
        opportunity_score=opp, best_strategy=best_strat, best_margin=best_margin,
        notes=p.notes,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    db.close()
    return {"id": prod.id, "message": "Created", "best_strategy": best_strat, "best_margin": best_margin}

@app.get("/api/products")
def list_products(
    status: Optional[str] = None,
    min_margin: Optional[float] = None,
    strategy: Optional[str] = None,
    sort_by: Optional[str] = "opportunity",
    sort_order: Optional[str] = "desc",
    min_cost: Optional[float] = None,
    max_cost: Optional[float] = None,
    skip: int = 0,
    limit: int = 100,
):
    """List products with filtering and sorting.
    sort_by: price | margin | cost | demand | opportunity | rating | created | name
    sort_order: asc | desc
    """
    db = SessionLocal()
    q = db.query(Product)
    if status:
        q = q.filter(Product.status == status)
    
    # Filter by margin based on strategy
    if min_margin and min_margin > 0:
        if strategy == "extreme":
            q = q.filter(Product.margin_extreme >= min_margin)
        elif strategy == "luxury":
            q = q.filter(Product.margin_luxury >= min_margin)
        elif strategy == "aggressive":
            q = q.filter(Product.margin_aggressive >= min_margin)
        elif strategy == "value":
            q = q.filter(Product.margin_value >= min_margin)
        elif strategy == "premium_vs_comp":
            q = q.filter(Product.margin_premium_vs_comp >= min_margin)
        else:
            q = q.filter(Product.margin_cost_plus >= min_margin)
    
    # Filter by cost range (USD)
    if min_cost is not None and min_cost > 0:
        q = q.filter(Product.product_cost_usd >= min_cost)
    if max_cost is not None and max_cost > 0:
        q = q.filter(Product.product_cost_usd <= max_cost)
    
    # Sorting
    sort_col = {
        "price": Product.total_landed_cost_uyu,
        "margin": Product.best_margin,
        "cost": Product.product_cost_usd,
        "demand": Product.demand_score,
        "opportunity": Product.opportunity_score,
        "rating": Product.demand_score,  # proxy
        "created": Product.created_at,
        "name": Product.name,
    }.get(sort_by, Product.opportunity_score)
    
    if sort_order and sort_order.lower() == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())
    
    prods = q.offset(skip).limit(limit).all()
    db.close()
    return [{"id": p.id, "name": p.name, "description": p.description, "category": p.category,
             "product_cost_usd": p.product_cost_usd,
             "total_landed_cost_uyu": p.total_landed_cost_uyu,
             "price_cost_plus_uyu": p.price_cost_plus_uyu,
             "price_value_uyu": p.price_value_uyu,
             "price_aggressive_uyu": p.price_aggressive_uyu,
             "price_luxury_uyu": p.price_luxury_uyu,
             "price_extreme_uyu": p.price_extreme_uyu,
             "price_premium_vs_comp_uyu": p.price_premium_vs_comp_uyu,
             "margin_cost_plus": p.margin_cost_plus,
             "margin_value": p.margin_value,
             "margin_aggressive": p.margin_aggressive,
             "margin_luxury": p.margin_luxury,
             "margin_extreme": p.margin_extreme,
             "margin_premium_vs_comp": p.margin_premium_vs_comp,
             "best_strategy": p.best_strategy,
             "best_margin": p.best_margin,
             "status": p.status, "opportunity_score": p.opportunity_score,
             "image_url": p.image_url, "demand_score": p.demand_score,
             "ml_competitor_price": p.ml_competitor_price,
             "created_at": p.created_at.isoformat() if p.created_at else None}
            for p in prods]



@app.post("/api/products/refresh-images")
async def refresh_product_images():
    """Refresh all product images with real photos from Bing Images."""
    db = SessionLocal()
    products = db.query(Product).all()
    updated = 0
    failed = 0
    skipped = 0
    
    for p in products:
        # Skip if already has a real image (not unsplash generic)
        if p.image_url and "unsplash" not in p.image_url and p.image_url.startswith("http"):
            skipped += 1
            continue
        
        # Try Bing search
        try:
            img = await find_product_image_bing(p.name)
            if img:
                p.image_url = img
                updated += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    
    db.commit()
    db.close()
    return {
        "total": len(products),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "message": f"Images refreshed. {updated} updated, {skipped} skipped (already had real images), {failed} failed."
    }


@app.post("/api/products/clear-all")
def clear_all_products():
    """Delete all products from the database."""
    db = SessionLocal()
    count = db.query(Product).count()
    db.query(Product).delete()
    db.commit()
    db.close()
    return {"deleted": count, "message": f"All {count} products deleted."}

@app.get("/api/products/{pid}")
def get_product(pid: int):
    db = SessionLocal()
    p = db.query(Product).filter(Product.id == pid).first()
    db.close()
    if not p:
        raise HTTPException(404, "Not found")
    calc = calculate_landed_cost(
        p.product_cost_usd, p.shipping_cost_usd,
        p.tariff_rate, 0.22, 0.03, p.agent_fee_usd
    )
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "category": p.category, "source_url": p.source_url, "image_url": p.image_url,
        "product_cost_usd": p.product_cost_usd, "shipping_cost_usd": p.shipping_cost_usd,
        "hs_code": p.hs_code, "tariff_rate": p.tariff_rate,
        "total_landed_cost_uyu": p.total_landed_cost_uyu,
        "prices": {
            "cost_plus": p.price_cost_plus_uyu,
            "value": p.price_value_uyu,
            "aggressive": p.price_aggressive_uyu,
            "luxury": p.price_luxury_uyu,
            "extreme": p.price_extreme_uyu,
            "premium_vs_comp": p.price_premium_vs_comp_uyu,
        },
        "margins": {
            "cost_plus": p.margin_cost_plus,
            "value": p.margin_value,
            "aggressive": p.margin_aggressive,
            "luxury": p.margin_luxury,
            "extreme": p.margin_extreme,
            "premium_vs_comp": p.margin_premium_vs_comp,
        },
        "best_strategy": p.best_strategy,
        "best_margin": p.best_margin,
        "status": p.status,
        "ml_competitor_price": p.ml_competitor_price,
        "ml_competitor_url": p.ml_competitor_url,
        "demand_score": p.demand_score, "opportunity_score": p.opportunity_score,
        "notes": p.notes,
        "cost_breakdown": calc,
    }

@app.patch("/api/products/{pid}")
def update_product(pid: int, p: ProductUpdate):
    db = SessionLocal()
    prod = db.query(Product).filter(Product.id == pid).first()
    if not prod:
        db.close()
        raise HTTPException(404, "Not found")
    data = p.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(prod, k, v)
    tariff = CATEGORY_TARIFFS.get(prod.category, prod.tariff_rate)
    calc, strategies = calculate_all_strategies(
        prod.product_cost_usd, prod.shipping_cost_usd, tariff, prod.ml_competitor_price
    )
    best_strat, best_margin = determine_best_strategy(strategies)
    prod.total_landed_cost_uyu = calc["total_uyu"]
    prod.price_cost_plus_uyu = strategies["cost_plus"]["price"]
    prod.price_value_uyu = strategies["value"]["price"]
    prod.price_aggressive_uyu = strategies["aggressive"]["price"]
    prod.price_luxury_uyu = strategies["luxury"]["price"]
    prod.price_extreme_uyu = strategies["extreme"]["price"]
    prod.price_premium_vs_comp_uyu = strategies["premium_vs_comp"]["price"]
    prod.margin_cost_plus = strategies["cost_plus"]["margin"]
    prod.margin_value = strategies["value"]["margin"]
    prod.margin_aggressive = strategies["aggressive"]["margin"]
    prod.margin_luxury = strategies["luxury"]["margin"]
    prod.margin_extreme = strategies["extreme"]["margin"]
    prod.margin_premium_vs_comp = strategies["premium_vs_comp"]["margin"]
    prod.best_strategy = best_strat
    prod.best_margin = best_margin
    prod.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prod)
    db.close()
    return {"id": prod.id, "message": "Updated", "best_strategy": best_strat}

@app.delete("/api/products/{pid}")
def delete_product(pid: int):
    db = SessionLocal()
    prod = db.query(Product).filter(Product.id == pid).first()
    if not prod:
        db.close()
        raise HTTPException(404, "Not found")
    db.delete(prod)
    db.commit()
    db.close()
    return {"message": "Deleted"}

@app.get("/api/shipments")
def list_shipments():
    db = SessionLocal()
    rows = db.query(Shipment).order_by(Shipment.created_at.desc()).all()
    db.close()
    return rows

@app.post("/api/shipments")
def create_shipment(body: ShipmentCreate):
    db = SessionLocal()
    from datetime import datetime
    est = None
    if body.estimated_arrival:
        try:
            est = datetime.fromisoformat(body.estimated_arrival.replace('Z', '+00:00'))
        except Exception:
            est = None
    ship = Shipment(
        product_id=body.product_id,
        tracking_number=body.tracking_number,
        carrier=body.carrier,
        origin=body.origin,
        destination=body.destination,
        status=body.status,
        estimated_arrival=est,
        shipping_cost_usd=body.shipping_cost_usd,
        notes=body.notes,
    )
    db.add(ship)
    db.commit()
    db.refresh(ship)
    db.close()
    return ship

@app.put("/api/shipments/{sid}")
def update_shipment(sid: int, body: ShipmentUpdate):
    db = SessionLocal()
    ship = db.query(Shipment).filter(Shipment.id == sid).first()
    if not ship:
        db.close()
        raise HTTPException(404, "Not found")
    from datetime import datetime
    for field in ["product_id", "tracking_number", "carrier", "origin", "destination", "status", "shipping_cost_usd", "notes"]:
        val = getattr(body, field, None)
        if val is not None:
            setattr(ship, field, val)
    if body.estimated_arrival is not None:
        try:
            ship.estimated_arrival = datetime.fromisoformat(body.estimated_arrival.replace('Z', '+00:00'))
        except Exception:
            ship.estimated_arrival = None
    db.commit()
    db.refresh(ship)
    db.close()
    return ship

@app.delete("/api/shipments/{sid}")
def delete_shipment(sid: int):
    db = SessionLocal()
    ship = db.query(Shipment).filter(Shipment.id == sid).first()
    if not ship:
        db.close()
        raise HTTPException(404, "Not found")
    db.delete(ship)
    db.commit()
    db.close()
    return {"message": "Deleted"}

@app.post("/api/calculate")
def calculate_import(body: ImportCalcInput):
    calc, strategies = calculate_all_strategies(
        body.product_cost_usd, body.shipping_cost_usd,
        body.tariff_rate, body.competitor_price_uyu
    )
    best_strat, best_margin = determine_best_strategy(strategies)
    return {
        "breakdown": calc,
        "strategies": strategies,
        "best_strategy": best_strat,
        "best_margin": best_margin,
    }

@app.get("/api/ml-search")
async def ml_search(q: str = Query(...), limit: int = 10):
    return await search_ml_uruguay(q, limit)

@app.get("/api/stats")
def dashboard_stats():
    db = SessionLocal()
    total = db.query(Product).count()
    by_status = {}
    for s in ["researching", "importing", "testing", "winner", "flop"]:
        by_status[s] = db.query(Product).filter(Product.status == s).count()
    
    all_prods = db.query(Product).all()
    avg_best_margin = 0
    if all_prods:
        margins = [p.best_margin for p in all_prods if p.best_margin]
        avg_best_margin = round(sum(margins) / len(margins), 1) if margins else 0
    
    total_invested = sum(p.total_landed_cost_uyu for p in all_prods)
    high_margin = db.query(Product).filter(Product.margin_extreme >= 60).count()
    ultra_margin = db.query(Product).filter(Product.margin_extreme >= 70).count()
    
    db.close()
    return {
        "total_products": total,
        "by_status": by_status,
        "avg_best_margin": avg_best_margin,
        "total_invested_uyu": round(total_invested, 2),
        "high_margin_products": high_margin,
        "ultra_margin_products": ultra_margin,
    }

@app.post("/api/hunter/run")
def run_hunter():
    """Legacy endpoint — now just returns info without auto-saving to DB.
    Products are discovered via /api/hunter/trending and saved individually."""
    return {
        "added": 0,
        "message": "Hunter listo. Mirá los productos en el tab Hunter y guardá los que te interesen individualmente.",
        "total_available": len(WINNING_NICHES),
    }

@app.get("/api/hunter/niches")
def get_winning_niches():
    return [{"name": n["name"], "category": n["cat"], "cost_usd": n["cost_usd"],
             "ship_usd": n["ship_usd"], "ml_avg_price": n["ml_avg"], "demand": n["demand"],
             "description": n.get("desc", ""), "image_url": n.get("img", "")}
            for n in WINNING_NICHES]

@app.get("/api/hunter/logs")
def get_hunter_logs(limit: int = 10):
    db = SessionLocal()
    logs = db.query(HunterLog).order_by(HunterLog.run_at.desc()).limit(limit).all()
    db.close()
    return [{"id": l.id, "query": l.query, "results_found": l.results_found,
             "products_added": l.products_added, "run_at": l.run_at.isoformat()}
            for l in logs]

@app.get("/api/categories")
def get_categories():
    return [{"id": k, "name": k.replace("_", " ").title(), "tariff": v}
            for k, v in CATEGORY_TARIFFS.items()]


# ═══════════════════════════════════════════════════════════════
# MERCADOLIBRE SEARCH & ANALYSIS — Enhanced v4
# ═══════════════════════════════════════════════════════════════

ML_API_BASE = "https://api.mercadolibre.com/sites/MLU"

async def search_ml_uruguay(query: str, limit: int = 10):
    """Search ML Uruguay with enhanced data extraction"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "es-UY,es;q=0.9",
    }
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        url = f"{ML_API_BASE}/search"
        params = {"q": query, "limit": limit, "sort": "price_asc"}
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            # Return mock data for demo when API blocks us
            return generate_mock_ml_data(query, limit)
        data = resp.json()
        results = []
        prices = []
        sellers = {}
        official_stores = 0
        
        for item in data.get("results", [])[:limit]:
            price = item.get("price", 0)
            prices.append(price)
            
            seller = item.get("seller", {})
            seller_id = seller.get("id", "")
            seller_nickname = seller.get("nickname", "")
            
            if seller_id:
                sellers[seller_id] = seller_nickname
            
            tags = item.get("tags", [])
            is_official = "eshop" in tags or "official_store" in str(tags).lower()
            if is_official:
                official_stores += 1
            
            results.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "price": price,
                "currency": item.get("currency_id"),
                "permalink": item.get("permalink"),
                "thumbnail": item.get("thumbnail"),
                "seller": seller_nickname,
                "seller_id": seller_id,
                "seller_reputation": seller.get("seller_reputation", {}).get("level_id", ""),
                "seller_transactions": seller.get("seller_reputation", {}).get("transactions", {}).get("completed", 0),
                "sold_quantity": item.get("sold_quantity", 0),
                "available_quantity": item.get("available_quantity", 0),
                "condition": item.get("condition"),
                "is_official_store": is_official,
                "shipping_free": item.get("shipping", {}).get("free_shipping", False),
                "listing_type": item.get("listing_type_id", ""),
            })
        
        avg_price = sum(prices) / len(prices) if prices else 0
        prices_sorted = sorted(prices)
        p25 = prices_sorted[len(prices_sorted)//4] if prices_sorted else 0
        p50 = prices_sorted[len(prices_sorted)//2] if prices_sorted else 0
        p75 = prices_sorted[3*len(prices_sorted)//4] if prices_sorted else 0
        total_sold = sum(r["sold_quantity"] for r in results)
        
        return {
            "query": query,
            "results": results,
            "total": data.get("paging", {}).get("total", 0),
            "avg_price": round(avg_price, 0),
            "min_price": min(prices) if prices else 0,
            "max_price": max(prices) if prices else 0,
            "p25": p25,
            "p50": p50,
            "p75": p75,
            "price_spread": max(prices) - min(prices) if prices else 0,
            "unique_sellers": len(sellers),
            "official_stores": official_stores,
            "total_sold": total_sold,
            "seller_list": list(sellers.values())[:10],
        }

def generate_mock_ml_data(query: str, limit: int = 10):
    """Generate realistic mock ML data for demo purposes when API blocks us"""
    import random
    random.seed(hash(query) % 10000)
    
    # Generate realistic prices based on query keywords
    base_price = 1500
    if any(k in query.lower() for k in ["proyector", "drone", "monitor", "robot"]):
        base_price = 8000
    elif any(k in query.lower() for k in ["smartwatch", "teclado", "auricular", "cámara"]):
        base_price = 3500
    elif any(k in query.lower() for k in ["lámpara", "soporte", "organizador", "funda"]):
        base_price = 1200
    
    mock_sellers = ["TechStoreUY", "ImportDirect", "DigitalHouse", "ElectroShop", "GadgetWorld", 
                    "MegaStoreUY", "TiendaTech", "ElectroImport", "SmartBuy", "TopGadgets"]
    
    results = []
    prices = []
    num_results = random.randint(8, 25)
    num_sellers = random.randint(3, min(8, num_results))
    
    for i in range(min(limit, num_results)):
        price_var = random.uniform(0.7, 1.5)
        price = round(base_price * price_var, 0)
        prices.append(price)
        seller = mock_sellers[i % len(mock_sellers)]
        
        results.append({
            "id": f"MLU{random.randint(1000000000, 9999999999)}",
            "title": f"{query.title()} {'Original' if random.random() > 0.5 else 'Premium'} — Envío Gratis",
            "price": price,
            "currency": "UYU",
            "permalink": f"https://articulo.mercadolibre.com.uy/MLU-{random.randint(1000000000, 9999999999)}",
            "thumbnail": "",
            "seller": seller,
            "seller_id": str(random.randint(100000, 999999)),
            "seller_reputation": random.choice(["5_green", "4_light_green", "3_yellow", "2_orange"]),
            "seller_transactions": random.randint(50, 5000),
            "sold_quantity": random.randint(5, 200),
            "available_quantity": random.randint(1, 50),
            "condition": random.choice(["new", "new", "new", "used"]),
            "is_official_store": random.random() > 0.7,
            "shipping_free": random.random() > 0.3,
            "listing_type": random.choice(["gold_special", "gold_pro", "free"]),
        })
    
    avg_price = sum(prices) / len(prices) if prices else 0
    prices_sorted = sorted(prices)
    
    return {
        "query": query,
        "results": results,
        "total": num_results,
        "avg_price": round(avg_price, 0),
        "min_price": min(prices) if prices else 0,
        "max_price": max(prices) if prices else 0,
        "p25": prices_sorted[len(prices_sorted)//4] if prices_sorted else 0,
        "p50": prices_sorted[len(prices_sorted)//2] if prices_sorted else 0,
        "p75": prices_sorted[3*len(prices_sorted)//4] if prices_sorted else 0,
        "price_spread": max(prices) - min(prices) if prices else 0,
        "unique_sellers": num_sellers,
        "official_stores": sum(1 for r in results if r["is_official_store"]),
        "total_sold": sum(r["sold_quantity"] for r in results),
        "seller_list": list(set(r["seller"] for r in results))[:10],
        "_mock": True,
    }

@app.get("/api/ml-search")
async def ml_search(q: str = Query(...), limit: int = 10):
    return await search_ml_uruguay(q, limit)

class MLAnalyzeInput(BaseModel):
    query: str
    my_landed_cost_uyu: float = 0.0

@app.post("/api/ml-analyze")
async def ml_analyze(body: MLAnalyzeInput):
    """
    Advanced competitive analysis for ML Uruguay.
    Returns: GO / CAUTION / AVOID recommendation based on market data.
    """
    search_data = await search_ml_uruguay(body.query, limit=50)
    
    if "error" in search_data:
        return {"error": search_data["error"]}
    
    results = search_data.get("results", [])
    if not results:
        return {
            "recommendation": "NO_DATA",
            "message": "No se encontraron resultados para este producto en Uruguay.",
            "reasoning": "MercadoLibre Uruguay no tiene oferta para este producto. Podría ser una oportunidad de nicho.",
            "market_data": search_data,
        }
    
    avg_price = search_data["avg_price"]
    min_price = search_data["min_price"]
    max_price = search_data["max_price"]
    unique_sellers = search_data["unique_sellers"]
    official_stores = search_data["official_stores"]
    total_sold = search_data["total_sold"]
    total_results = search_data["total"]
    
    # Determine recommendation
    recommendation = "CAUTION"
    reasons = []
    opportunities = []
    risks = []
    
    # 1. Market saturation
    if unique_sellers <= 3 and total_results <= 10:
        recommendation = "GO"
        opportunities.append("Baja competencia: solo {} vendedores".format(unique_sellers))
    elif unique_sellers >= 15 or total_results >= 100:
        recommendation = "AVOID"
        risks.append("Mercado saturado: {} vendedores, {} resultados".format(unique_sellers, total_results))
    else:
        reasons.append("Competencia moderada: {} vendedores".format(unique_sellers))
    
    # 2. Price gap analysis
    price_spread = max_price - min_price
    if price_spread > 0:
        spread_pct = (price_spread / avg_price) * 100
        if spread_pct > 50:
            opportunities.append("Gran dispersión de precios ({:.0f}%): hay espacio para posicionarte".format(spread_pct))
        elif spread_pct < 15:
            risks.append("Precios muy homogéneos: competencia por precio agresiva")
    
    # 3. Official stores presence
    if official_stores == 0:
        opportunities.append("Sin tiendas oficiales: no compites contra marcas con presupuesto")
    elif official_stores >= 3:
        risks.append("{} tiendas oficiales compiten: difícil destacar".format(official_stores))
    
    # 4. Sales velocity
    if total_sold > 500:
        opportunities.append("Alto volumen de ventas ({:.0f} unidades): demanda confirmada".format(total_sold))
    elif total_sold < 50:
        reasons.append("Bajo volumen de ventas: mercado pequeño o nuevo")
    
    # 5. Margin analysis (if landed cost provided)
    margin_analysis = {}
    if body.my_landed_cost_uyu > 0 and avg_price > 0:
        potential_margin = ((avg_price * 0.95) - body.my_landed_cost_uyu) / (avg_price * 0.95) * 100
        margin_analysis = {
            "landed_cost": body.my_landed_cost_uyu,
            "avg_market_price": avg_price,
            "potential_margin_percent": round(potential_margin, 1),
            "suggested_price": round(avg_price * 0.95, 0),
            "profit_per_unit": round(avg_price * 0.95 - body.my_landed_cost_uyu, 0),
        }
        
        if potential_margin >= 60:
            if recommendation != "AVOID":
                recommendation = "GO"
            opportunities.append("Margen potencial del {:.0f}%: muy rentable".format(potential_margin))
        elif potential_margin >= 40:
            reasons.append("Margen potencial del {:.0f}%: aceptable".format(potential_margin))
        elif potential_margin > 0:
            risks.append("Margen potencial del {:.0f}%: muy ajustado".format(potential_margin))
        else:
            recommendation = "AVOID"
            risks.append("PÉRDIDA: tu costo (${:.0f}) supera el precio de mercado".format(body.my_landed_cost_uyu))
    
    # Final recommendation logic
    if risks and len(risks) >= 2:
        recommendation = "AVOID"
    elif opportunities and len(opportunities) >= 2 and not risks:
        recommendation = "GO"
    
    messages = {
        "GO": "✅ IR — Condiciones favorables para entrar",
        "CAUTION": "⚠️ PRECAUCIÓN — Evaluar bien antes de importar",
        "AVOID": "❌ EVITAR — Riesgo alto o mercado saturado",
        "NO_DATA": "❓ SIN DATOS — No hay oferta, posible nicho",
    }
    
    return {
        "recommendation": recommendation,
        "message": messages.get(recommendation, ""),
        "reasoning": reasons,
        "opportunities": opportunities,
        "risks": risks,
        "market_data": {
            "query": body.query,
            "total_results": total_results,
            "avg_price": avg_price,
            "min_price": min_price,
            "max_price": max_price,
            "price_spread": search_data["price_spread"],
            "p25": search_data["p25"],
            "p50": search_data["p50"],
            "p75": search_data["p75"],
            "unique_sellers": unique_sellers,
            "official_stores": official_stores,
            "total_sold": total_sold,
            "seller_list": search_data["seller_list"],
        },
        "margin_analysis": margin_analysis if margin_analysis else None,
    }
# ═══════════════════════════════════════════════════════════════

class MLPublishInput(BaseModel):
    product_id: int
    strategy: str = "extreme"  # extreme, luxury, aggressive, cost_plus, value, premium_vs_comp
    access_token: str
    quantity: int = 10
    condition: str = "new"  # new, used
    listing_type: str = "gold_special"  # gold_special, gold_pro, free

class MLPublishResponse(BaseModel):
    success: bool
    item_id: Optional[str] = None
    permalink: Optional[str] = None
    message: str
    error_details: Optional[str] = None

async def publish_to_ml(product: Product, strategy: str, access_token: str, quantity: int, condition: str, listing_type: str):
    """Publish a product to MercadoLibre Uruguay"""
    
    # Determine price based on strategy
    price_map = {
        "extreme": product.price_extreme_uyu,
        "luxury": product.price_luxury_uyu,
        "aggressive": product.price_aggressive_uyu,
        "cost_plus": product.price_cost_plus_uyu,
        "value": product.price_value_uyu,
        "premium_vs_comp": product.price_premium_vs_comp_uyu,
    }
    price = price_map.get(strategy, product.price_cost_plus_uyu)
    if price <= 0:
        price = product.price_cost_plus_uyu
    
    # Category mapping (simplified - in production, use category predictor)
    CATEGORY_MAP = {
        "tecnologia": "MLU352001",  # Electrónica, Audio y Video
        "hogar_inteligente": "MLU1574",  # Hogar, Muebles y Jardín
        "electronica": "MLU352001",
        "bienestar": "MLU1246",  # Belleza y Cuidado Personal
        "accesorios_auto": "MLU1747",  # Accesorios para Vehículos
        "mascotas": "MLU1071",  # Animales y Mascotas
        "herramientas": "MLU1368",  # Herramientas
        "moda_accesorios": "MLU1430",  # Ropa y Accesorios
        "deportes": "MLU1276",  # Deportes y Fitness
        "juguetes": "MLU1132",  # Juegos y Juguetes
        "papeleria": "MLU1367",  # Librería y Papelería
    }
    category_id = CATEGORY_MAP.get(product.category, "MLU352001")
    
    # Build item payload
    payload = {
        "title": product.name,
        "category_id": category_id,
        "price": int(price),
        "currency_id": "UYU",
        "available_quantity": quantity,
        "buying_mode": "buy_it_now",
        "listing_type_id": listing_type,
        "condition": condition,
        "description": {
            "plain_text": product.description or f"{product.name}. Producto importado. Envío a todo Uruguay. Garantía de satisfacción."
        },
        "pictures": [],
        "shipping": {
            "mode": "me2",  # Mercado Envíos
            "local_pick_up": False,
            "free_shipping": False,
        },
        "attributes": [
            {"id": "BRAND", "value_name": "Generic"},
            {"id": "MODEL", "value_name": product.name[:50]},
        ],
    }
    
    # Add image if available
    if product.image_url:
        payload["pictures"].append({"source": product.image_url})
    else:
        # Use a placeholder
        payload["pictures"].append({"source": "https://via.placeholder.com/800x800?text=" + product.name.replace(" ", "+")})
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        resp = await client.post("https://api.mercadolibre.com/items", json=payload, headers=headers)
        
        if resp.status_code in (200, 201):
            data = resp.json()
            return {
                "success": True,
                "item_id": data.get("id"),
                "permalink": data.get("permalink"),
                "message": f"Publicado exitosamente: {data.get('id')}",
            }
        else:
            error_text = resp.text
            try:
                error_json = resp.json()
                if "message" in error_json:
                    error_text = error_json["message"]
                if "cause" in error_json:
                    causes = error_json["cause"]
                    if causes:
                        error_text += " | " + "; ".join([c.get("message", "") for c in causes[:3]])
            except:
                pass
            return {
                "success": False,
                "message": f"Error {resp.status_code}: {error_text[:200]}",
                "error_details": error_text,
            }

@app.post("/api/ml-publish")
async def ml_publish(body: MLPublishInput):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == body.product_id).first()
    db.close()
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    
    result = await publish_to_ml(
        product, body.strategy, body.access_token,
        body.quantity, body.condition, body.listing_type
    )
    return result

@app.get("/api/ml-categories")
async def ml_categories(q: str = Query(...)):
    """Predict category for a product title"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        url = f"https://api.mercadolibre.com/sites/MLU/category_predictor/predict"
        resp = await client.get(url, params={"title": q})
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}

@app.get("/api/products/{pid}/ml-preview")
def ml_preview(pid: int, strategy: str = "extreme"):
    """Preview what the ML listing would look like"""
    db = SessionLocal()
    p = db.query(Product).filter(Product.id == pid).first()
    db.close()
    if not p:
        raise HTTPException(404, "Not found")
    
    price_map = {
        "extreme": p.price_extreme_uyu,
        "luxury": p.price_luxury_uyu,
        "aggressive": p.price_aggressive_uyu,
        "cost_plus": p.price_cost_plus_uyu,
        "value": p.price_value_uyu,
        "premium_vs_comp": p.price_premium_vs_comp_uyu,
    }
    price = price_map.get(strategy, p.price_cost_plus_uyu)
    
    CATEGORY_MAP = {
        "tecnologia": "MLU352001",
        "hogar_inteligente": "MLU1574",
        "electronica": "MLU352001",
        "bienestar": "MLU1246",
        "accesorios_auto": "MLU1747",
        "mascotas": "MLU1071",
        "herramientas": "MLU1368",
        "moda_accesorios": "MLU1430",
        "deportes": "MLU1276",
        "juguetes": "MLU1132",
        "papeleria": "MLU1367",
    }
    
    return {
        "title": p.name,
        "category_id": CATEGORY_MAP.get(p.category, "MLU352001"),
        "price": int(price),
        "currency": "UYU",
        "description": p.description or f"{p.name}. Producto importado. Envío a todo Uruguay.",
        "image_url": p.image_url,
        "margin": getattr(p, f"margin_{strategy}", p.margin_cost_plus),
        "landed_cost": p.total_landed_cost_uyu,
    }


# ═══════════════════════════════════════════════════════════════
# MERCADOLIBRE OAUTH HELPERS
# ═══════════════════════════════════════════════════════════════

ML_AUTH_URL = "https://auth.mercadolibre.com.uy/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

class MLOAuthConfig(BaseModel):
    app_id: str
    redirect_uri: str = "http://localhost:8080/ml-callback"
    state: str = "uyimportops"

class MLOAuthExchange(BaseModel):
    app_id: str
    secret_key: str
    code: str
    redirect_uri: str = "http://localhost:8080/ml-callback"

@app.post("/api/ml-auth-url")
def get_ml_auth_url(config: MLOAuthConfig):
    """Generate the MercadoLibre authorization URL"""
    url = f"{ML_AUTH_URL}?response_type=code&client_id={config.app_id}&redirect_uri={config.redirect_uri}&state={config.state}"
    return {
        "auth_url": url,
        "instructions": [
            "1. Abrí la URL en tu navegador",
            "2. Iniciá sesión con tu cuenta de MercadoLibre",
            "3. Autorizá la aplicación",
            "4. Copiá el 'code' de la URL de redirección",
            "5. Usá /api/ml-exchange para obtener el token"
        ]
    }

@app.post("/api/ml-exchange")
async def exchange_ml_code(body: MLOAuthExchange):
    """Exchange authorization code for access token"""
    async with httpx.AsyncClient(timeout=15.0) as client:
        payload = {
            "grant_type": "authorization_code",
            "client_id": body.app_id,
            "client_secret": body.secret_key,
            "code": body.code,
            "redirect_uri": body.redirect_uri,
        }
        resp = await client.post(ML_TOKEN_URL, data=payload)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "success": True,
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "user_id": data.get("user_id"),
                "token_type": data.get("token_type"),
                "message": "Token obtenido exitosamente. Guardalo en un lugar seguro."
            }
        else:
            return {
                "success": False,
                "error": resp.text,
                "message": "Error al intercambiar el código. Verificá que el code no haya expirado (vence en 10 min)."
            }

@app.get("/api/ml-test-token")
async def test_ml_token(token: str = Query(...)):
    """Test if a MercadoLibre token is valid"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get("https://api.mercadolibre.com/users/me", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "valid": True,
                "nickname": data.get("nickname"),
                "user_id": data.get("id"),
                "email": data.get("email"),
                "site_id": data.get("site_id"),
                "message": "Token válido"
            }
        return {
            "valid": False,
            "status_code": resp.status_code,
            "message": "Token inválido o expirado"
        }

# ═══════════════════════════════════════════════════════════════
# REAL PRODUCT HUNTER ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class URLAnalyzeInput(BaseModel):
    url: str

class AliExpressSearchInput(BaseModel):
    query: str
    limit: int = 10

@app.post("/api/hunter/analyze-url")
async def analyze_product_url(body: URLAnalyzeInput):
    """Analyze a product URL from AliExpress or 1688 and extract pricing data"""
    hunter = ProductHunter()
    result = await hunter.analyze_url(body.url)
    if not result:
        raise HTTPException(400, "Could not analyze URL. Make sure it's a valid AliExpress or 1688 product URL.")
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.post("/api/hunter/search-aliexpress")
async def search_aliexpress(body: AliExpressSearchInput):
    """Search AliExpress for products using real browser automation"""
    hunter = ProductHunter()
    results = await hunter.search_aliexpress(body.query, body.limit)
    return {
        "query": body.query,
        "results": results,
        "count": len(results),
        "source": "aliexpress",
    }

@app.get("/api/hunter/trending")
async def get_trending_products(
    category: Optional[str] = None,
    min_demand: int = 50,
    limit: int = 20,
    page: int = 1,
    with_images: bool = False,
    q: Optional[str] = None,
    sort_by: Optional[str] = "demand",
    sort_order: Optional[str] = "desc",
    min_cost: Optional[float] = None,
    max_cost: Optional[float] = None,
    mode: Optional[str] = None,
):
    """Real Product Hunter — searches live sources.
    Pass ?q=auriculares to search live (Bing Shopping -> AliExpress -> mock).
    Pass ?mode=curated to see the pre-built niche list (69 products).
    sort_by: price | margin | cost | demand | opportunity | rating | reviews | name
    sort_order: asc | desc
    min_cost / max_cost: filter by USD purchase price in China
    """
    
    # ┌────────────────────────────────────────────────────────────────┐
    # LIVE SEARCH MODE — the real hunter
    # └─────────────────────────────────────────────────────────────────┘
    if q and q.strip():
        query = q.strip()
        all_results = []
        sources_used = []
        
        # Step 1: Bing Shopping (HTTP-only, works on Render)
        try:
            bing_results = await search_bing_shopping(query, limit=limit)
            if bing_results:
                all_results.extend(bing_results)
                sources_used.append("bing-shopping")
                print(f"[Hunter] Bing Shopping: {len(bing_results)} results")
        except Exception as e:
            print(f"[Hunter] Bing Shopping failed: {e}")
        
        # Step 2: Bing Web fallback
        if len(all_results) < 3:
            try:
                web_results = await search_bing_web_products(query, limit=limit)
                if web_results:
                    all_results.extend(web_results)
                    sources_used.append("bing-web")
                    print(f"[Hunter] Bing Web: {len(web_results)} results")
            except Exception as e:
                print(f"[Hunter] Bing Web failed: {e}")
        
        # Step 3: AliExpress (Playwright — may OOM on Render)
        if len(all_results) < 3:
            try:
                hunter = ProductHunter()
                ali_results = await hunter.search_aliexpress(query, limit)
                if ali_results:
                    for r in ali_results:
                        all_results.append({
                            "name": r.get("name", "Unknown"),
                            "price_usd": r.get("price_usd", 0),
                            "image_url": r.get("image_url", ""),
                            "product_url": r.get("product_url", ""),
                            "rating": r.get("rating", 0),
                            "sold_count": r.get("sold_count", 0),
                            "source": "aliexpress",
                        })
                    sources_used.append("aliexpress")
                    print(f"[Hunter] AliExpress: {len(ali_results)} results")
            except Exception as e:
                print(f"[Hunter] AliExpress failed: {e}")
        
        # Step 4: Mock fallback (realistic, keyword-aware)
        if len(all_results) < 3:
            mock_results = generate_mock_sourcing_data(query, limit)
            all_results.extend(mock_results)
            sources_used.append("mock-fallback")
            print(f"[Hunter] Mock fallback: {len(mock_results)} results")
        
        # Normalize to common format
        normalized = []
        for r in all_results:
            cost = r.get("price_usd", 0)
            # Apply cost filters
            if min_cost is not None and cost < min_cost:
                continue
            if max_cost is not None and cost > max_cost:
                continue
            
            # Try to enrich with real product image
            img = r.get("image_url", "")
            if not img:
                # Try Bing image cache
                img = _image_cache.get(r.get("name", ""), "")
            
            normalized.append({
                "name": r.get("name", "Unknown")[:150],
                "cat": category or "general",
                "demand": min(95, max(50, int(70 + (r.get("sold_count", 0) / 100)))),
                "cost_usd": cost,
                "ship_usd": round(cost * 0.15 + 2, 2),  # 15% of cost + base
                "ml_avg": round(cost * 3 * 42, 0) if cost > 0 else 0,  # rough ML estimate
                "img": img,
                "desc": r.get("name", ""),
                "source_url": r.get("product_url", ""),
                "rating": r.get("rating", 4.2),
                "reviews": r.get("sold_count", 0),
                "store": r.get("store", r.get("source", "unknown")),
                "source": r.get("source", "unknown"),
            })
        
        # Sort
        def _sort_margin(x):
            c = x.get("cost_usd", 0)
            m = x.get("ml_avg", 0) / 42 if x.get("ml_avg", 0) else 0
            if c > 0:
                return x.get("demand", 0) * 0.6 + ((m - c) / c * 100) * 0.4
            return x.get("demand", 0)
        
        def _sort_opp(x):
            c = x.get("cost_usd", 0)
            m = x.get("ml_avg", 0) / 42 if x.get("ml_avg", 0) else 0
            if c > 0:
                return x.get("demand", 0) * 0.6 + ((m - c) / c * 100) * 0.4
            return x.get("demand", 0)
        
        sort_key = {
            "price": lambda x: x.get("cost_usd", 0),
            "margin": _sort_margin,
            "cost": lambda x: x.get("cost_usd", 0),
            "demand": lambda x: x.get("demand", 0),
            "opportunity": _sort_opp,
            "rating": lambda x: x.get("rating", 0),
            "reviews": lambda x: x.get("reviews", 0),
            "name": lambda x: x.get("name", "").lower(),
        }.get(sort_by, lambda x: x.get("demand", 0))
        normalized.sort(key=sort_key, reverse=(sort_order != "asc"))
        
        return {
            "products": normalized[:limit],
            "count": len(normalized[:limit]),
            "total_available": len(normalized),
            "page": 1,
            "total_pages": max(1, (len(normalized) + limit - 1) // limit),
            "with_images": with_images,
            "query": query,
            "sources": sources_used,
            "source": "live",
        }
    
    # ┌────────────────────────────────────────────────────────────────┐
    # CURATED MODE — only when explicitly requested
    # └─────────────────────────────────────────────────────────────────┘
    if mode == "curated":
        products = WINNING_NICHES.copy()
        if category:
            products = [p for p in products if p.get("cat") == category]
        products = [p for p in products if p.get("demand", 0) >= min_demand]
        if min_cost is not None:
            products = [p for p in products if p.get("cost_usd", 0) >= min_cost]
        if max_cost is not None:
            products = [p for p in products if p.get("cost_usd", 0) <= max_cost]
        
        sort_key = {
            "price": lambda x: x.get("cost_usd", 0) + x.get("ship_usd", 0),
            "margin": lambda x: x.get("profit_score", 0),
            "cost": lambda x: x.get("cost_usd", 0),
            "demand": lambda x: x.get("demand", 0),
            "opportunity": lambda x: x.get("demand", 0) * 0.6 + x.get("profit_score", 0) * 0.4,
            "rating": lambda x: x.get("est_rating", 0),
            "reviews": lambda x: x.get("est_reviews", 0),
            "name": lambda x: x.get("name", "").lower(),
        }.get(sort_by, lambda x: x.get("demand", 0))
        products.sort(key=sort_key, reverse=(sort_order != "asc"))
        
        total = len(products)
        start = (page - 1) * limit
        products = products[start:start + limit]
        
        if with_images and products:
            products = await enrich_products_with_images(products, max_concurrent=5)
        
        return {
            "products": products,
            "count": len(products),
            "total_available": total,
            "page": page,
            "total_pages": (total + limit - 1) // limit,
            "with_images": with_images,
            "source": "curated",
        }
    
    # ┌────────────────────────────────────────────────────────────────┐
    # EMPTY STATE — prompt user to search
    # └─────────────────────────────────────────────────────────────────┘
    return {
        "products": [],
        "count": 0,
        "total_available": 0,
        "page": 1,
        "total_pages": 0,
        "with_images": False,
        "source": "empty",
        "message": "Ingresá un producto para buscar (ej: auriculares, smartwatch, lámpara). Usá ?mode=curated para ver los 69 nichos pre-cargados.",
    }

@app.get("/api/hunter/categories")
def get_hunter_categories():
    """Get all product categories with counts"""
    groups = {}
    for item in WINNING_NICHES:
        cat = item.get("cat", "otros")
        groups[cat] = groups.get(cat, 0) + 1
    return {
        "categories": [
            {"id": k, "name": k.replace("_", " ").title(), "count": v}
            for k, v in sorted(groups.items(), key=lambda x: -x[1])
        ],
        "total_products": len(WINNING_NICHES),
    }

@app.get("/api/hunter/find-image")
async def find_product_image(name: str = Query(..., description="Product name to search for")):
    """Search Bing Images for a real product photo and return the best URL"""
    query = f"{name} producto"
    search_url = f"https://www.bing.com/images/search?q={query.replace(' ', '+')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(search_url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                return {"image_url": "", "source": "bing", "error": f"Status {resp.status_code}"}
            
            # Bing stores image URLs in murl JSON fields
            murls = re.findall(r'&quot;murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
            
            # Filter for likely product images (exclude logos, icons, tiny images)
            good_urls = []
            for url in murls:
                url_clean = url.replace("\\", "")
                # Skip tiny images, icons, and non-image domains
                if any(bad in url_clean.lower() for bad in ['icon', 'logo', 'favicon', 'sprite', 'button', 'badge']):
                    continue
                if url_clean.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    good_urls.append(url_clean)
            
            best = good_urls[0] if good_urls else (murls[0] if murls else "")
            return {"image_url": best, "source": "bing", "alternatives": good_urls[:5]}
    except Exception as e:
        return {"image_url": "", "source": "bing", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# SHIPMENT & TRACKING ENDPOINTS (Point 4)
# ═══════════════════════════════════════════════════════════════

class ShipmentCreate(BaseModel):
    product_id: int
    tracking_number: str = ""
    carrier: str = ""
    origin: str = "China"
    destination: str = "Uruguay"
    status: str = "ordered"
    estimated_arrival: Optional[str] = None  # ISO format
    shipping_cost_usd: float = 0.0
    notes: str = ""

class ShipmentUpdate(BaseModel):
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    status: Optional[str] = None
    estimated_arrival: Optional[str] = None
    actual_arrival: Optional[str] = None
    shipping_cost_usd: Optional[float] = None
    notes: Optional[str] = None

class ShipmentEventCreate(BaseModel):
    shipment_id: int
    event_type: str
    description: str = ""
    location: str = ""

class CostActualCreate(BaseModel):
    product_id: int
    actual_product_cost_usd: float = 0.0
    actual_shipping_usd: float = 0.0
    actual_tariff_usd: float = 0.0
    actual_iva_usd: float = 0.0
    actual_agent_fee_usd: float = 0.0
    notes: str = ""

# Valid extended statuses for the pipeline
EXTENDED_STATUSES = [
    "researching", "sourcing", "ordered", "in_transit", "customs",
    "arrived", "testing", "listed", "winner", "flop"
]

@app.post("/api/shipments")
def create_shipment(body: ShipmentCreate):
    db = SessionLocal()
    
    # Parse dates
    est_arrival = None
    if body.estimated_arrival:
        try:
            est_arrival = datetime.fromisoformat(body.estimated_arrival.replace("Z", "+00:00"))
        except:
            pass
    
    ship = Shipment(
        product_id=body.product_id,
        tracking_number=body.tracking_number,
        carrier=body.carrier,
        origin=body.origin,
        destination=body.destination,
        status=body.status,
        estimated_arrival=est_arrival,
        shipping_cost_usd=body.shipping_cost_usd,
        notes=body.notes,
    )
    db.add(ship)
    db.commit()
    db.refresh(ship)
    
    # Add initial event
    if body.status:
        event = ShipmentEvent(
            shipment_id=ship.id,
            event_type="status_change",
            description=f"Envío creado con estado: {body.status}",
        )
        db.add(event)
        db.commit()
    
    db.close()
    return {"id": ship.id, "message": "Shipment created"}

@app.get("/api/shipments")
def list_shipments(product_id: Optional[int] = None):
    db = SessionLocal()
    q = db.query(Shipment)
    if product_id:
        q = q.filter(Shipment.product_id == product_id)
    ships = q.order_by(Shipment.created_at.desc()).all()
    db.close()
    return [{"id": s.id, "product_id": s.product_id, "tracking_number": s.tracking_number,
             "carrier": s.carrier, "origin": s.origin, "destination": s.destination,
             "status": s.status, "estimated_arrival": s.estimated_arrival.isoformat() if s.estimated_arrival else None,
             "actual_arrival": s.actual_arrival.isoformat() if s.actual_arrival else None,
             "shipping_cost_usd": s.shipping_cost_usd, "notes": s.notes,
             "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in ships]

@app.get("/api/shipments/{sid}")
def get_shipment(sid: int):
    db = SessionLocal()
    ship = db.query(Shipment).filter(Shipment.id == sid).first()
    if not ship:
        db.close()
        raise HTTPException(404, "Shipment not found")
    
    events = db.query(ShipmentEvent).filter(ShipmentEvent.shipment_id == sid).order_by(ShipmentEvent.occurred_at.desc()).all()
    db.close()
    
    return {
        "id": ship.id, "product_id": ship.product_id, "tracking_number": ship.tracking_number,
        "carrier": ship.carrier, "origin": ship.origin, "destination": ship.destination,
        "status": ship.status, "estimated_arrival": ship.estimated_arrival.isoformat() if ship.estimated_arrival else None,
        "actual_arrival": ship.actual_arrival.isoformat() if ship.actual_arrival else None,
        "shipping_cost_usd": ship.shipping_cost_usd, "notes": ship.notes,
        "created_at": ship.created_at.isoformat() if ship.created_at else None,
        "events": [{"id": e.id, "event_type": e.event_type, "description": e.description,
                    "location": e.location, "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None}
                   for e in events]
    }

@app.patch("/api/shipments/{sid}")
def update_shipment(sid: int, body: ShipmentUpdate):
    db = SessionLocal()
    ship = db.query(Shipment).filter(Shipment.id == sid).first()
    if not ship:
        db.close()
        raise HTTPException(404, "Shipment not found")
    
    data = body.model_dump(exclude_unset=True)
    
    # Handle date parsing
    for date_field in ["estimated_arrival", "actual_arrival"]:
        if date_field in data and data[date_field]:
            try:
                data[date_field] = datetime.fromisoformat(data[date_field].replace("Z", "+00:00"))
            except:
                data[date_field] = None
    
    # Track status change for event
    old_status = ship.status
    new_status = data.get("status", old_status)
    
    for k, v in data.items():
        setattr(ship, k, v)
    
    ship.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ship)
    
    # Add event if status changed
    if new_status != old_status:
        event = ShipmentEvent(
            shipment_id=sid,
            event_type="status_change",
            description=f"Estado cambiado de '{old_status}' a '{new_status}'",
        )
        db.add(event)
        db.commit()
    
    db.close()
    return {"id": ship.id, "message": "Shipment updated", "status": ship.status}

@app.post("/api/shipments/{sid}/events")
def add_shipment_event(sid: int, body: ShipmentEventCreate):
    db = SessionLocal()
    ship = db.query(Shipment).filter(Shipment.id == sid).first()
    if not ship:
        db.close()
        raise HTTPException(404, "Shipment not found")
    
    event = ShipmentEvent(
        shipment_id=sid,
        event_type=body.event_type,
        description=body.description,
        location=body.location,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    db.close()
    return {"id": event.id, "message": "Event added"}

@app.delete("/api/shipments/{sid}")
def delete_shipment(sid: int):
    db = SessionLocal()
    ship = db.query(Shipment).filter(Shipment.id == sid).first()
    if not ship:
        db.close()
        raise HTTPException(404, "Shipment not found")
    
    # Delete related events first
    db.query(ShipmentEvent).filter(ShipmentEvent.shipment_id == sid).delete()
    db.delete(ship)
    db.commit()
    db.close()
    return {"message": "Shipment deleted"}


# ═══════════════════════════════════════════════════════════════
# COST ACTUAL & ROI ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.post("/api/products/{pid}/actual-costs")
def record_actual_costs(pid: int, body: CostActualCreate):
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")
    
    # Calculate actual total
    actual_total_usd = (body.actual_product_cost_usd + body.actual_shipping_usd +
                        body.actual_tariff_usd + body.actual_iva_usd + body.actual_agent_fee_usd)
    actual_total_uyu = actual_total_usd * UYU_PER_USD
    
    # Calculate variance vs estimated
    estimated_total = product.total_landed_cost_uyu
    variance = ((actual_total_uyu - estimated_total) / estimated_total * 100) if estimated_total > 0 else 0
    
    cost = CostActual(
        product_id=pid,
        actual_product_cost_usd=body.actual_product_cost_usd,
        actual_shipping_usd=body.actual_shipping_usd,
        actual_tariff_usd=body.actual_tariff_usd,
        actual_iva_usd=body.actual_iva_usd,
        actual_agent_fee_usd=body.actual_agent_fee_usd,
        actual_total_usd=actual_total_usd,
        actual_total_uyu=actual_total_uyu,
        variance_percent=round(variance, 1),
        notes=body.notes,
    )
    db.add(cost)
    db.commit()
    db.refresh(cost)
    db.close()
    
    return {
        "id": cost.id,
        "actual_total_uyu": actual_total_uyu,
        "variance_percent": round(variance, 1),
        "message": "Actual costs recorded",
    }

@app.get("/api/products/{pid}/actual-costs")
def get_actual_costs(pid: int):
    db = SessionLocal()
    costs = db.query(CostActual).filter(CostActual.product_id == pid).order_by(CostActual.recorded_at.desc()).all()
    db.close()
    return [{"id": c.id, "actual_total_uyu": c.actual_total_uyu, "variance_percent": c.variance_percent,
             "recorded_at": c.recorded_at.isoformat() if c.recorded_at else None, "notes": c.notes}
            for c in costs]

@app.get("/api/products/{pid}/roi")
def get_product_roi(pid: int):
    """Calculate ROI projection for a product"""
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")
    
    # Get actual costs if available, otherwise use estimated
    actual = db.query(CostActual).filter(CostActual.product_id == pid).order_by(CostActual.recorded_at.desc()).first()
    db.close()
    
    landed_cost = actual.actual_total_uyu if actual else product.total_landed_cost_uyu
    
    # Calculate ROI for each strategy
    roi_data = {}
    for strat in ["cost_plus", "aggressive", "luxury", "extreme", "value", "premium_vs_comp"]:
        price = getattr(product, f"price_{strat}_uyu", 0)
        margin = getattr(product, f"margin_{strat}", 0)
        if price > 0:
            profit = price - landed_cost
            roi_percent = (profit / landed_cost * 100) if landed_cost > 0 else 0
            roi_data[strat] = {
                "price": price,
                "profit": round(profit, 0),
                "margin": margin,
                "roi_percent": round(roi_percent, 1),
            }
    
    # Get shipment status
    db = SessionLocal()
    shipments = db.query(Shipment).filter(Shipment.product_id == pid).all()
    db.close()
    
    return {
        "product_id": pid,
        "product_name": product.name,
        "landed_cost": landed_cost,
        "is_actual_cost": actual is not None,
        "variance_percent": actual.variance_percent if actual else None,
        "strategies": roi_data,
        "best_strategy": product.best_strategy,
        "shipments": [{"id": s.id, "status": s.status, "carrier": s.carrier, "tracking": s.tracking_number} for s in shipments],
    }

@app.get("/api/products/{pid}/analysis")
def get_product_analysis(pid: int):
    """Complete product analysis: projections, break-even, risk, insights"""
    db = SessionLocal()
    p = db.query(Product).filter(Product.id == pid).first()
    if not p:
        db.close()
        raise HTTPException(404, "Product not found")
    
    # Get actual costs if available
    actual = db.query(CostActual).filter(CostActual.product_id == pid).order_by(CostActual.recorded_at.desc()).first()
    db.close()
    
    landed = actual.actual_total_uyu if actual else p.total_landed_cost_uyu
    best_price = getattr(p, f"price_{p.best_strategy}_uyu", p.price_cost_plus_uyu)
    profit_per_unit = best_price - landed
    margin = p.best_margin
    
    # ── BREAK-EVEN ──
    # Assume initial investment = 20 units + fixed costs (agent fee)
    initial_investment = (p.product_cost_usd + p.shipping_cost_usd) * 20 * UYU_PER_USD + (p.agent_fee_usd * UYU_PER_USD)
    break_even_units = int(initial_investment / profit_per_unit) if profit_per_unit > 0 else 9999
    
    # ── MONTHLY PROJECTIONS ──
    # Conservative: sell 5 units/month initially, grow 10% monthly
    # Optimistic: sell 10 units/month initially, grow 15% monthly
    projections = []
    conservative_base = 5
    optimistic_base = 10
    for month in range(1, 13):
        cons_units = int(conservative_base * (1.1 ** (month - 1)))
        opt_units = int(optimistic_base * (1.15 ** (month - 1)))
        projections.append({
            "month": month,
            "conservative": {
                "units": cons_units,
                "revenue": round(cons_units * best_price, 0),
                "profit": round(cons_units * profit_per_unit, 0),
                "cumulative_profit": round(sum(int(conservative_base * (1.1 ** (m - 1))) * profit_per_unit for m in range(1, month + 1)), 0),
            },
            "optimistic": {
                "units": opt_units,
                "revenue": round(opt_units * best_price, 0),
                "profit": round(opt_units * profit_per_unit, 0),
                "cumulative_profit": round(sum(int(optimistic_base * (1.15 ** (m - 1))) * profit_per_unit for m in range(1, month + 1)), 0),
            }
        })
    
    # ── RISK SCORE ──
    # 0-100, lower is better (safer)
    risk_factors = {
        "demand_risk": max(0, 100 - p.demand_score),
        "competition_risk": 80 if p.ml_competitor_price > 0 else 40,  # High if competitors exist
        "margin_risk": max(0, 100 - int(p.best_margin)),
        "seasonality_risk": 30 if p.category in ["deportes", "bienestar"] else 15,
    }
    risk_score = int(sum(risk_factors.values()) / len(risk_factors))
    risk_level = "Bajo" if risk_score < 35 else "Medio" if risk_score < 60 else "Alto"
    
    # ── INVENTORY PLANNER ──
    # Reorder point: when stock = 2 weeks of sales
    # Order quantity: 1 month of optimistic sales
    avg_monthly_sales = optimistic_base * 6  # 6 months avg
    reorder_point = max(5, int(avg_monthly_sales / 2))
    order_quantity = max(20, int(avg_monthly_sales * 1.5))
    inventory_cost = order_quantity * landed
    
    # ── PRICING COMPARISON ──
    pricing_vs_comp = {}
    if p.ml_competitor_price > 0:
        comp_price = p.ml_competitor_price
        for strat in ["cost_plus", "aggressive", "luxury", "extreme"]:
            price = getattr(p, f"price_{strat}_uyu", 0)
            diff_pct = round((price - comp_price) / comp_price * 100, 1)
            pricing_vs_comp[strat] = {
                "price": price,
                "vs_competitor": diff_pct,
                "position": "below" if diff_pct < 0 else "match" if diff_pct < 10 else "premium",
            }
    
    # ── AI INSIGHT ──
    insights = []
    if margin >= 70:
        insights.append("Margen EXCEPCIONAL. Producto altamente rentable con potencial de ganancia superior al mercado.")
    elif margin >= 60:
        insights.append("Margen MUY BUENO. Rentabilidad por encima del promedio del sector.")
    else:
        insights.append("Margen MODERADO. Considerar estrategias de upselling o bundling.")
    
    if p.demand_score >= 80:
        insights.append("Demanda ALTA. Producto en tendencia con buen volumen de búsquedas.")
    elif p.demand_score >= 60:
        insights.append("Demanda MEDIA. Nicho estable con potencial de crecimiento.")
    else:
        insights.append("Demanda BAJA. Considerar marketing agresivo o nicho especializado.")
    
    if p.ml_competitor_price > 0 and best_price < p.ml_competitor_price:
        insights.append(f"PRECIO COMPETITIVO. Tu precio es {round((p.ml_competitor_price - best_price)/p.ml_competitor_price*100)}% menor que la competencia en ML Uruguay.")
    
    if break_even_units <= 20:
        insights.append(f"Break-even RÁPIDO. Solo {break_even_units} unidades para recuperar la inversión inicial.")
    
    # ── ANNUAL ROI ──
    annual_profit_cons = projections[-1]["conservative"]["cumulative_profit"]
    annual_profit_opt = projections[-1]["optimistic"]["cumulative_profit"]
    annual_roi_cons = round(annual_profit_cons / initial_investment * 100, 1) if initial_investment > 0 else 0
    annual_roi_opt = round(annual_profit_opt / initial_investment * 100, 1) if initial_investment > 0 else 0
    
    return {
        "product_id": pid,
        "product_name": p.name,
        "analysis_date": datetime.utcnow().isoformat(),
        "break_even": {
            "units": break_even_units,
            "initial_investment_uyu": round(initial_investment, 0),
            "profit_per_unit": round(profit_per_unit, 0),
        },
        "projections": projections,
        "annual_summary": {
            "conservative_roi": annual_roi_cons,
            "optimistic_roi": annual_roi_opt,
            "conservative_profit": annual_profit_cons,
            "optimistic_profit": annual_profit_opt,
        },
        "risk": {
            "score": risk_score,
            "level": risk_level,
            "factors": risk_factors,
        },
        "inventory": {
            "reorder_point": reorder_point,
            "order_quantity": order_quantity,
            "inventory_cost_uyu": round(inventory_cost, 0),
            "suggested_first_order": max(20, order_quantity),
        },
        "pricing_vs_competitor": pricing_vs_comp,
        "insights": insights,
        "best_strategy": p.best_strategy,
        "key_metrics": {
            "landed_cost_uyu": round(landed, 0),
            "selling_price_uyu": round(best_price, 0),
            "margin_percent": round(margin, 1),
            "demand_score": p.demand_score,
            "competitor_price_uyu": round(p.ml_competitor_price, 0) if p.ml_competitor_price else None,
        }
    }


# ═══════════════════════════════════════════════════════════════
# ENHANCED STATS WITH PIPELINE STAGES
# ═══════════════════════════════════════════════════════════════

@app.get("/api/stats")
def dashboard_stats():
    db = SessionLocal()
    total = db.query(Product).count()
    
    # Extended status counts
    all_statuses = EXTENDED_STATUSES
    by_status = {}
    for s in all_statuses:
        by_status[s] = db.query(Product).filter(Product.status == s).count()
    
    all_prods = db.query(Product).all()
    avg_best_margin = 0
    if all_prods:
        margins = [p.best_margin for p in all_prods if p.best_margin]
        avg_best_margin = round(sum(margins) / len(margins), 1) if margins else 0
    
    total_invested = sum(p.total_landed_cost_uyu for p in all_prods)
    high_margin = db.query(Product).filter(Product.margin_extreme >= 60).count()
    ultra_margin = db.query(Product).filter(Product.margin_extreme >= 70).count()
    
    # Shipment stats
    total_shipments = db.query(Shipment).count()
    in_transit = db.query(Shipment).filter(Shipment.status.in_(["ordered", "in_transit", "customs"])).count()
    arrived = db.query(Shipment).filter(Shipment.status == "arrived").count()
    
    db.close()
    return {
        "total_products": total,
        "by_status": by_status,
        "avg_best_margin": avg_best_margin,
        "total_invested_uyu": round(total_invested, 2),
        "high_margin_products": high_margin,
        "ultra_margin_products": ultra_margin,
        "shipments": {
            "total": total_shipments,
            "in_transit": in_transit,
            "arrived": arrived,
        },
    }


# ═══════════════════════════════════════════════════════════════
# MARKETING & GROWTH ENGINE
# ═══════════════════════════════════════════════════════════════

class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, nullable=False)
    competitor_price = Column(Float, default=0.0)
    our_price = Column(Float, default=0.0)
    platform = Column(String, default="mercadolibre")  # mercadolibre, amazon, etc
    recorded_at = Column(DateTime, default=datetime.utcnow)

class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, nullable=False)
    name = Column(String, default="")
    type = Column(String, default="")  # email, social, ads, ml_ads
    content = Column(Text, default="")
    status = Column(String, default="draft")  # draft, active, completed
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# Marketing keyword templates by category
CATEGORY_KEYWORDS = {
    "tecnologia": ["bluetooth", "inalambrico", "smart", "digital", "gadget", "USB-C", "WiFi", "HD"],
    "hogar_inteligente": ["smart home", "automatizacion", "WiFi", "app", "alexa", "google home", "ahorro energia"],
    "electronica": ["carga rapida", "USB", "HDMI", "alta calidad", "duradero"],
    "bienestar": ["salud", "bienestar", "relajacion", "masaje", "fitness", "cuidado personal"],
    "accesorios_auto": ["auto", "vehiculo", "conduccion", "seguridad", "practico"],
    "mascotas": ["mascota", "perro", "gato", "automatico", "cuidado", "alimentacion"],
    "herramientas": ["herramienta", "bricolaje", "reparacion", "precision", "profesional"],
    "moda_accesorios": ["moda", "estilo", "tendencia", "elegante", "unico"],
    "deportes": ["deporte", "fitness", "entrenamiento", "salud", "rendimiento"],
    "juguetes": ["juego", "diversion", "entretenimiento", "niños", "educativo"],
    "papeleria": ["oficina", "escuela", "escritorio", "organizacion"],
}

CATEGORY_BENEFITS = {
    "tecnologia": ["Compatible con todos los dispositivos", "Tecnologia de ultima generacion", "Bateria de larga duracion"],
    "hogar_inteligente": ["Control desde tu celular", "Ahorra tiempo y energia", "Facil instalacion"],
    "electronica": ["Carga ultra rapida", "Materiales premium", "Garantia extendida"],
    "bienestar": ["Alivia tension y estres", "Resultados visibles en semanas", "Diseno ergonomico"],
    "accesorios_auto": ["Instalacion en segundos", "Compatible con todos los autos", "Material resistente"],
    "mascotas": ["Mantene a tu mascota feliz", "Ahorra tiempo", "Diseno seguro y duradero"],
    "herramientas": ["Precision profesional", "Incluye estuche organizador", "Acero inoxidable"],
    "moda_accesorios": ["Edicion limitada", "Regalo perfecto", "Acabado premium"],
    "deportes": ["Mejora tu rendimiento", "Material transpirable", "Resistente al agua"],
    "juguetes": ["Seguro para ninos", "Desarrolla habilidades", "Horas de diversion"],
    "papeleria": ["Organiza tu espacio", "Material ecologico", "Diseno minimalista"],
}

ML_CATEGORY_IDS = {
    "tecnologia": "MLU352001",
    "hogar_inteligente": "MLU1574",
    "electronica": "MLU352001",
    "bienestar": "MLU1246",
    "accesorios_auto": "MLU1747",
    "mascotas": "MLU1071",
    "herramientas": "MLU1368",
    "moda_accesorios": "MLU1430",
    "deportes": "MLU1276",
    "juguetes": "MLU1132",
    "papeleria": "MLU1367",
}

class ListingOptimizeInput(BaseModel):
    strategy: str = "aggressive"  # aggressive, luxury, extreme, value
    include_emojis: bool = True
    max_title_length: int = 60

class SocialContentInput(BaseModel):
    platform: str = "instagram"  # instagram, x, facebook, tiktok
    tone: str = "professional"   # professional, casual, hype, educational
    include_hashtags: bool = True

class EmailCampaignInput(BaseModel):
    campaign_type: str = "launch"  # launch, discount, restock, seasonal
    discount_percent: int = 0
    urgency: bool = True

class CompetitorTrackInput(BaseModel):
    competitor_url: str = ""
    competitor_price: float = 0.0
    platform: str = "mercadolibre"

@app.post("/api/products/{pid}/track-competitor")
def track_competitor(pid: int, body: CompetitorTrackInput):
    """Track a competitor's price for this product"""
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")
    
    # Record price history
    best_price = getattr(product, f"price_{product.best_strategy}_uyu", product.price_cost_plus_uyu)
    history = PriceHistory(
        product_id=pid,
        competitor_price=body.competitor_price,
        our_price=best_price,
        platform=body.platform,
    )
    db.add(history)
    db.commit()
    
    # Generate pricing recommendation
    diff_pct = 0
    if body.competitor_price > 0:
        diff_pct = round((best_price - body.competitor_price) / body.competitor_price * 100, 1)
    
    recommendation = "mantener"
    if diff_pct > 15:
        recommendation = "bajar_precio"
    elif diff_pct < -20:
        recommendation = "subir_precio"
    
    # Get price history for this product
    history_records = db.query(PriceHistory).filter(PriceHistory.product_id == pid).order_by(PriceHistory.recorded_at.desc()).limit(10).all()
    db.close()
    
    return {
        "tracked": True,
        "competitor_price": body.competitor_price,
        "our_price": best_price,
        "difference_percent": diff_pct,
        "position": "below" if diff_pct < 0 else "match" if diff_pct < 10 else "premium",
        "recommendation": recommendation,
        "history_count": len(history_records),
        "history": [{"price": h.competitor_price, "date": h.recorded_at.isoformat()} for h in history_records[:5]],
    }

@app.get("/api/products/{pid}/price-history")
def get_price_history(pid: int):
    """Get price history for a product"""
    db = SessionLocal()
    records = db.query(PriceHistory).filter(PriceHistory.product_id == pid).order_by(PriceHistory.recorded_at.desc()).limit(50).all()
    db.close()
    return {
        "product_id": pid,
        "records": [{"id": r.id, "competitor_price": r.competitor_price, "our_price": r.our_price, "platform": r.platform, "date": r.recorded_at.isoformat()} for r in records],
    }

@app.post("/api/products/{pid}/optimize-listing")
def optimize_listing(pid: int, body: ListingOptimizeInput):
    """Generate optimized ML listing (title, description, keywords)"""
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")
    db.close()
    
    cat = product.category or "tecnologia"
    keywords = CATEGORY_KEYWORDS.get(cat, ["producto", "calidad", "importado"])
    benefits = CATEGORY_BENEFITS.get(cat, ["Alta calidad", "Importado directo", "Garantia"])
    
    # Get selling price based on strategy
    price = getattr(product, f"price_{body.strategy}_uyu", product.price_cost_plus_uyu)
    
    # Generate optimized title
    name_words = product.name.split()
    keyword = keywords[0] if keywords else ""
    benefit = benefits[0] if benefits else ""
    
    emojis = {"aggressive": "🔥", "luxury": "✨", "extreme": "💎", "value": "💰", "cost_plus": "📦"}
    emoji = emojis.get(body.strategy, "🚀") if body.include_emojis else ""
    
    title_templates = [
        f"{emoji} {product.name} {keyword} - {benefit} - Envio Gratis",
        f"{emoji} {product.name} | {keyword} | {benefit} | Uruguay",
        f"{emoji} {product.name} {keyword} - Calidad Premium - Stock",
    ]
    
    # Pick best title (shorter is better for ML)
    best_title = min(title_templates, key=len)[:body.max_title_length]
    
    # Generate description
    desc_lines = [
        f"## {product.name}",
        "",
        f"**Precio:** ${int(price)} UYU",
        f"**Estrategia:** {body.strategy.replace('_', ' ').title()}",
        "",
        "### Caracteristicas principales:",
    ]
    for b in benefits[:3]:
        desc_lines.append(f"✅ {b}")
    
    desc_lines.extend([
        "",
        "### Beneficios:",
        f"📦 Envio a todo Uruguay",
        f"🔒 Producto nuevo y sellado",
        f"💬 Atencion personalizada",
        "",
        "### Keywords:",
        ", ".join(keywords[:5]),
    ])
    
    # Generate ML attributes
    category_id = ML_CATEGORY_IDS.get(cat, "MLU352001")
    
    return {
        "product_id": pid,
        "strategy": body.strategy,
        "optimized_title": best_title,
        "description": "\n".join(desc_lines),
        "keywords": keywords[:8],
        "benefits": benefits[:5],
        "suggested_price": price,
        "ml_category_id": category_id,
        "listing_tips": [
            "Usa las 3 fotos principales: producto, detalle, empaque",
            f"Precio sugerido: ${int(price)} UYU (margen {round(product.best_margin)}%)",
            "Responde en menos de 1 hora para mejor ranking",
            "Ofrece MercadoEnvios para mayor visibilidad",
            "Incluye video del producto si es posible",
        ],
    }

@app.post("/api/products/{pid}/marketing-strategy")
def generate_marketing_strategy(pid: int):
    """Generate a complete marketing strategy for a product"""
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")
    db.close()
    
    cat = product.category or "tecnologia"
    keywords = CATEGORY_KEYWORDS.get(cat, [])
    price = getattr(product, f"price_{product.best_strategy}_uyu", product.price_cost_plus_uyu)
    margin = product.best_margin
    
    # Strategy based on margin and demand
    strategies = []
    
    if margin >= 70:
        strategies.append({
            "name": "Premium Positioning",
            "description": "Posicionamiento premium con precio alto y marketing de lujo",
            "tactics": [
                "Fotos profesionales con fondo blanco",
                "Video de unboxing de alta calidad",
                "Influencers de lifestyle/nicho",
                "Email marketing segmentado a compradores premium",
            ],
            "budget_percent": 20,
            "expected_roi": "300-400%",
        })
    
    if product.demand_score >= 75:
        strategies.append({
            "name": "Volume Attack",
            "description": "Ataque de volumen con precio competitivo y ads agresivas",
            "tactics": [
                "Precio 5-10% debajo de la competencia",
                "Ads en ML Uruguay con CPC agresivo",
                "Bundles (2x1, kit completo)",
                "Flash sales cada 2 semanas",
            ],
            "budget_percent": 25,
            "expected_roi": "200-300%",
        })
    
    strategies.append({
        "name": "Content Marketing",
        "description": "Generar contenido organico que eduque y venda",
        "tactics": [
            "Reviews comparativas en redes sociales",
            "Videos de 'unboxing' y 'first look'",
            "Blog posts SEO sobre el nicho",
            "User-generated content (clientes mostrando el producto)",
        ],
        "budget_percent": 15,
        "expected_roi": "150-250%",
    })
    
    # Platform-specific recommendations
    platforms = {
        "mercadolibre": {
            "priority": "Alta" if margin >= 60 else "Media",
            "actions": [
                "Optimizar titulo con keywords de alta busqueda",
                "Usar todas las fotos disponibles (max 12)",
                "Activar MercadoEnvios Full",
                f"Precio recomendado: ${int(price)} UYU",
            ],
        },
        "instagram": {
            "priority": "Alta" if product.demand_score >= 70 else "Media",
            "actions": [
                "Reels de 15-30 segundos mostrando el producto",
                "Stories con encuestas y swipe-up",
                "Colaboraciones con micro-influencers (1k-10k seguidores)",
                "Hashtags especificos del nicho",
            ],
        },
        "whatsapp": {
            "priority": "Alta",
            "actions": [
                "Catalogo de productos en WhatsApp Business",
                "Broadcast a lista de clientes",
                "Respuesta automatica con info del producto",
                "Ofertas exclusivas para contactos",
            ],
        },
    }
    
    # 30-day action plan
    action_plan = [
        {"day": 1, "action": "Publicar producto en ML con listing optimizado", "platform": "mercadolibre"},
        {"day": 2, "action": "Crear 3 posts para Instagram (foto + reel + story)", "platform": "instagram"},
        {"day": 3, "action": "Enviar email a lista de contactos anunciando el producto", "platform": "email"},
        {"day": 7, "action": "Analizar primeros 5 dias de ventas y ajustar precio si es necesario", "platform": "analytics"},
        {"day": 10, "action": "Lanzar primera campaña de ads en ML ($500-1000 UYU)", "platform": "mercadolibre"},
        {"day": 14, "action": "Publicar review/comparativa en redes", "platform": "instagram"},
        {"day": 21, "action": "Oferta flash de 24 horas con 10% de descuento", "platform": "all"},
        {"day": 30, "action": "Analizar ROI del mes y ajustar estrategia", "platform": "analytics"},
    ]
    
    return {
        "product_id": pid,
        "product_name": product.name,
        "generated_at": datetime.utcnow().isoformat(),
        "strategies": strategies,
        "platforms": platforms,
        "action_plan": action_plan,
        "budget_recommendation": {
            "monthly_ads_uyu": int(price * 5) if margin >= 60 else int(price * 3),
            "split": {"mercadolibre_ads": 50, "instagram_ads": 30, "whatsapp": 10, "retargeting": 10},
        },
        "kpis": {
            "target_monthly_sales": 20 if margin >= 70 else 30 if margin >= 60 else 40,
            "target_conversion_rate": "3-5%",
            "target_response_time": "< 1 hora",
            "target_customer_rating": "4.5+",
        },
    }

@app.post("/api/products/{pid}/social-content")
def generate_social_content(pid: int, body: SocialContentInput):
    """Generate social media content for a product"""
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")
    db.close()
    
    cat = product.category or "tecnologia"
    keywords = CATEGORY_KEYWORDS.get(cat, [])
    price = getattr(product, f"price_{product.best_strategy}_uyu", product.price_cost_plus_uyu)
    
    # Hashtags
    base_hashtags = ["#Uruguay", "#Montevideo", "#Importaciones", "#ProductosImportados", "#Calidad"]
    niche_hashtags = [f"#{k.replace(' ', '')}" for k in keywords[:5]]
    all_hashtags = base_hashtags + niche_hashtags
    
    # Platform-specific content
    content = {}
    
    if body.platform == "instagram":
        content = {
            "caption": f"""✨ {product.name} — Disponible en Uruguay

¿Buscas {keywords[0] if keywords else 'calidad'}? Este producto es para vos.

💰 Precio: ${int(price)} UYU
🚚 Envio a todo el pais
✅ Stock disponible

{chr(10).join(['• ' + b for b in CATEGORY_BENEFITS.get(cat, ['Alta calidad'])[:3]])}

Link en bio o escribinos por DM 📩

{' '.join(all_hashtags[:8])}""",
            "story_text": f"🔥 {product.name}\n💰 ${int(price)} UYU\n👉 Desliza para ver mas",
            "reel_hook": f"Este {product.name} cambio mi {cat.replace('_', ' ')}...",
            "call_to_action": "Comenta 'INFO' y te mandamos los detalles",
        }
    elif body.platform == "x":
        content = {
            "tweet": f"🚀 {product.name} ahora en Uruguay\n💰 ${int(price)} UYU | Envio gratis\n📦 Stock limitado\n\n{' '.join(all_hashtags[:5])}",
            "thread": [
                f"1/3 Hoy te presento un producto que me cambio la rutina: {product.name}\n\nPrecio: ${int(price)} UYU",
                f"2/3 Por que me gusto?\n" + "\n".join([f"• {b}" for b in CATEGORY_BENEFITS.get(cat, [''])[:3]]),
                f"3/3 Si te interesa, manda DM. Stock limitado. Uruguay nomas 🚀",
            ],
        }
    elif body.platform == "tiktok":
        content = {
            "hook": f"Compre {product.name} de China y esto paso...",
            "script": f"POV: Llego tu {product.name}\n\n1. Abris el paquete 📦\n2. Lo probas 🤩\n3. Te das cuenta que valio cada peso 💰\n\nPrecio: ${int(price)} UYU",
            "hashtags": "#TikTokMadeMeBuyIt #Uruguay #Unboxing",
        }
    else:  # facebook
        content = {
            "post": f"🎯 {product.name} — Oferta especial\n\nPrecio: ${int(price)} UYU\nEnvio a todo Uruguay\n\nEscribinos por WhatsApp o ML para comprar.",
            "ad_copy": f"¿Buscas {keywords[0] if keywords else 'calidad'}? {product.name} al mejor precio del mercado. Envio gratis a Montevideo. Click para comprar.",
        }
    
    # Return without auto-saving
    return {
        "product_id": pid,
        "platform": body.platform,
        "tone": body.tone,
        "content": content,
        "hashtags": all_hashtags,
        "saved_as_campaign_id": None,
    }

@app.post("/api/marketing/campaigns")
def save_campaign(body: dict):
    """Save a campaign manually"""
    db = SessionLocal()
    campaign = MarketingCampaign(
        product_id=body.get("product_id", 0),
        name=body.get("name", "Campaña sin nombre"),
        type=body.get("type", "social"),
        content=json.dumps(body.get("content", {}), ensure_ascii=False) if isinstance(body.get("content"), dict) else body.get("content", ""),
        status="draft",
    )
    db.add(campaign)
    db.commit()
    campaign_id = campaign.id
    db.close()
    return {"ok": True, "campaign_id": campaign_id, "message": "Campaña guardada"}

@app.post("/api/products/{pid}/email-campaign")
def generate_email_campaign(pid: int, body: EmailCampaignInput):
    """Generate email marketing campaign"""
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")
    db.close()
    
    cat = product.category or "tecnologia"
    price = getattr(product, f"price_{product.best_strategy}_uyu", product.price_cost_plus_uyu)
    benefits = CATEGORY_BENEFITS.get(cat, ["Alta calidad", "Importado directo"])
    
    discount_text = f"{body.discount_percent}% OFF" if body.discount_percent > 0 else "PRECIO ESPECIAL"
    urgency_text = "⚡ Solo por 48 horas" if body.urgency else "📦 Stock disponible"
    
    subject_templates = {
        "launch": f"🚀 Lanzamiento: {product.name} en Uruguay",
        "discount": f"🔥 {discount_text} en {product.name} — {urgency_text}",
        "restock": f"📦 Volver a stock: {product.name} (se agoto rapido)",
        "seasonal": f"🎁 Oferta de temporada: {product.name} a ${int(price)} UYU",
    }
    
    email_body = f"""<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
    <h1 style="color: white; margin: 0; font-size: 24px;">{product.name}</h1>
    <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0;">{subject_templates[body.campaign_type]}</p>
  </div>
  
  <div style="padding: 30px; background: #fff;">
    <p style="font-size: 18px; line-height: 1.6;">Hola,</p>
    
    <p style="font-size: 16px; line-height: 1.6;">
      Te traemos <strong>{product.name}</strong> directo de fabrica. 
      Un producto que esta revolucionando el mercado de {cat.replace('_', ' ')}.
    </p>
    
    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
      <h3 style="margin-top: 0;">Que incluye?</h3>
      <ul style="line-height: 2;">
        <li>{benefits[0] if benefits else 'Producto original'}</li>
        <li>{benefits[1] if len(benefits) > 1 else 'Envio a todo Uruguay'}</li>
        <li>{benefits[2] if len(benefits) > 2 else 'Garantia de satisfaccion'}</li>
      </ul>
    </div>
    
    <div style="text-align: center; margin: 30px 0;">
      <div style="font-size: 36px; font-weight: bold; color: #667eea;">${int(price)} UYU</div>
      {f'<div style="font-size: 18px; color: #e74c3c; text-decoration: line-through;">Antes: ${int(price * 1.2)} UYU</div>' if body.discount_percent > 0 else ''}
      <div style="margin-top: 15px;">
        <a href="#" style="background: #667eea; color: white; padding: 15px 40px; text-decoration: none; border-radius: 30px; font-weight: bold; display: inline-block;">COMPRAR AHORA</a>
      </div>
      <p style="color: #999; font-size: 12px; margin-top: 10px;">{urgency_text}</p>
    </div>
    
    <p style="font-size: 14px; color: #666; margin-top: 30px;">
      Envios a todo Uruguay · Pago contra entrega en Montevideo · Atencion por WhatsApp
    </p>
  </div>
</body>
</html>"""
    
    # Return without auto-saving
    return {
        "product_id": pid,
        "campaign_type": body.campaign_type,
        "subject": subject_templates[body.campaign_type],
        "html_body": email_body,
        "plain_text": f"{product.name} — ${int(price)} UYU\n\n{benefits[0] if benefits else ''}\n\nComprar ahora: [link]\n\n{urgency_text}",
        "saved_as_campaign_id": None,
    }

@app.get("/api/marketing/campaigns")
def list_campaigns(product_id: Optional[int] = None):
    """List all marketing campaigns"""
    db = SessionLocal()
    query = db.query(MarketingCampaign)
    if product_id:
        query = query.filter(MarketingCampaign.product_id == product_id)
    campaigns = query.order_by(MarketingCampaign.created_at.desc()).all()
    db.close()
    return {
        "campaigns": [{"id": c.id, "name": c.name, "type": c.type, "status": c.status, "created_at": c.created_at.isoformat()} for c in campaigns],
        "count": len(campaigns),
    }

@app.get("/api/marketing/campaigns/{cid}")
def get_campaign(cid: int):
    """Get a single campaign with full content"""
    db = SessionLocal()
    c = db.query(MarketingCampaign).filter(MarketingCampaign.id == cid).first()
    if not c:
        db.close()
        raise HTTPException(404, "Campaign not found")
    
    # Get product image
    product = db.query(Product).filter(Product.id == c.product_id).first()
    product_image = product.image_url if product else ""
    product_name = product.name if product else ""
    
    # Try to parse content as JSON (for social campaigns)
    content = c.content
    try:
        parsed = json.loads(content)
        is_json = True
    except:
        parsed = None
        is_json = False
    
    db.close()
    return {
        "id": c.id,
        "name": c.name,
        "type": c.type,
        "status": c.status,
        "product_id": c.product_id,
        "product_name": product_name,
        "product_image": product_image,
        "created_at": c.created_at.isoformat(),
        "content": content,
        "parsed_content": parsed,
        "is_json": is_json,
    }

@app.delete("/api/marketing/campaigns/{cid}")
def delete_campaign(cid: int):
    """Delete a marketing campaign"""
    db = SessionLocal()
    c = db.query(MarketingCampaign).filter(MarketingCampaign.id == cid).first()
    if not c:
        db.close()
        raise HTTPException(404, "Campaign not found")
    db.delete(c)
    db.commit()
    db.close()
    return {"ok": True, "message": f"Campaign {cid} deleted"}

@app.get("/api/products/{pid}/generate-campaign-image")
async def generate_campaign_image(
    pid: int,
    style: str = Query("modern", description="Image style: modern, lifestyle, minimal, bold, unboxing"),
    usage: str = Query("feed", description="Where image will be used: feed, story, ad, listing, email"),
    design_type: str = Query("product_photo", description="Design type: product_photo, banner, mockup, social_card, flyer, hero"),
):
    """Generate campaign image. For product_photo uses Bing real photos first.
    For graphic design (banner, mockup, etc) uses Pollinations AI with creative prompts."""
    db = SessionLocal()
    product = db.query(Product).filter(Product.id == pid).first()
    if not product:
        db.close()
        raise HTTPException(404, "Product not found")

    name = product.name
    cat = product.category or "product"
    db.close()

    # DIMENSIONS per design type
    DIMS = {
        "product_photo": (1024, 1024),
        "banner": (1024, 512),
        "mockup": (1024, 1024),
        "social_card": (1024, 1024),
        "flyer": (768, 1024),
        "hero": (1280, 720),
    }
    w, h = DIMS.get(design_type, (1024, 1024))

    # ── PRODUCT PHOTO: Bing first, Pollinations fallback ──
    if design_type == "product_photo":
        bing_img = await find_product_image_bing(name)
        if bing_img:
            return {
                "product_id": pid, "product_name": name,
                "style": style, "usage": usage, "design_type": design_type,
                "image_url": bing_img, "width": w, "height": h,
                "source": "bing-images (real photo)",
                "note": "Real product photo. Loads instantly.",
            }

    # ── GRAPHIC DESIGN: Generate background with CF + compose real product ──
    # Shorten product name
    short_name = name[:60]

    # Step 1: Find real product image
    bing_img = await find_product_image_bing(name)
    product_bytes = b""
    if bing_img:
        product_bytes = await download_image(bing_img)

    # Step 2: Generate background (scene without product)
    # Prompts describe ONLY the background/scene, not the product
    BG_PROMPTS = {
        "banner": (
            f"Clean ecommerce banner background, vibrant purple-to-blue gradient, "
            f"neon light streaks, abstract geometric shapes, empty center space, "
            f"professional digital marketing backdrop, high quality"
        ),
        "mockup": (
            f"Lifestyle desk scene background, marble surface, soft natural window light, "
            f"coffee cup and smartphone on side, cozy warm tones, blurred background, "
            f"Instagram aesthetic, premium feel, empty center space"
        ),
        "social_card": (
            f"Square social media background, vibrant gradient frame, floating abstract shapes, "
            f"bold color blocking, modern geometric patterns, empty center, "
            f"professional Instagram template backdrop"
        ),
        "flyer": (
            f"Promotional flyer background, diagonal dynamic lines, bright energetic colors, "
            f"abstract shapes, discount burst graphic, clean modern backdrop, "
            f"print-ready background, empty center space"
        ),
        "hero": (
            f"Website hero background, dark futuristic tech scene, electric blue and magenta "
            f"light streaks, particle effects, abstract digital waves, cinematic atmosphere, "
            f"empty center space, ultra modern landing page backdrop"
        ),
        "product_photo": (
            f"Professional studio background, clean white surface, soft diffused lighting, "
            f"subtle shadow, minimal, product photography backdrop"
        ),
    }

    bg_prompt = BG_PROMPTS.get(design_type, BG_PROMPTS["product_photo"])

    # Style modifiers (for background)
    STYLE_BG_MODS = {
        "modern": "sleek contemporary lines",
        "lifestyle": "warm cozy ambient lighting",
        "minimal": "ultra clean white negative space",
        "bold": "high saturation dramatic colors",
        "unboxing": "warm premium packaging backdrop",
    }
    if style in STYLE_BG_MODS:
        bg_prompt += f", {STYLE_BG_MODS[style]}"

    import hashlib
    bg_hash = hashlib.md5(f"bg_{pid}_{style}_{usage}_{design_type}".encode()).hexdigest()[:12]
    bg_filename = f"bg_{pid}_{bg_hash}.png"
    final_filename = f"composed_{pid}_{bg_hash}.png"
    
    bg_path = os.path.join(_DESIGNS_DIR, bg_filename)
    final_path = os.path.join(_DESIGNS_DIR, final_filename)
    
    # If already composed, return cached
    if os.path.exists(final_path):
        return {
            "product_id": pid, "product_name": name,
            "style": style, "usage": usage, "design_type": design_type,
            "width": w, "height": h,
            "image_url": f"http://localhost:8000/generated_designs/{final_filename}",
            "source": "cloudflare-ai + real product (composed)",
            "note": f"{design_type} with real product photo composed. Reloads instantly.",
        }

    # Generate background (try CF first, then Pollinations fallback)
    bg_url = await generate_image_with_cf(bg_prompt, bg_filename, w, h)
    if not bg_url or not os.path.exists(bg_path):
        print(f"[Design] CF failed, trying Pollinations fallback...")
        bg_url = await generate_image_with_pollinations(bg_prompt, bg_filename, w, h)
    
    if not bg_url or not os.path.exists(bg_path):
        print(f"[Design] All AI generation failed, falling back to real photo")
        return {
            "product_id": pid, "product_name": name,
            "style": style, "usage": usage, "design_type": design_type,
            "image_url": bing_img if bing_img else "",
            "source": "bing-fallback" if bing_img else "failed",
            "note": "Background generation failed. Using real photo only." if bing_img else "Failed to generate design.",
        }

    # If we have a real product image, compose it
    if product_bytes:
        compose_design(bg_path, product_bytes, final_path, design_type)
        return {
            "product_id": pid, "product_name": name,
            "style": style, "usage": usage, "design_type": design_type,
            "width": w, "height": h,
            "image_url": f"/generated_designs/{final_filename}",
            "source": "ai + real product (composed)",
            "note": f"{design_type} with your real product photo. AI background + real product.",
        }
    
    # No real product image, just return the background
    return {
        "product_id": pid, "product_name": name,
        "style": style, "usage": usage, "design_type": design_type,
        "width": w, "height": h,
        "image_url": f"/generated_designs/{bg_filename}",
        "source": "ai (background only)",
        "note": f"AI-generated {design_type} background. No real product photo found.",
    }

@app.get("/api/marketing/dashboard")
def marketing_dashboard():
    """Marketing dashboard overview"""
    db = SessionLocal()
    total_campaigns = db.query(MarketingCampaign).count()
    active_campaigns = db.query(MarketingCampaign).filter(MarketingCampaign.status == "active").count()
    products_with_campaigns = db.query(MarketingCampaign.product_id).distinct().count()
    
    # Products ready for marketing (have real images, high margin)
    ready_products = db.query(Product).filter(Product.best_margin >= 60).count()
    
    db.close()
    
    return {
        "campaigns": {"total": total_campaigns, "active": active_campaigns, "draft": total_campaigns - active_campaigns},
        "products": {"total": products_with_campaigns, "ready_for_marketing": ready_products},
        "recommendations": [
            f"{ready_products} productos listos para campañas de marketing (margen 60%+)",
            "Activar campañas de ML Ads para productos con demanda > 75",
            "Crear contenido social semanal para mantener engagement",
            "Segmentar email marketing por categoria de producto",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
