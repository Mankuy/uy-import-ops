#!/bin/bash
# UYHunter — Local development startup
# Arranca Camofox Browser + UYHunter API

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "╔═══════════════════════════════════════╗"
echo "║   UYHunter — Multi-Source Hunter      ║"
echo "║   🟦 Banggood (httpx directo)         ║"
echo "║   🟠 AliExpress (via Camofox)         ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# --- Camofox Browser ---
CAMOFOX_DIR="$DIR/../camofox-browser"
if [ -d "$CAMOFOX_DIR" ]; then
    echo "🦊 Iniciando Camofox Browser..."
    cd "$CAMOFOX_DIR"
    if [ ! -d "node_modules" ]; then
        echo "   📦 Instalando dependencias de Camofox..."
        npm install
    fi
    npm start &
    CAMOFOX_PID=$!
    echo "   ✅ Camofox PID: $CAMOFOX_PID (puerto 9377)"
    cd "$DIR"
    sleep 3
else
    echo "⚠️  Camofox no encontrado en $CAMOFOX_DIR"
    echo "   AliExpress no estará disponible."
    echo "   Para habilitarlo: cd ~/uy-import-ops && git clone https://github.com/jo-inc/camofox-browser.git"
    echo ""
fi

# --- UYHunter API ---
echo ""
echo "🚀 Iniciando UYHunter API..."
cd "$DIR"

# Crear venv si no existe
if [ ! -d "venv" ]; then
    echo "   📦 Creando entorno virtual..."
    python3 -m venv venv
fi

source venv/bin/activate

# Instalar dependencias
pip install -q -r requirements.txt 2>/dev/null

echo "   🌐 API: http://localhost:8000"
echo "   📊 Dashboard: http://localhost:8000/"
echo "   📖 Swagger: http://localhost:8000/docs"
echo ""
echo "   Ctrl+C para detener todo"
echo ""

# Trap para limpiar Camofox al salir
cleanup() {
    echo ""
    echo "🛑 Deteniendo servicios..."
    if [ -n "$CAMOFOX_PID" ]; then
        kill $CAMOFOX_PID 2>/dev/null || true
        echo "   🦊 Camofox detenido"
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

uvicorn hunter_svc:app --host 0.0.0.0 --port 8000 --reload
