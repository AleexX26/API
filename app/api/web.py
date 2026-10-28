"""Local-only supplier workspace. No background network activity."""
import ipaddress
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.services.cards import CARD_KEYS, CARD_TYPES, card_form
from app.services.products import product_form
from app.services.workbench import IDS, PROVIDERS, catalog_listing, init_db, save_quote, search, valid_source

ROOT = Path(__file__).resolve().parents[2]


class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=100)
    quantity: int = Field(ge=1, le=1000000)
    format: str = Field(max_length=100, default="Sin especificar")
    material: str = Field(max_length=150, default="Sin especificar")
    printing: str = Field(max_length=100, default="Sin especificar")
    finishing: str = Field(max_length=150, default="Sin especificar")
    max_days: int = Field(ge=1, le=180, default=30)
    country: Literal["ES"] = "ES"
    extras: dict[str, str] = Field(default_factory=dict, max_length=12)
    strict: bool = False  # characteristics form: show only products that meet every chosen characteristic
    generic: bool = False  # strict form built from the collected pages (flyers, bags…) instead of the business-card one
    filters: dict[str, str] = Field(default_factory=dict, max_length=16)

    @field_validator("extras")
    @classmethod
    def known_extras(cls, value):
        clean = {}
        for key, val in value.items():
            if key not in CARD_KEYS:
                raise ValueError("Característica desconocida")
            val = val.strip()
            if key == "type" and val and val not in CARD_TYPES:
                raise ValueError("Tipo de tarjeta no válido")
            if len(val) > 100:
                raise ValueError("Valor demasiado largo")
            if val:
                clean[key] = val
        return clean

    @field_validator("filters")
    @classmethod
    def clean_filters(cls, value):
        clean = {}
        for key, val in value.items():
            if len(key) > 60 or len(val) > 150:
                raise ValueError("Filtro demasiado largo")
            if val.strip():
                clean[key.strip()] = val.strip()
        return clean

    @field_validator("query", "format", "material", "printing", "finishing")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Introduce un valor o indica Sin especificar")
        return value.strip()


class SearchRequest(BaseModel):
    brief: Brief
    providers: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("providers")
    @classmethod
    def known(cls, value):
        if not set(value) <= IDS:
            raise ValueError("Proveedor desconocido")
        return value


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brief: Brief
    provider: str
    product_net: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    shipping_net: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    additional_net: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    delivery_days: int = Field(ge=1, le=180)
    valid_until: date
    source_url: str = Field(max_length=1500)
    notes: str = Field(max_length=2000, default="")
    confirmed_equivalent: Literal[True]


LOOPBACK = ("127.0.0.1", "::1", "localhost", "testclient")


def private_client(host: str | None) -> bool:
    try:
        return ipaddress.ip_address(host or "").is_private
    except ValueError:
        return host in LOOPBACK


def create_app(database: Path | None = None, seed: Path | None = None, catalog: Path | None = None, lan: bool = False) -> FastAPI:
    """lan=True also serves the other computers of the private network, read-only (only this PC saves quotes)."""
    if catalog is None and database is None:
        catalog = Path(os.environ.get("PRINT_CATALOG_DB", ROOT / "data/catalog.sqlite3"))  # tests pass explicit paths
    database = database or Path(os.environ.get("PRINT_WORKBENCH_DB", ROOT / "data/workbench.sqlite3"))
    seed = seed or ROOT / "data/catalog_links.json"
    init_db(database)
    app = FastAPI(title="Mesa de impresión", docs_url="/api/docs")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"] if lan else ["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_write_guard(request: Request, call_next):
        client = request.client.host if request.client else None
        if lan and not private_client(client):
            return JSONResponse({"detail": "Solo la red local"}, status_code=403)
        if request.method == "POST":
            origin = request.headers.get("origin")
            same = ("http://127.0.0.1:8765", "http://localhost:8765") + ((f"http://{request.headers.get('host')}",) if lan else ())
            if origin and origin not in same:
                return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
            if lan and request.url.path == "/api/quotes" and client not in LOOPBACK:
                return JSONResponse({"detail": "Solo lectura: los presupuestos se guardan desde el PC que aloja el comparador"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Se requiere JSON"}, status_code=415)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.method == "GET" and not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"  # local app: always pick up the latest page and script
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web/index.html")

    @app.get("/api/providers")
    def providers():
        return {"providers": PROVIDERS}

    @app.get("/api/catalog")
    def catalog_view(provider: str = "", q: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                     cards: str = Query("", max_length=1500)):
        if provider and provider not in IDS:
            raise HTTPException(422, "Proveedor desconocido")
        brief = None
        if cards:  # JSON with the business-card form: format, material, printing, finishing, extras
            try:
                data = json.loads(cards)
                brief = Brief(query="tarjetas de visita", quantity=1, **data).model_dump()
            except (ValueError, TypeError):
                raise HTTPException(422, "Filtros de tarjetas no válidos")
        return catalog_listing(catalog, provider or None, q, limit, offset, brief)

    @app.get("/api/card-options")
    def card_choices():
        return card_form(catalog)

    @app.get("/api/product-options")
    def product_choices(q: str = Query(..., min_length=2, max_length=100)):
        return product_form(catalog, q)

    @app.post("/api/search")
    def find(data: SearchRequest):
        return search(database, seed, data.brief.model_dump(), data.providers, catalog)

    @app.post("/api/quotes", status_code=201)
    def add(data: QuoteRequest):
        if data.provider not in IDS:
            raise HTTPException(422, "Proveedor desconocido")
        try:
            valid = valid_source(data.provider, data.source_url)
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(422, "La URL debe ser HTTPS del proveedor seleccionado")
        payload = data.model_dump()
        payload["valid_until"] = data.valid_until.isoformat()
        return {"id": save_quote(database, payload)}

    app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")
    return app
