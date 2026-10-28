"""Business-card form modelled on Print24's configurator, and the matching of products against it.

The option lists come from the Print24 page already in the cache (no new requests). Print24 only has prices for
the default configuration of each page we collected, so a filter that asks for another option finds no price.
"""
import json
import re
import sqlite3
from pathlib import Path

from app.parsers.price_matrix import MatrixError
from app.parsers.product_page import calculation_data
from app.services.workbench import enrich_spec, normalize

CARD_CACHE = "cache/products/productos-impresion__tarjetas-de-visita.html"
PRINT24_GROUPS = {"seiten": "pages", "format": "format", "aspect_ratio": "orientation", "papier": "paper",
                  "farben": "inks", "verarbeitung": "processing", "finishing": "finishing", "proofformat": "proof",
                  "quantity": "quantity", "individualization": "individualization", "motive": "designs", "packing": "packing"}
PRINT24_ONLY = ("proof", "individualization", "designs", "packing")  # concepts the other providers do not have
CARD_KEYS = {"type", "pages", "orientation", "processing", *PRINT24_ONLY}

# Kind of card -> words that show it in a product's name or spec. [] = the plain card (none of the others).
CARD_TYPES = {"Estándar": [], "Exclusiva": ["exclusiv"], "Ecológica": ["ecolog", "greenline", "green line"],
              "Multiloft / Luxecore (grueso)": ["multiloft", "luxecore"], "Pack múltiple": ["pack"],
              "Contracolada": ["contracolad"], "Plegada": ["plegad", "plegable"], "NFC": ["nfc"],
              "Plástico / PVC": ["pvc", "plastico"]}
FINISH_TERMS = {"barniz": ["barniz", "lacado"], "relieve": ["relieve", "golpe seco"],
                "plastific": ["plastific", "laminado"], "laminado en caliente": ["caliente", "stamping", "foil"]}
PAPER_FAMILIES = {"estucado": ["estucado", "cuche", "couche"], "offset": ["offset"], "carton": ["carton"],
                  "reciclado": ["reciclad", "ecolog"], "noble": ["noble", "rococo", "gmund"], "luxecore": ["luxecore"],
                  "kraft": ["kraft"], "hierba": ["hierba"], "natural": ["natural"]}
SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)?")
NEGATED = re.compile(r"\bsin (?:propiedad de |acabados?|laminado|plastificado|barniz\w*|relieve|redondeo(?: de esquinas)?)")


def card_form(catalog: Path | None) -> dict:
    """Option lists of Print24's business-card configurator, keyed as the web form needs them."""
    form = {key: [] for key in PRINT24_GROUPS.values()}
    cache = Path(catalog).parent / CARD_CACHE if catalog is not None else None
    if cache is not None and cache.exists():
        try:
            boxes = calculation_data(cache.read_text(encoding="utf-8"))["itemMaster"]["boxes"]
        except (OSError, MatrixError, KeyError, TypeError):
            boxes = []
        for box in boxes:
            key = PRINT24_GROUPS.get(box["propGroupName"])
            if key and not box.get("hide"):
                for prop in box["properties"]:
                    label = " ".join(part.strip() for part in prop["propertyTranslated"] if part and part.strip())
                    if label and label not in form[key]:
                        form[key].append(label)
    add_other_providers(catalog, form)
    return {"types": list(CARD_TYPES), **form}


FAMILY_LABEL = {"estucado": "Papel estucado", "offset": "Offset", "carton": "Cartón", "reciclado": "Reciclado", "noble": "Papel noble",
                "luxecore": "Luxecore", "kraft": "Papel kraft", "hierba": "Papel de hierba", "natural": "Papel natural"}


def paper_key(label: str) -> tuple:
    text = normalize(label)
    grams = tuple(sorted(grams_in(text)))
    family = next((f for f, terms in PAPER_FAMILIES.items() if any(t in text for t in terms)), "")
    return (grams, family) if grams else ((), text)


def other_cards(catalog: Path | None) -> list[dict]:
    """The business cards collected from the providers other than Print24: url, spec (with format/printing read from
    the address) and the quantities that have a price."""
    if catalog is None or not Path(catalog).exists():
        return []
    db = sqlite3.connect(f"file:{Path(catalog).as_posix()}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT product_url, product_name, spec_json, group_concat(DISTINCT quantity) FROM supplier_offers GROUP BY product_url").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()
    found = []
    for url, name, spec, quantities in rows:
        text = normalize(f"{name} {url}")
        if "tarjeta" in text and "visita" in text:
            found.append({"spec": enrich_spec(json.loads(spec), url), "quantities": [int(q) for q in str(quantities).split(",") if q]})
    return found


def add_other_providers(catalog: Path | None, form: dict) -> None:
    """Add to Print24's option lists what the other providers' business cards offer (sizes, papers, inks, quantities)."""
    cards = other_cards(catalog)
    for card in cards:
        for item in card["spec"]:
            group, label = normalize(item["group"]), item["label"].strip()
            if group in ("formato", "tamano"):
                for w, h in sorted(sizes_in(label), key=lambda s: -s[0])[:1]:
                    if not any(sizes_in(x) & {(w, h)} for x in form["format"]):
                        form["format"].append(f"{w} x {h} mm")
            elif group in ("papel", "material"):
                key = paper_key(label)
                if not any(paper_key(x) == key for x in form["paper"]):
                    grams, family = key if key[0] else ((), "")
                    form["paper"].append(f"{grams[0]} g/m² {FAMILY_LABEL[family]}" if grams and family else label)
            elif group in ("impresion", "caras impresion"):
                for pair in sorted(inks_in(normalize(label))):
                    if not any(pair in inks_in(x) for x in form["inks"]):
                        form["inks"].append(f"{pair} tintas (CMYK)")
    have = {int(m.group(1)) for x in form["quantity"] if (m := re.match(r"(\d+)", x))}
    for card in cards:
        have |= set(card["quantities"])
    form["quantity"] = [f"{n} Unidad" + ("" if n == 1 else "es") for n in sorted(have)]


def sizes_in(text: str) -> set[tuple[int, int]]:
    """Every 'W x H' in the text, in mm and in both orders (8,5x5,5cm and 85 x 55 mm are the same size)."""
    found = set()
    for a, b, unit in SIZE.findall(text.replace("×", "x")):
        w, h = float(a.replace(",", ".")), float(b.replace(",", "."))
        if unit == "cm" or max(w, h) < 20:
            w, h = w * 10, h * 10
        found |= {(round(w), round(h)), (round(h), round(w))}
    return found


def inks_in(text: str) -> set[str]:
    return {f"{a}+{b}" for a, b in re.findall(r"\b(\d)\s*[+/]\s*(\d)\b", text)}


def sides_in(text: str) -> set[int]:
    found = set()
    if re.search(r"\b(1 cara|una cara)\b|\b\d[+/]0\b", text):
        found.add(1)
    if re.search(r"\b(2 caras|dos caras)\b|\b\d[+/][1-9]\b", text):
        found.add(2)
    return found


def grams_in(text: str) -> set[str]:
    return set(re.findall(r"(\d{2,4})\s*(?:g/m|gr\b|g\b)", text))


def clean(value: str) -> str:
    return normalize(re.sub(r"\s*\([^)]*\)\s*$", "", value or ""))


def entry_matches(entry: dict, brief: dict, provider: str = "") -> bool:
    """True when the product shows everything chosen in the business-card form.

    A page that does not say it fails. Prueba, diseños and packing only exist at Print24, so they are not asked
    of the other providers.
    """
    items = [(normalize(x["group"]), normalize(x["label"])) for x in entry["spec"]]
    head = normalize(entry["url"].rsplit("/", 1)[-1].replace("-", " ") + " " + entry["title"])
    everything = head + " | " + " | ".join(f"{g}: {l}" for g, l in items)
    joined = " | ".join(f"{g}: {clean(l)} | {clean(l)}" for g, l in items)
    extras = brief.get("extras") or {}

    def chosen(key):
        value = clean(brief.get(key) or "")
        return "" if value in ("", "sin especificar") else value

    if (want := chosen("format")):
        wanted = sizes_in(want)
        if not (wanted & sizes_in(everything) if wanted else want in everything):
            return False

    if (want := chosen("material")):
        wanted_grams = grams_in(want)
        if wanted_grams:
            if not wanted_grams <= grams_in(everything):
                return False
            for family, terms in PAPER_FAMILIES.items():
                if family in want and not any(t in everything for t in terms):
                    return False
        elif want not in joined:
            return False

    if (want := chosen("printing")):
        pairs = inks_in(want)
        have = inks_in(everything)
        if pairs and have:
            if not pairs <= have:
                return False
        elif pairs:  # the page gives sides but not inks: accept only plain full colour on the same sides
            sides = {1} if all(p.endswith("+0") for p in pairs) else {2}
            if "cmyk" not in want or not (sides & sides_in(everything)):
                return False
        elif want not in joined:
            return False
        if any(word in want for word in ("pantone", "oro", "plata")) and not any(w in everything for w in ("pantone", "oro", "plata")):
            return False

    if (pages := clean(extras.get("pages", ""))):
        wanted = sides_in(pages)
        if not (wanted <= sides_in(everything) if wanted else pages in everything):
            return False

    if (orientation := normalize(extras.get("orientation", ""))):
        terms = ["vertical"] if orientation == "vertical" else ["horizontal", "apaisad"]
        if not any(t in everything for t in terms):
            return False

    stripped = NEGATED.sub("", everything)
    if (processing := normalize(extras.get("processing", ""))):
        rounded = "redonde" in stripped
        if ("redonde" in processing) != rounded:
            return False

    if (finishing := chosen("finishing")):
        if finishing == "sin":
            if any(t in stripped for terms in FINISH_TERMS.values() for t in terms):
                return False
        else:
            terms = next((v for k, v in FINISH_TERMS.items() if finishing.startswith(k)), [finishing])
            if not any(t in stripped for t in terms):
                return False

    if (kind := extras.get("type", "")) in CARD_TYPES:
        terms = CARD_TYPES[kind]
        if terms and not any(t in everything for t in terms):
            return False
        if not terms and any(t in everything for other in CARD_TYPES.values() for t in other):
            return False

    if provider == "print24":
        for key in PRINT24_ONLY:
            if (want := clean(extras.get(key, ""))) and want not in joined:
                return False
    return True
