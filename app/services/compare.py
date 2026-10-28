"""Side-by-side comparison of collected products: same size, same paper weight and same number of sides, one price per provider.

Orientative: it does not know about finishes or ink details, so the web asks to check the product pages.
"""
import re
from decimal import Decimal

from app.services.cards import grams_in, sides_in, sizes_in
from app.services.products import DIN
from app.services.workbench import IVA, PROVIDERS, normalize

SIZE_GROUPS = ("formato", "tamano", "medidas")
PAPER_GROUPS = ("papel", "material", "soporte", "elige el papel")


def item_text(item: dict) -> str:
    return normalize(item["title"] + " " + item["url"].rsplit("/", 1)[-1].replace("-", " ") + " " + " ".join(f"{x['group']} {x['label']}" for x in item["spec"]))


def item_sizes(item: dict) -> set:
    """Sizes in mm (both orders) from the format of the page, else from its name and address; A5 = 148 x 210."""
    for source in ([f"{x['label']}" for x in item["spec"] if normalize(x["group"]) in SIZE_GROUPS], [item["title"], item["url"].replace("-", " ")]):
        found = set()
        for text in source:
            text = normalize(text)
            found |= sizes_in(text)
            for name in re.findall(r"\b(a[3-8]|dl)\b", text):
                found |= {DIN[name], DIN[name][::-1]}
        if found:
            return found
    return set()


def item_grams(item: dict) -> str:
    for source in ([x["label"] for x in item["spec"] if normalize(x["group"]) in PAPER_GROUPS], [item_text(item)]):
        for text in source:
            if (found := sorted(grams_in(normalize(text)))):
                return found[0]
    return ""


def search_tokens(item: dict) -> str:
    """Extra words a person may type to find this product: 85x55, a5, 350g."""
    tokens = {f"{w}x{h}" for w, h in item_sizes(item)} | {name for name, size in DIN.items() if size in item_sizes(item)}
    tokens |= {f"{g}g" for g in grams_in(item_text(item))}
    return " ".join(sorted(tokens))


def price_at(item: dict, quantity: int) -> tuple[Decimal, bool] | None:
    """Total net price at exactly that quantity (and whether it is estimated from a unit price), or None."""
    for q, price in item.get("prices", []):
        if int(q) == quantity:
            return (Decimal(price) * quantity, True) if item["price_kind"] == "unit" else (Decimal(price), False)
    return None


def gross(total: Decimal, tax: str) -> Decimal | None:
    """Total with 21% VAT: net prices get it added, gross ones stay, unknown ones cannot be compared."""
    return total * IVA if tax == "net" else total if tax == "gross" else None


def compare(items: list[dict], quantity: int) -> dict:
    rows: dict[tuple, dict] = {}
    skipped = 0
    for item in items:
        sizes = item_sizes(item)
        grams = item_grams(item)
        sides = sides_in(item_text(item))
        priced = price_at(item, quantity)
        if not sizes or not grams or priced is None:
            skipped += 1
            continue
        size = tuple(sorted(sizes, key=lambda s: (-s[0], s[1]))[0])
        side = next(iter(sides)) if len(sides) == 1 else 0
        row = rows.setdefault((size, grams, side), {"size": f"{size[0]} × {size[1]} mm", "grams": grams, "sides": side, "cells": {}})
        cell = row["cells"].get(item["provider"])
        tax = item.get("tax_status", "unknown")
        if cell is None or priced[0] < Decimal(cell["total"]):
            row["cells"][item["provider"]] = {"total": str(priced[0]), "estimated": priced[1], "tax_status": tax, "title": item["title"], "url": item["url"]}
    order = {p["id"]: i for i, p in enumerate(PROVIDERS)}
    out = []
    for row in rows.values():
        known = {p: gross(Decimal(c["total"]), c["tax_status"]) for p, c in row["cells"].items()}
        known = {p: v for p, v in known.items() if v is not None}  # a price with unknown VAT is shown but never marked cheapest
        cheapest = min(known, key=known.get) if len(known) > 1 else None
        sides = {1: " · 1 cara", 2: " · 2 caras"}.get(row["sides"], "")
        out.append({"label": f"{row['size']} · {row['grams']} g/m²{sides}", "cells": row["cells"], "cheapest": cheapest,
                    "providers": len(row["cells"])})
    out.sort(key=lambda r: (-r["providers"], min(Decimal(c["total"]) for c in r["cells"].values())))
    used = sorted({p for r in out for p in r["cells"]}, key=lambda p: order.get(p, 99))
    return {"quantity": quantity, "providers": used, "rows": out[:60], "skipped": skipped}
