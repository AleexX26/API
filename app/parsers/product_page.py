"""Read the default configuration and its price matrix out of a saved Print24 product page.

Offline only: works on an HTML file already on disk. The page is a Next.js app whose data
travels in `self.__next_f.push([1,"..."])` fragments; joined, they contain
`calculationData` (options, default selection and the price matrix of that default selection).
"""
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs

from app.parsers.price_matrix import MatrixError

PUSH = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', re.S)
# Groups that the price matrix itself spans: they are not part of the configuration identity.
SPANNED = {"quantity", "shipping_type"}


def flight_text(html: str) -> str:
    parts = [json.loads(m.group(1)) for m in PUSH.finditer(html)]
    if not parts:
        raise MatrixError("No embedded page data found")
    return "".join(parts)


def calculation_data(html: str) -> dict:
    flight = flight_text(html)
    decoder = json.JSONDecoder(parse_float=Decimal)
    marker = '"calculationData":'
    start = flight.find(marker)
    while start != -1:
        try:
            data, _ = decoder.raw_decode(flight, start + len(marker))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and "priceMatrix" in data and "itemMaster" in data:
            return data
        start = flight.find(marker, start + 1)
    raise MatrixError("calculationData with a price matrix not found")


def default_configuration(html: str, *, url: str, observed_at: datetime, refresh_days: int = 31) -> tuple[str, dict]:
    """Return (price_matrix_json, import_context) for the page's default configuration."""
    data = calculation_data(html)
    master = data["itemMaster"]
    link = parse_qs(master["deepLink"])
    try:
        product_id = link["product_alias_id"][0]
        country = link["delivery_country_code"][0]
        currency = data["priceMatrix"][0]["quantity"]["shipping_type"][0]["price"]["currency"]
    except (KeyError, IndexError) as exc:
        raise MatrixError(f"Unexpected page structure: {exc!r}") from exc
    properties = [p for p in master["selectedProps"] if p["name"] not in SPANNED]
    matrix = json.dumps(data["priceMatrix"], default=str, ensure_ascii=False)
    context = {
        "product_id": product_id,
        "properties": [{"name": p["name"], "id": p["id"]} for p in properties],
        "country": country,
        "currency": currency,
        "account_scope": "public-web-no-session",
        "services": {},
        "validity_evidence": (f"Default configuration read from the public product page {url} "
                              "without a session. valid_until is our own refresh deadline, not a Print24 promise."),
        "observed_at": observed_at.isoformat(),
        "valid_until": (observed_at + timedelta(days=refresh_days)).isoformat(),
    }
    return matrix, context
