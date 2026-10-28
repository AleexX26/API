"""Characteristics form for any product (flyers, bags, shirts…), built from what was collected for it.

The groups and options are the ones the collected pages state (their spec), joined across providers, plus every option
of Print24's configurator when its page is in the cache. A product passes the filter only if its page states the
chosen option; Print24 only has prices for the default configuration of each page, so other options find nothing.
"""
import re
from functools import lru_cache
from pathlib import Path

from app.parsers.price_matrix import MatrixError
from app.parsers.product_page import calculation_data
from app.services.cards import clean, grams_in, inks_in, paper_key, sides_in, sizes_in
from app.services.workbench import catalog_listing, enrich_spec, normalize

MAX_GROUPS, MAX_OPTIONS = 16, 80
# Print24 configurator box -> group name, the same names its collected specs use
BOX_GROUPS = {"seiten": "Páginas", "format": "Formato", "aspect_ratio": "Orientación", "papier": "Papel", "farben": "Impresión",
              "verarbeitung": "Procesamiento", "finishing": "Acabados", "Perforation": "Perforación", "Nutung": "Hendido",
              "proofformat": "Prueba", "individualization": "Individualización", "motive": "Diseños", "packing": "Empaquetado"}
ALIASES = {"formato": "Formato", "tamano": "Formato", "medidas": "Formato", "papel": "Papel", "material": "Papel", "soporte": "Papel",
           "impresion": "Impresión", "caras impresion": "Impresión", "paginas": "Páginas", "numero de paginas": "Páginas",
           "acabados": "Acabados", "laminado": "Acabados", "tratamiento posterior": "Acabados", "golpe seco": "Acabados",
           "barniz 3d selectivo": "Acabados", "orientacion": "Orientación", "prueba": "Prueba", "disenos": "Diseños",
           "empaquetado": "Empaquetado", "procesamiento": "Procesamiento", "individualizacion": "Individualización",
           "elige el papel": "Papel", "prueba digital": "Prueba", "metodo de impresion": "Impresión", "realizacion": "Acabados"}
# groups that say nothing about the product itself (checks, delivery time, grouping): not offered as a dropdown
HIDDEN_GROUPS = {"comprobacion de datos", "revision de tu diseno", "agrupacion", "plazo de produccion", "plazo de entrega", "entrega",
                 "envio", "tirada por version", "disenos", "motivos", "accesorios"}


PREFIX_ALIASES = (("caras impresion", "Impresión"), ("tamano", "Formato"), ("formato", "Formato"), ("tipo estucado", "Papel"), ("gramaje", "Papel"),
                  ("papel", "Papel"), ("plastificado", "Acabados"), ("acabado", "Acabados"), ("laminado", "Acabados"), ("barniz", "Acabados"))


def group_name(raw: str) -> str:
    name = normalize(raw)
    if name in ALIASES:
        return ALIASES[name]
    return next((target for prefix, target in PREFIX_ALIASES if name.startswith(prefix)), raw.strip())


DIN = {"a3": (297, 420), "a4": (210, 297), "a5": (148, 210), "a6": (105, 148), "a7": (74, 105), "a8": (52, 74), "dl": (100, 210)}


def tokens(group: str, label: str) -> set:
    """What two labels of the same group must share to count as the same option (sizes, paper, inks, sides, or the text)."""
    text = normalize(label)
    if group == "Formato":
        sizes = sizes_in(text)
        for name in re.findall(r"\b(a[3-8]|dl)\b", text):  # A5, DIN A5 and 148 x 210 mm are the same size
            sizes |= {DIN[name], DIN[name][::-1]}
        if sizes:
            return {("size", s) for s in sizes}
    if group == "Papel" and grams_in(text):
        return {("paper", paper_key(label))}
    if group == "Impresión" and (inks := inks_in(text)):
        return {("ink", i) for i in inks}
    if group == "Páginas" and (sides := sides_in(text)):
        return {("side", s) for s in sides}
    return {("text", clean(label))}


def shown(group: str, label: str) -> str:
    """The label without a trailing '(…)' that only repeats it (Onlineprinters writes '8,5 x 5,5 cm (8,5 x 5,5 cm)')."""
    label = label.strip()
    return re.sub(r"\s*\(([^()]*)\)$", lambda m: "" if normalize(m.group(1)) == normalize(label[:m.start()]) else m.group(0), label)


@lru_cache(maxsize=64)
def box_options(path: str, mtime: float) -> dict:
    try:
        boxes = calculation_data(Path(path).read_text(encoding="utf-8"))["itemMaster"]["boxes"]
    except (OSError, MatrixError, KeyError, TypeError):
        return {}
    found: dict[str, list] = {}
    for box in boxes:
        group = BOX_GROUPS.get(box["propGroupName"])
        if group and not box.get("hide"):
            for prop in box["properties"]:
                label = " ".join(part.strip() for part in prop["propertyTranslated"] if part and part.strip())
                if label:
                    found.setdefault(group, []).append(label)
    return found


def entries(catalog: Path | None, query: str) -> list[dict]:
    items = catalog_listing(catalog, None, query, 100000)["items"]
    for item in items:
        if item["provider"] != "print24":
            item["spec"] = enrich_spec(item["spec"], item["url"])
    return items


def product_form(catalog: Path | None, query: str) -> dict:
    """Groups and options for the products matching the query: {"matched": n, "groups": [{"name", "options"}]}."""
    items = entries(catalog, query)
    groups: dict[str, dict] = {}  # name -> {"seen": set of tokens, "options": [labels], "count": products stating it}

    def add(group: str, label: str):
        slot = groups.setdefault(group, {"seen": set(), "options": [], "count": 0})
        tok = tokens(group, label)
        if tok & slot["seen"] or not clean(label):
            return
        slot["seen"] |= tok
        slot["options"].append(shown(group, label))

    if catalog is not None:
        cache = Path(catalog).parent / "cache/products"
        for item in [i for i in items if i["provider"] == "print24"][:8]:
            page = cache / (item["url"].split("/es/", 1)[-1].strip("/").replace("/", "__") + ".html")
            if page.exists():
                for group, labels in box_options(str(page), page.stat().st_mtime).items():
                    for label in labels:
                        add(group, label)
    for item in items:
        for group in {group_name(x["group"]) for x in item["spec"]}:
            groups.setdefault(group, {"seen": set(), "options": [], "count": 0})["count"] += 1
        for x in item["spec"]:
            add(group_name(x["group"]), x["label"])
    def useful(name: str, options: list[str]) -> bool:
        if normalize(name) in HIDDEN_GROUPS or not options:
            return False
        return not all(normalize(o).startswith(("sin ", "no ", "ninguno")) for o in options)  # only 'sin acabado' etc.: nothing to choose

    ranked = [kv for kv in sorted(groups.items(), key=lambda kv: (-kv[1]["count"], kv[0])) if useful(kv[0], kv[1]["options"])][:MAX_GROUPS]
    return {"matched": len(items), "groups": [{"name": name, "options": slot["options"][:MAX_OPTIONS]} for name, slot in ranked]}


def generic_matches(entry: dict, filters: dict) -> bool:
    """True when the product states every chosen option (group name -> option label)."""
    by_group: dict[str, list] = {}
    for x in entry["spec"]:
        by_group.setdefault(group_name(x["group"]), []).append(x["label"])
    for group, wanted in filters.items():
        want = tokens(group, wanted)
        if not any(tokens(group, label) & want for label in by_group.get(group, [])):
            return False
    return True
