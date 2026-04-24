import sys
sys.path.insert(0, '/home/facajgs/uy-import-ops/research-dashboard/backend')
from main import SessionLocal, Product, calculate_landed_cost

db = SessionLocal()
existing = db.query(Product).all()
if existing:
    for p in existing:
        db.delete(p)
    db.commit()
    print(f"Cleared {len(existing)} old products")

demos = [
    {"name": "Auriculares Bluetooth ANC", "category": "Electrónica", "cost": 12, "ship": 4, "tariff": 0.15, "ml": 2490, "status": "winner"},
    {"name": "Organizador cables magnético", "category": "Hogar", "cost": 3.5, "ship": 2, "tariff": 0.10, "ml": 890, "status": "testing"},
    {"name": "Lámpara LED escritorio", "category": "Hogar", "cost": 8, "ship": 5, "tariff": 0.18, "ml": 1890, "status": "testing"},
    {"name": "Soporte notebook aluminio", "category": "Electrónica", "cost": 9, "ship": 4.5, "tariff": 0.15, "ml": 2190, "status": "researching"},
    {"name": "Botella térmica inteligente", "category": "Hogar", "cost": 6.5, "ship": 3.5, "tariff": 0.12, "ml": 1590, "status": "researching"},
    {"name": "Mini masajeador portátil", "category": "Bienestar", "cost": 7, "ship": 4, "tariff": 0.15, "ml": 1990, "status": "importing"},
    {"name": "Hub USB-C 7 en 1", "category": "Electrónica", "cost": 14, "ship": 3, "tariff": 0.15, "ml": 3290, "status": "winner"},
    {"name": "Mochila antirrobo USB", "category": "Accesorios", "cost": 18, "ship": 6, "tariff": 0.20, "ml": 3890, "status": "flop"},
]

for d in demos:
    calc = calculate_landed_cost(d["cost"], d["ship"], d["tariff"], 0.22, 0.03, 15)
    suggested = calc["total_uyu"] * 1.6
    margin = (suggested - calc["total_uyu"]) / suggested * 100 if suggested > 0 else 0
    opp = 50
    if d["ml"] > 0 and calc["total_uyu"] > 0:
        if suggested < d["ml"]:
            opp = min(95, 50 + int((d["ml"] - suggested) / d["ml"] * 50))
        else:
            opp = max(10, 50 - int((suggested - d["ml"]) / d["ml"] * 50))
    p = Product(
        name=d["name"], category=d["category"],
        product_cost_usd=d["cost"], shipping_cost_usd=d["ship"],
        tariff_rate=d["tariff"], total_landed_cost_uyu=calc["total_uyu"],
        suggested_price_uyu=round(suggested, 2),
        margin_pct=round(margin, 1), status=d["status"],
        ml_competitor_price=d["ml"], opportunity_score=opp,
    )
    db.add(p)

db.commit()
db.close()
print(f"Seeded {len(demos)} products")
