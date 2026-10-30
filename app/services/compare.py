"""Side-by-side comparison of collected products: same size, paper weight and family, finish and number of sides, one price per provider.

Products that are not comparable (blank garments, without printing) stay out. Orientative still: ink details are not compared.
"""
import re
from decimal import Decimal

from app.services.cards import FINISH_TERMS, NEGATED, PAPER_FAMILIES, grams_in, sides_in, sizes_in
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


def price_at(item: dict, quantity: int) -> dict | None:
    """Net total at that quantity: {"total", "estimated" (from a unit price or between two tiers), "between" ([lo, hi] or None)}.

    Exact tier first. A page with unit prices by bracket ('from N units') gives the unit price of the largest bracket not above
    the quantity. For totals, a quantity between two tiers is estimated from the unit prices of its neighbours (never beyond them).
    """
    tiers = sorted({(int(t[0]), Decimal(t[1])) for t in item.get("prices", [])})
    if not tiers or quantity < 1:
        return None
    if item["price_kind"] == "unit":
        below = [t for t in tiers if t[0] <= quantity]
        return {"total": str((below[-1][1] * quantity).quantize(Decimal("0.01"))), "estimated": True, "between": None} if below else None
    for q, price in tiers:
        if q == quantity:
            return {"total": str(price), "estimated": False, "between": None}
    lo = [t for t in tiers if t[0] < quantity]
    hi = [t for t in tiers if t[0] > quantity]
    if not lo or not hi:
        return None
    (q1, p1), (q2, p2) = lo[-1], hi[0]
    unit = p1 / q1 + (p2 / q2 - p1 / q1) * Decimal(quantity - q1) / Decimal(q2 - q1)
    return {"total": str((unit * quantity).quantize(Decimal("0.01"))), "estimated": True, "between": [q1, q2]}


def item_family(item: dict) -> str:
    """Paper family named by the page (estucado, offset, carton…), or '' when it does not say."""
    sources = [x["label"] for x in item["spec"] if normalize(x["group"]) in PAPER_GROUPS] or [item_text(item)]
    text = normalize(" ".join(sources))
    return next((family for family, terms in PAPER_FAMILIES.items() if any(t in text for t in terms)), "")


def item_finishes(item: dict) -> tuple:
    """Finishes the page names (barniz, relieve, plastific…), leaving out the 'sin …' ones."""
    text = NEGATED.sub("", item_text(item))
    return tuple(sorted(name for name, terms in FINISH_TERMS.items() if any(t in text for t in terms)))


def gross(total: Decimal, tax: str) -> Decimal | None:
    """Total with 21% VAT: net prices get it added, gross ones stay, unknown ones cannot be compared."""
    return total * IVA if tax == "net" else total if tax == "gross" else None


def days_at(item: dict, quantity: int | None) -> tuple[int | None, int | None]:
    """(days of the cheapest option, days of the fastest option) at that quantity, or over all tiers when it has none."""
    tiers = item.get("prices", [])
    chosen = [t for t in tiers if quantity is not None and int(t[0]) == quantity] or tiers
    cheapest = next((t[2] for t in chosen if len(t) > 2 and t[2] is not None), None)
    fastest = [t[3] for t in chosen if len(t) > 3 and t[3] is not None]
    return cheapest, min(fastest) if fastest else None


def finish_label(finishes: tuple) -> str:
    return " + ".join({"plastific": "plastificado", "laminado en caliente": "laminado en caliente"}.get(f, f) for f in finishes) or "sin acabado"


def compare(items: list[dict], quantity: int) -> dict:
    """One row per configuration (size, paper weight, paper family, finish, sides) and one price per provider at that quantity."""
    rows: dict[tuple, dict] = {}
    loose: dict[tuple, dict] = {}  # same size, weight and sides but maybe other paper or finish: "similar", never "equal"
    skipped = excluded = 0
    for item in items:
        if not item.get("comparable", True):
            excluded += 1
            continue
        sizes = item_sizes(item)
        grams = item_grams(item)
        sides = sides_in(item_text(item))
        priced = price_at(item, quantity)
        if not sizes or not grams or priced is None:
            skipped += 1
            continue
        size = tuple(sorted(sizes, key=lambda s: (-s[0], s[1]))[0])
        side = next(iter(sides)) if len(sides) == 1 else 0
        family, finishes = item_family(item), item_finishes(item)
        row = rows.setdefault((size, grams, family, finishes, side), {"size": f"{size[0]} × {size[1]} mm", "grams": grams, "family": family,
                                                                     "finishes": finishes, "sides": side, "cells": {}})
        data = {**priced, "tax_status": item.get("tax_status", "unknown"), "shipping": item.get("shipping", "unknown"),
                "days": days_at(item, quantity)[0], "title": item["title"], "url": item["url"]}
        cell = row["cells"].get(item["provider"])
        if cell is None or Decimal(priced["total"]) < Decimal(cell["total"]):
            row["cells"][item["provider"]] = data
        group = loose.setdefault((size, grams, side), {"size": f"{size[0]} × {size[1]} mm", "grams": grams, "sides": side, "cells": {}})
        current = group["cells"].get(item["provider"])
        if current is None or Decimal(priced["total"]) < Decimal(current["total"]):
            group["cells"][item["provider"]] = {**data, "detail": f"{family or 'papel sin indicar'} · {finish_label(finishes)}", "key": (family, finishes)}
    order = {p["id"]: i for i, p in enumerate(PROVIDERS)}
    similar = []
    for group in loose.values():
        if len(group["cells"]) > 1 and len({c["key"] for c in group["cells"].values()}) > 1:
            known = {p: gross(Decimal(c["total"]), c["tax_status"]) for p, c in group["cells"].items()}
            known = {p: v for p, v in known.items() if v is not None}
            sides = {1: " · 1 cara", 2: " · 2 caras"}.get(group["sides"], "")
            for c in group["cells"].values():
                c.pop("key")
            similar.append({"label": f"{group['size']} · {group['grams']} g/m²{sides}", "cells": group["cells"],
                            "cheapest": min(known, key=known.get) if len(known) > 1 else None, "providers": len(group["cells"])})
    similar.sort(key=lambda r: (-r["providers"], min(Decimal(c["total"]) for c in r["cells"].values())))
    out = []
    for row in rows.values():
        known = {p: gross(Decimal(c["total"]), c["tax_status"]) for p, c in row["cells"].items()}
        known = {p: v for p, v in known.items() if v is not None}  # a price with unknown VAT is shown but never marked cheapest
        cheapest = min(known, key=known.get) if len(known) > 1 else None
        sides = {1: " · 1 cara", 2: " · 2 caras"}.get(row["sides"], "")
        finish = finish_label(row["finishes"])
        out.append({"label": f"{row['size']} · {row['grams']} g/m² · {row['family'] or 'papel sin indicar'}{sides} · {finish}", "cells": row["cells"],
                    "cheapest": cheapest, "providers": len(row["cells"])})
    out.sort(key=lambda r: (-r["providers"], min(Decimal(c["total"]) for c in r["cells"].values())))
    used = sorted({p for r in out for p in r["cells"]}, key=lambda p: order.get(p, 99))
    used = sorted({p for r in out + similar for p in r["cells"]}, key=lambda p: order.get(p, 99))
    return {"quantity": quantity, "providers": used, "rows": out[:60], "similar": similar[:40], "skipped": skipped, "excluded": excluded}
