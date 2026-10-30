"""Isolated multi-supplier workbench; never mixes synthetic Print24 prices."""
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

PROVIDERS = [
    {"id": "print24", "name": "Print24", "url": "https://print24.com/es", "initials": "P24", "specialty": "Impresión y gran formato"},
    {"id": "truyol", "name": "Truyol", "url": "https://truyol.com/", "initials": "TR", "specialty": "Impresión digital y acabados"},
    {"id": "printai", "name": "Printai", "url": "https://www.printai.es/", "initials": "PA", "specialty": "Impresión y packaging"},
    {"id": "onlineprinters", "name": "Onlineprinters", "url": "https://www.onlineprinters.es/", "initials": "OP", "specialty": "Impresión digital y offset"},
    {"id": "stricker", "name": "Stricker", "url": "https://www.stricker-europe.com/es/", "initials": "ST", "specialty": "Regalo promocional y textil"},
    {"id": "tuskamisetas", "name": "TusKamisetas", "url": "https://www.tuskamisetas.com/es", "initials": "TK", "specialty": "Textil y personalización"},
]
IDS = {p["id"] for p in PROVIDERS}
IVA = Decimal("1.21")  # Spanish VAT 21%: prices read as net are shown with it added


def normalize(value: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                            if not unicodedata.combining(c)).split())


def signature(brief: dict) -> str:
    normalized = {key: normalize(value) if isinstance(value, str) else value for key, value in brief.items()}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS supplier_quotes (
          id INTEGER PRIMARY KEY, provider TEXT NOT NULL, brief_hash TEXT NOT NULL,
          brief_json TEXT NOT NULL, product_net TEXT NOT NULL, shipping_net TEXT,
          additional_net TEXT NOT NULL, delivery_days INTEGER NOT NULL,
          valid_until TEXT NOT NULL, source_url TEXT NOT NULL, notes TEXT NOT NULL,
          created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_quotes_brief ON supplier_quotes(brief_hash,provider,created_at);
        ''')


def valid_source(provider: str, url: str) -> bool:
    domain = urlsplit(next(p["url"] for p in PROVIDERS if p["id"] == provider)).hostname.removeprefix("www.")
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname is not None
            and parsed.hostname.removeprefix("www.") == domain
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443))


def save_quote(path: Path, data: dict) -> int:
    with sqlite3.connect(path) as db:
        cursor = db.execute('''INSERT INTO supplier_quotes
        (provider,brief_hash,brief_json,product_net,shipping_net,additional_net,
        delivery_days,valid_until,source_url,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (data["provider"], signature(data["brief"]), json.dumps(data["brief"], ensure_ascii=False),
         str(data["product_net"]), None if data["shipping_net"] is None else str(data["shipping_net"]),
         str(data["additional_net"]), data["delivery_days"], data["valid_until"], data["source_url"],
         data["notes"], datetime.now(timezone.utc).isoformat()))
        return cursor.lastrowid


def print24_entry(db: sqlite3.Connection, configuration_id: str, title: str, url: str, fetched_at: str,
                  spec: list, quantity: int, max_days: int) -> dict:
    offers = []
    for r in db.execute("""SELECT q.value AS quantity, s.source_id AS delivery_type, p.delivery_days, p.delivery_text,
                           p.product_net, p.shipping_net, p.total_net, p.total_gross
                           FROM prices p JOIN quantities q ON q.id=p.quantity_id
                           JOIN shipping_options s ON s.id=p.shipping_option_id
                           WHERE p.configuration_id=?""", (configuration_id,)):
        o = dict(r)
        o["meets_deadline"] = int(o["delivery_days"]) <= max_days
        offers.append(o)
    offers.sort(key=lambda o: (o["quantity"], Decimal(o["total_net"])))
    exact = [o for o in offers if o["quantity"] == quantity and o["meets_deadline"]]
    return {"title": title, "url": url, "fetched_at": fetched_at, "spec": spec, "offers": offers, "tax_status": "net",
            "quantities": sorted({o["quantity"] for o in offers}), "matches_quantity": bool(exact),
            "suggested": min(exact, key=lambda o: Decimal(o["total_net"])) if exact else None}


def auto_offers(catalog: Path | None, terms: set[str], words: list[str], quantity: int, max_days: int) -> list[dict]:
    """Print24 default-configuration prices collected into the catalog DB. References, not verified equivalents."""
    if catalog is None or not Path(catalog).exists():
        return []
    db = sqlite3.connect(f"file:{Path(catalog).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        try:
            pages = db.execute("SELECT * FROM product_pages WHERE status='ok' ORDER BY url").fetchall()
        except sqlite3.OperationalError:
            return []
        try:
            specs = {r["url"]: json.loads(r["spec_json"]) for r in db.execute("SELECT * FROM product_specs")}
        except sqlite3.OperationalError:
            specs = {}
        result = []
        for page in pages:
            slug = normalize(page["url"].split("/es/", 1)[1].replace("-", " ").replace("/", " "))
            if not words or not all(any(t in slug for t in terms_for(word)) for word in words):
                continue
            title = page["url"].rstrip("/").rsplit("/", 1)[1].replace("-", " ").capitalize()
            result.append(print24_entry(db, page["configuration_id"], title, page["url"], page["fetched_at"],
                                        specs.get(page["url"], []), quantity, max_days))
            try:  # one-option-at-a-time variations, when the variants collector has been run
                extra = db.execute("""SELECT c.id, s.title, s.spec_json FROM configurations c
                                      JOIN products pr ON pr.id=c.product_id JOIN config_specs s ON s.configuration_id=c.id
                                      WHERE pr.source_id=? AND c.id<>? ORDER BY s.title""",
                                   (page["product_id"], page["configuration_id"])).fetchall()
            except sqlite3.OperationalError:
                extra = []
            for variant in extra:
                result.append(print24_entry(db, variant["id"], f"{title} · {variant['title']}", page["url"], page["fetched_at"],
                                            json.loads(variant["spec_json"]), quantity, max_days))
        return result
    finally:
        db.close()


def enrich_spec(spec: list, url: str) -> list:
    """Add format and printing read from the product's own address when its page lists them elsewhere
    (Onlineprinters writes `tarjetas-visita-4-4-90x50mm`: 4/4 inks, 9 x 5 cm)."""
    slug = url.rsplit("/", 1)[-1]
    groups = " ".join(normalize(x["group"]) for x in spec)
    extra = []
    size = re.search(r"(\d+)x(\d+)(?:-?mm)?", slug)
    if size and not any(k in groups for k in ("formato", "tamano")):
        extra.append({"group": "Formato", "label": f"{size.group(1)} × {size.group(2)} mm"})
    inks = re.search(r"-([04])-([04])-", slug)
    if inks and not any(k in groups for k in ("impresion", "caras")):
        sides = "una cara" if inks.group(2) == "0" else "dos caras"
        extra.append({"group": "Impresión", "label": f"{inks.group(1)}/{inks.group(2)} · color {sides}"})
    return extra + spec


def other_offers(catalog: Path | None, provider: str, words: list[str], quantity: int, max_days: int) -> list[dict]:
    """Prices read from public pages of the other providers (table supplier_offers). References, not equivalents.

    'unit' prices (TusKamisetas) become an estimated order total = unit price of the tier x quantity, garment
    only; 'total' prices (Onlineprinters, Printai) are used as published. Unknown delivery time stays unknown.
    """
    if catalog is None or not Path(catalog).exists():
        return []
    db = sqlite3.connect(f"file:{Path(catalog).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        try:
            rows = db.execute("SELECT * FROM supplier_offers WHERE provider=? ORDER BY product_name, group_label, variant, quantity", (provider,)).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        db.close()
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["product_url"], r["group_label"], r["variant"]), []).append(r)
    result = []
    for (url, group, variant), items in groups.items():
        slug = normalize(url.rsplit("/", 1)[-1].replace("-", " ") + " " + items[0]["product_name"] + " " + variant)
        if words and not all(any(t in slug for t in terms_for(word)) for word in words):
            continue
        first = items[0]
        unit = first["price_kind"] == "unit"
        offers = []
        for r in items:
            price = Decimal(r["price"])
            total = price * r["quantity"] if unit else price
            days = r["delivery_days"]
            offers.append({"quantity": r["quantity"], "delivery_type": "estimado" if unit else "estándar", "delivery_days": days,
                           "delivery_text": "", "product_net": str(total), "shipping_net": None if unit else "0",
                           "total_net": str(total), "total_gross": None, "unit_net": str(price if unit else total / r["quantity"]),
                           "meets_deadline": True if days is None else days <= max_days})
        eligible = [o for o in offers if o["quantity"] <= quantity] if unit else [o for o in offers if o["quantity"] == quantity]
        pick = max(eligible, key=lambda o: o["quantity"]) if (unit and eligible) else (eligible[0] if eligible else None)
        title = first["product_name"] + (f" · {variant}" if variant else "")
        result.append({"title": title, "url": url, "fetched_at": first["observed_at"], "spec": enrich_spec(json.loads(first["spec_json"]), url),
                       "offers": offers, "quantities": sorted({o["quantity"] for o in offers}), "price_kind": first["price_kind"],
                       "tax_status": first["tax_status"], "shipping": first["shipping"], "scope": first["scope"],
                       "matches_quantity": pick is not None, "suggested": pick})
    return result


SYNONYM_GROUPS = [{"flyer", "folleto", "octavilla"}, {"camiseta", "playera"}, {"pegatina", "adhesivo"}, {"cartel", "poster"},
                  {"taza", "mug"}, {"sudadera", "hoodie"}]
STOPWORDS = {"de", "del", "con", "para", "en", "y", "el", "la", "los", "las", "un", "una", "por", "a"}


def query_words(text: str) -> list[str]:
    """The words of a search without the little ones ('tarjetas de visita' -> tarjetas, visita)."""
    return [w for w in re.findall(r"\w+", normalize(text)) if w not in STOPWORDS]


def catalog_words(q: str) -> list[str]:
    """Words of a catalog search; '85 x 55' becomes 85x55 and '350 g/m2' or '350gr' becomes 350g, as the products are indexed."""
    def size(match):  # 8,5 x 5,5 cm and 85 x 55 mm are both 85x55 (the products are indexed in mm)
        w, h, unit = float(match.group(1)), float(match.group(2)), match.group(3)
        if unit == "cm" or max(w, h) < 20:
            w, h = w * 10, h * 10
        return f"{round(w)}x{round(h)}"

    text = normalize(q).replace(",", ".")
    text = re.sub(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)(?:\s*(mm|cm)\b)?", size, text)
    text = re.sub(r"(\d{2,4})\s*(?:g/m2|g/m²|gramos|gr\b|g\b)", r"\1g", text)
    return [w for w in re.findall(r"\w+", text) if w not in STOPWORDS | {"mm", "cm"}]


def terms_for(word: str) -> set[str]:
    """What a searched word may look like in a product name: singular/plural and a few real synonyms
    (flyer = folleto, camiseta = playera). Names are matched by containment, so 'flyer' also finds 'flyers'."""
    stems = {word}
    if len(word) > 5 and word.endswith("es"):
        stems |= {word[:-2], word[:-1]}
    elif len(word) > 3 and word.endswith("s"):
        stems.add(word[:-1])
    terms = set(stems)
    for group in SYNONYM_GROUPS:
        if stems & group:
            terms |= group
    return terms


def general_rank(link: dict, words: list[str]) -> tuple:
    """Sort key that puts the most general page first: its address says little more than what was searched
    (onlineprinters.es/k/tarjetas-visita before .../tarjetas-visita-plegados-formato-horizontal), category pages first."""
    path = urlsplit(link["url"]).path
    slug = [w for w in re.findall(r"[a-z0-9]+", normalize(path.rstrip("/").rsplit("/", 1)[-1])) if w not in STOPWORDS]
    extra = sum(1 for w in slug if not any(term in w for word in words for term in terms_for(word)))
    return (extra, 0 if re.search(r"/(k|c|categoria)/", path) else 1, len(slug))


def search(path: Path, seed: Path, brief: dict, selected: list[str], catalog_db: Path | None = None) -> dict:
    catalog = json.loads(seed.read_text(encoding="utf-8")) if seed.exists() else {"providers": {}}
    words = query_words(brief["query"])
    today = datetime.now(timezone.utc).date().isoformat()
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM supplier_quotes WHERE brief_hash=? ORDER BY id DESC", (signature(brief),)).fetchall()
    result = []
    for provider in PROVIDERS:
        if selected and provider["id"] not in selected:
            continue
        entry = catalog.get("providers", {}).get(provider["id"], {})
        hits = []
        for link in entry.get("links", []):
            text = normalize(link["title"] + " " + link["url"])
            if words and all(any(term in text for term in terms_for(word)) for word in words):
                hits.append(link)
        hits.sort(key=lambda link: general_rank(link, words))
        quotes = []
        latest_sources = set()
        for row in rows:
            if row["provider"] != provider["id"]:
                continue
            q = dict(row)
            superseded = q["source_url"] in latest_sources
            latest_sources.add(q["source_url"])
            total = None if q["shipping_net"] is None else sum((Decimal(q[k]) for k in ("product_net", "shipping_net", "additional_net")), Decimal(0))
            q.update(total_net=None if total is None else str(total),
                     unit_net=None if total is None else str(total / brief["quantity"]),
                     expired=q["valid_until"] < today, superseded=superseded,
                     meets_deadline=q["delivery_days"] <= brief["max_days"])
            quotes.append(q)
        eligible = [q for q in quotes if not q["superseded"] and not q["expired"] and q["meets_deadline"] and q["total_net"] is not None]
        best = min(eligible, key=lambda q: Decimal(q["total_net"])) if eligible else None
        auto = (auto_offers(catalog_db, set(), words, brief["quantity"], brief["max_days"]) if provider["id"] == "print24"
                else other_offers(catalog_db, provider["id"], words, brief["quantity"], brief["max_days"]))
        dropped = 0
        if brief.get("strict"):  # characteristics form: only products that meet every chosen characteristic
            if brief.get("generic"):
                from app.services.products import generic_matches
                kept = [e for e in auto if generic_matches(e, brief.get("filters") or {})]
            else:
                from app.services.cards import entry_matches
                kept = [e for e in auto if entry_matches(e, brief, provider["id"])]
            dropped, auto = len(auto) - len(kept), kept
        result.append({**provider, "auto": auto[:12], "auto_matched": len(auto), "auto_filtered_out": dropped, "links": hits[:30], "matched_links": len(hits),
                       "indexed_links": len(entry.get("links", [])), "indexed_at": entry.get("fetched_at"),
                       "index_status": entry.get("status", "not_indexed"), "quotes": quotes, "best": best})
    comparable = [p for p in result if p["best"] is not None]
    minimum = min((Decimal(p["best"]["total_net"]) for p in comparable), default=None)
    winners = [p["id"] for p in comparable if Decimal(p["best"]["total_net"]) == minimum] if len(comparable) >= 2 else []
    return {"providers": result, "winners": winners, "comparable_providers": len(comparable),
            "brief_hash": signature(brief), "currency": "EUR", "pricing_mode": "manual_public_quotes"}


def spec_days(spec: list) -> int | None:
    """Delivery or production time written in a page's spec ('8-9 días hábiles', '3/4 días laborables'): the longest figure."""
    for x in spec:
        name = normalize(x["group"])
        if name.startswith(("plazo", "entrega")) or "plazo de produccion" in name:
            numbers = [int(n) for n in re.findall(r"\d+", x["label"])]
            if numbers:
                return max(numbers)
    for x in spec:  # Printai writes it inside another label ('Ecosostenible - 3/4 días laborables de producción')
        match = re.search(r"(\d+)(?:\s*[-/]\s*(\d+))?\s*d[ií]as\s*(?:h[aá]biles|laborables)", x["label"], re.I)
        if match:
            return max(int(g) for g in match.groups() if g)
    return None


def catalog_listing(catalog: Path | None, provider: str | None = None, q: str = "", limit: int = 50, offset: int = 0, cards: dict | None = None, quantity: int | None = None, max_days: int | None = None,
                    seed: Path | None = None, sides: int | None = None) -> dict:
    """Everything collected, one row per product (or per variant), cheapest published price and quantity range."""
    empty = {"total": 0, "items": [], "counts": {p["id"]: 0 for p in PROVIDERS}}
    if catalog is None or not Path(catalog).exists():
        return empty
    db = sqlite3.connect(f"file:{Path(catalog).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    items = []
    try:
        try:
            specs = {r["url"]: json.loads(r["spec_json"]) for r in db.execute("SELECT * FROM product_specs")}
        except sqlite3.OperationalError:
            specs = {}
        try:
            for page in db.execute("SELECT * FROM product_pages WHERE status='ok' ORDER BY url"):
                raw = [(r["q"], Decimal(r["t"]), r["d"]) for r in db.execute(
                    """SELECT qt.value AS q, p.total_net AS t, p.delivery_days AS d FROM prices p JOIN quantities qt ON qt.id=p.quantity_id
                       WHERE p.configuration_id=?""", (page["configuration_id"],))]
                if not raw:
                    continue
                prices, tiers_days = [], {}
                for tier_qty in sorted({r[0] for r in raw}):
                    rows_q = [r for r in raw if r[0] == tier_qty]
                    best_q = min(rows_q, key=lambda r: r[1])
                    days = [int(r[2]) for r in rows_q if r[2] not in (None, "")]
                    prices.append((tier_qty, best_q[1]))
                    tiers_days[tier_qty] = [int(best_q[2]) if best_q[2] not in (None, "") else None, min(days) if days else None]
                try:
                    variants = db.execute("""SELECT count(*) FROM configurations c JOIN products pr ON pr.id=c.product_id
                                             JOIN config_specs s ON s.configuration_id=c.id WHERE pr.source_id=? AND c.id<>?""",
                                          (page["product_id"], page["configuration_id"])).fetchone()[0]
                except sqlite3.OperationalError:
                    variants = 0
                cheapest = min(prices, key=lambda x: x[1])
                items.append({"provider": "print24", "title": page["url"].rstrip("/").rsplit("/", 1)[1].replace("-", " ").capitalize(),
                              "url": page["url"], "price_kind": "total", "tax_status": "net", "shipping": "included", "comparable": True,
                              "scope": "configuración por defecto; el total incluye el envío de la opción más barata", "from_price": str(cheapest[1]), "from_quantity": cheapest[0],
                              "min_quantity": min(p[0] for p in prices), "max_quantity": max(p[0] for p in prices),
                              "tiers": len({p[0] for p in prices}), "variants": variants, "prices": [[q, str(t), *tiers_days[q]] for q, t in prices],
                              "observed_at": page["fetched_at"], "spec": specs.get(page["url"], [])})
        except sqlite3.OperationalError:
            pass
        try:
            groups: dict[tuple, list] = {}
            for r in db.execute("SELECT * FROM supplier_offers ORDER BY provider, product_name, group_label, variant, quantity"):
                groups.setdefault((r["provider"], r["product_url"], r["group_label"], r["variant"]), []).append(r)
            for (prov, url, group, variant), rows in groups.items():
                best = min(rows, key=lambda r: Decimal(r["price"]))
                items.append({"provider": prov, "title": rows[0]["product_name"] + (f" · {variant}" if variant else ""), "url": url,
                              "price_kind": rows[0]["price_kind"], "tax_status": rows[0]["tax_status"], "shipping": rows[0]["shipping"],
                              "scope": rows[0]["scope"], "comparable": "sin personalizar" not in normalize(rows[0]["scope"] or ""), "from_price": best["price"], "from_quantity": best["quantity"],
                              "min_quantity": min(r["quantity"] for r in rows), "max_quantity": max(r["quantity"] for r in rows),
                              "tiers": len(rows), "variants": 0, "observed_at": rows[0]["observed_at"], "prices": [[r["quantity"], r["price"], spec_days(json.loads(rows[0]["spec_json"])), spec_days(json.loads(rows[0]["spec_json"]))] for r in rows],
                              "spec": json.loads(rows[0]["spec_json"])})
        except sqlite3.OperationalError:
            pass
    finally:
        db.close()
    order = {p["id"]: i for i, p in enumerate(PROVIDERS)}
    names = {p["id"]: p["name"] for p in PROVIDERS}
    counts = {p["id"]: 0 for p in PROVIDERS}
    for item in items:
        counts[item["provider"]] = counts.get(item["provider"], 0) + 1
        item["provider_name"] = names.get(item["provider"], item["provider"])
    words = catalog_words(q)
    for item in items:
        if item["provider"] != "print24":
            item["spec"] = enrich_spec(item["spec"], item["url"])
    if cards is not None:  # business-card form: only business cards that meet every chosen characteristic
        from app.services.cards import entry_matches
        items = [i for i in items if (lambda t: "tarjeta" in t and "visita" in t)(normalize(i["title"] + " " + i["url"]))]
        for item in items:
            if item["provider"] != "print24":
                item["spec"] = enrich_spec(item["spec"], item["url"])
        items = [i for i in items if entry_matches(i, cards, i["provider"])]
    from app.services.compare import search_tokens
    chosen = []
    for item in items:
        if provider and item["provider"] != provider:
            continue
        haystack = normalize(item["title"] + " " + item["url"] + " " + " ".join(x["label"] for x in item["spec"]))
        extra = set(search_tokens(item).split()) if words else set()  # 85x55, a5, 350g: matched whole, never as part of other words
        if all(word in extra or any(t in haystack for t in terms_for(word)) for word in words):
            chosen.append(item)
    chosen.sort(key=lambda i: (order.get(i["provider"], 99), i["title"]))
    if sides:  # the customer asked for 1 or 2 printed sides: only pages that say exactly that
        from app.services.cards import sides_in
        from app.services.compare import item_text
        chosen = [i for i in chosen if sides_in(item_text(i)) == {sides}]
    if max_days:  # a page with no delivery time written cannot be said to arrive in time
        from app.services.compare import days_at
        chosen = [i for i in chosen if (d := days_at(i, quantity)[1]) is not None and d <= max_days]
    result = {"total": len(chosen), "items": chosen[offset:offset + limit], "counts": counts}
    if quantity and words:
        from app.services.compare import price_at
        for item in result["items"]:
            item["at"] = price_at(item, quantity)  # price at that quantity (exact, or estimated between two tiers)
    if words and seed is not None and cards is None and not max_days:
        result["unpriced"] = unpriced_pages(catalog, seed, words, provider, {i["url"] for i in items})
    if quantity and words:
        from app.services.compare import compare
        result["compare"] = compare([i for i in chosen if not provider or i["provider"] == provider], quantity)
    return result


def url_key(url: str) -> str:
    return url.strip().rstrip("/").lower()


def unpriced_pages(catalog: Path | None, seed: Path, words: list[str], provider: str | None, priced: set[str]) -> list[dict]:
    """Pages that match the search but have no price collected: those of the public link index and the ones whose
    price table could not be read (e.g. Printai's, behind a calculator its robots.txt forbids). Shown as links only."""
    names = {p["id"]: p["name"] for p in PROVIDERS}
    order = {p["id"]: i for i, p in enumerate(PROVIDERS)}
    seen = {url_key(u) for u in priced}
    found = []

    def add(prov: str, title: str, url: str):
        if re.fullmatch(r"[0-9a-f]{20,}", title.strip().lower()):  # Truyol ends addresses with a hash: use the product name before it
            title = url.rstrip("/").rsplit("/", 2)[-2].replace("-", " ").capitalize()
        text = normalize(title + " " + url)
        if (provider and prov != provider) or url_key(url) in seen or not all(any(t in text for t in terms_for(w)) for w in words):
            return
        seen.add(url_key(url))
        found.append({"provider": prov, "provider_name": names.get(prov, prov), "title": title, "url": url})

    if seed.exists():
        for prov, entry in json.loads(seed.read_text(encoding="utf-8")).get("providers", {}).items():
            for link in entry.get("links", []):
                add(prov, link["title"], link["url"])
    if catalog is not None and Path(catalog).exists():
        db = sqlite3.connect(f"file:{Path(catalog).as_posix()}?mode=ro", uri=True)
        try:
            for prov, url in db.execute("SELECT provider, url FROM supplier_pages WHERE status='failed' AND error NOT LIKE '%no longer available%'"):
                from urllib.parse import unquote
                add(prov, unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("-", " ").capitalize(), url)
        except sqlite3.OperationalError:
            pass
        finally:
            db.close()
    found.sort(key=lambda x: (order.get(x["provider"], 99), x["title"]))
    return found[:400]


def general_links(seed: Path, q: str) -> dict:
    """For each provider, its most general page for the searched product (from the public link index), or None."""
    words = query_words(q)
    found = {p["id"]: None for p in PROVIDERS}
    if not words or not seed.exists():
        return found
    catalog = json.loads(seed.read_text(encoding="utf-8")).get("providers", {})
    for provider in PROVIDERS:
        hits = [link for link in catalog.get(provider["id"], {}).get("links", [])
                if all(any(t in normalize(link["title"] + " " + link["url"]) for t in terms_for(w)) for w in words)]
        if hits:
            best = min(hits, key=lambda link: general_rank(link, words))
            found[provider["id"]] = {"url": best["url"], "title": best["title"]}
    return found


SUGGEST_TERMS = ["tarjetas de visita", "flyers", "folletos", "carteles", "camisetas", "sudaderas", "bolsas", "tazas", "pegatinas", "sobres",
                 "carpetas", "catálogos", "revistas", "calendarios", "lonas", "banners", "roll-up", "etiquetas", "posavasos", "gorras",
                 "delantales", "bolígrafos", "tarjetas postales", "invitaciones"]


def suggestions(catalog: Path | None, seed: Path) -> list[dict]:
    """Products worth typing: the usual terms that match something we have, with how many pages match."""
    texts = [normalize(i["title"] + " " + i["url"]) for i in catalog_listing(catalog, None, "", 100000)["items"]]
    if seed.exists():
        for entry in json.loads(seed.read_text(encoding="utf-8")).get("providers", {}).values():
            texts += [normalize(link["title"] + " " + link["url"]) for link in entry.get("links", [])]
    found = []
    for term in SUGGEST_TERMS:
        words = query_words(term)
        count = sum(1 for t in texts if all(any(x in t for x in terms_for(w)) for w in words))
        if count:
            found.append({"term": term, "count": count})
    return sorted(found, key=lambda x: -x["count"])
