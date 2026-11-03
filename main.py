import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import dashboard, stock, actions, movements, orders, settings, inventory

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialisation de la base de données et des données de démo au démarrage
    init_db()
    yield

app = FastAPI(
    title="StockMaster Pro - Gestion de Stock Multi-Déclinaisons",
    description="Solution Full-Stack de gestion de stock multi-couleurs, suivi financier en temps réel et traçabilité",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Montage des dossiers statiques
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Enregistrement des routes API
app.include_router(dashboard.router)
app.include_router(stock.router)
app.include_router(actions.router)
app.include_router(movements.router)
app.include_router(orders.router)
app.include_router(settings.router)
app.include_router(inventory.router)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(BASE_DIR, "templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Application en cours de chargement...</h1>")

@app.get("/supabase_schema.sql")
async def serve_supabase_schema():
    schema_path = os.path.join(BASE_DIR, "supabase_schema.sql")
    if os.path.exists(schema_path):
        return FileResponse(schema_path, media_type="text/plain", filename="supabase_schema.sql")
    return HTMLResponse("Fichier introuvable", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
