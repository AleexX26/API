"""Import of a Print24 price-matrix answer that a person copied from Chrome DevTools (tab Response).

This is a MANUAL import of a capture, not a connection to Print24: nothing here calls Print24, and no cookie, token or `Auth` header
is read, asked for or stored (a text that looks like one is refused). The answer is parsed with the strict parser
(`app.parsers.price_matrix`); the configuration it belongs to (format, paper, sides, finishing) is written by the person from what the
page shows, because the answer itself only carries numeric ids (the request's `properties` list holds ids and keys, not labels), and
nothing is guessed from those ids.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.collectors import offers
from app.collectors.laimprentadeinternet import slug
from app.collectors.print24_options import CARDS, DELIVERY, SCOPE, build_products
from app.parsers.price_matrix import MatrixError, parse_matrix

PROVIDER = "print24"
REQUIRED = {"format": "el formato", "paper": "el papel", "sides": "las caras", "finishing": "el acabado"}
OPTIONAL = ("orientation", "inks")
MAX_TEXT = 2_000_000
SECRET = re.compile(r"(?im)^\s*:?(cookie|auth|authorization|set-cookie)\s*:|user_identifier_token|\bbearer\s+[a-z0-9._-]{8,}|\bjwt=ey")
ORIGIN = {"group": "Origen", "label": "Captura copiada de DevTools (importada a mano)"}


class CaptureError(ValueError):
    pass


def refuse_secrets(*texts: str) -> None:
    for text in texts:
        if text and SECRET.search(text):
            raise CaptureError("El texto parece incluir cookies o credenciales (Cookie, Auth, token): pega solo el JSON de las pestañas Payload y Response")


def clean_configuration(configuration: dict) -> dict:
    state = {key: " ".join(str(configuration.get(key) or "").split()) for key in (*REQUIRED, *OPTIONAL)}
    missing = [name for key, name in REQUIRED.items() if not state[key]]
    if missing:
        raise CaptureError("Indica " + ", ".join(missing) + " tal como los muestra la página: la respuesta solo trae números de identificador")
    if any(len(v) > 120 for v in state.values()):
        raise CaptureError("Algún texto de la configuración es demasiado largo")
    return state


def request_checks(request_payload: dict | None, prices: list) -> list[str]:
    """What the Payload tab lets us verify against the answer (only what is in it; nothing is inferred)."""
    if not request_payload:
        return ["No se pegó el Payload: no se pudo comprobar que las cantidades de la petición coinciden con la respuesta"]
    asked = request_payload.get("quantities")
    got = {p.quantity_id for p in prices}
    if not isinstance(asked, list):
        return ["El Payload no trae la lista «quantities»"]
    asked_ids = {str(x) for x in asked}
    notes = []
    if asked_ids != got:
        notes.append(f"Las cantidades pedidas {sorted(asked_ids)} no coinciden con las recibidas {sorted(got)}")
    else:
        notes.append(f"Coinciden las {len(got)} cantidades pedidas y recibidas")
    if "product_alias_id" in request_payload:
        notes.append(f"product_alias_id {request_payload['product_alias_id']} (se anota; no se sabe a qué ficha corresponde)")
    return notes


def import_capture(db_path: Path, response_text: str, configuration: dict, request_payload: dict | None = None, *,
                   url: str = CARDS, title: str = "Tarjetas de visita", now: datetime | None = None) -> dict:
    if not isinstance(response_text, str) or not response_text.strip() or len(response_text) > MAX_TEXT:
        raise CaptureError("Falta el texto de la pestaña Response (o es demasiado largo)")
    refuse_secrets(response_text, json.dumps(request_payload) if request_payload else "")
    state = clean_configuration(configuration)
    try:
        prices = parse_matrix(response_text)
    except MatrixError as exc:
        raise CaptureError(f"La respuesta no tiene la forma de un price-matrix: {exc}") from exc
    now = now or datetime.now(timezone.utc)
    key = slug(" ".join(state[k] for k in ("format", "paper", "sides", "finishing") if state[k]))
    products = build_products(url, title, state, prices)
    for product in products:
        delivery = product["url"].rsplit("-", 1)[-1]
        product["url"] = f"{url}#captura-{key}-{delivery}"
        product["spec"] = product["spec"] + [ORIGIN]
        for row in product["rows"]:
            row["scope"] = SCOPE + " (captura importada a mano)"
    db = offers.connect(db_path)
    try:
        # exact addresses, not "key-%": a configuration whose key starts with another one ("barniz" / "barniz protector") must not be erased
        mine = [f"{url}#captura-{key}-{slug(name)}" for name in DELIVERY.values()]
        offers.replace_group(db, PROVIDER, mine, products, now.isoformat(timespec="seconds"))
    finally:
        db.close()
    return {"configuration": state, "products": len(products), "prices": len(prices),
            "quantities": sorted({p.quantity_value for p in prices}), "deliveries": sorted({p.delivery_type for p in prices}),
            "checks": request_checks(request_payload, prices), "key": key}


def list_captures(db_path: Path) -> list[dict]:
    db = offers.connect(db_path)
    try:
        db.row_factory = None
        found: dict[str, dict] = {}
        for url, name, quantity, price, days, spec, seen in db.execute(
                "SELECT product_url, product_name, quantity, price, delivery_days, spec_json, observed_at FROM supplier_offers "
                "WHERE provider=? AND product_url LIKE ? ORDER BY product_url, quantity", (PROVIDER, "%#captura-%")):
            item = found.setdefault(url, {"url": url, "name": name, "observed_at": seen, "spec": json.loads(spec), "rows": []})
            item["rows"].append({"quantity": quantity, "total_net": price, "delivery_days": days})
        return list(found.values())
    finally:
        db.close()
