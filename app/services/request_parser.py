"""Reads what a customer wrote ("necesito 500 tarjetas de visita 85x55 en cartulina de 350 g por las dos caras")
and turns it into what the catalog needs: product words, quantity, sides and a delivery limit.

Plain rules, no external service: the text never leaves this PC. It understands the usual Spanish ways of asking;
whatever it cannot understand is left out and shown to the user, who can edit the search.
"""
import re

from app.services.workbench import SUGGEST_TERMS, normalize

# product word (as written, normalized) -> term used to search the catalog
PRODUCTS = {
    "tarjetas de visita": "tarjetas de visita", "tarjeta de visita": "tarjetas de visita", "tarjetas visita": "tarjetas de visita",
    "tarjetas de presentacion": "tarjetas de visita", "tarjetas postales": "tarjetas postales", "postales": "tarjetas postales",
    "flyers": "flyers", "flyer": "flyers", "folletos": "folletos", "folleto": "folletos", "octavillas": "flyers", "dipticos": "folletos",
    "diptico": "folletos", "tripticos": "folletos", "triptico": "folletos",
    "carteles": "carteles", "cartel": "carteles", "posters": "carteles", "poster": "carteles",
    "camisetas": "camisetas", "camiseta": "camisetas", "sudaderas": "sudaderas", "sudadera": "sudaderas",
    "bolsas": "bolsas", "bolsa": "bolsas", "tazas": "tazas", "taza": "tazas", "pegatinas": "pegatinas", "pegatina": "pegatinas",
    "adhesivos": "pegatinas", "etiquetas": "etiquetas", "etiqueta": "etiquetas", "sobres": "sobres", "sobre": "sobres",
    "carpetas": "carpetas", "carpeta": "carpetas", "catalogos": "catálogos", "catalogo": "catálogos", "revistas": "revistas",
    "calendarios": "calendarios", "calendario": "calendarios", "lonas": "lonas", "lona": "lonas", "banners": "banners",
    "roll-up": "roll-up", "rollup": "roll-up", "roll up": "roll-up", "gorras": "gorras", "gorra": "gorras",
    "invitaciones": "invitaciones", "invitacion": "invitaciones", "delantales": "delantales", "bolígrafos": "bolígrafos",
    "boligrafos": "bolígrafos", "posavasos": "posavasos",
}
FINISHES = {"plastificado": "plastificado", "plastificadas": "plastificado", "plastificada": "plastificado", "laminado": "laminado",
            "barniz": "barniz", "barnizado": "barniz", "relieve": "relieve", "soft touch": "soft touch", "mate": "mate", "brillo": "brillo",
            "brillante": "brillo", "estucado": "estucado", "reciclado": "reciclado", "kraft": "kraft", "pantone": "pantone"}
SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)?")
DIN = re.compile(r"\b(?:din\s*)?(a[3-8]|dl)\b")
GRAMS = re.compile(r"(\d{2,4})\s*(?:g/m2|g/m²|gramos|gr|g)\b")
DAYS = re.compile(r"(?:en|maximo|max|hasta|antes de)\s*(\d{1,3})\s*dias")
TWO_SIDES = re.compile(r"\b(dos caras|2 caras|ambas caras|doble cara|por las dos caras|por ambos lados|4/4|4\+4|anverso y reverso|por los dos lados)\b")
ONE_SIDE = re.compile(r"\b(una cara|1 cara|una sola cara|solo anverso|4/0|4\+0|solo por delante)\b")
QTY_UNITS = r"(?:uds?\.?|unidades|ejemplares|piezas|copias)"


def clean_number(raw: str) -> int | None:
    digits = raw.replace(".", "").replace(",", "")  # 1.000 -> 1000
    return int(digits) if digits.isdigit() and 0 < int(digits) <= 1_000_000 else None


def split_items(text: str) -> list[str]:
    """One piece of text per product asked: by lines and ';', and inside a line before each 'number + product' after the first."""
    pieces = []
    for line in re.split(r"[\n;]+", text):
        line = line.strip()
        if not line:
            continue
        norm = normalize(line)
        starts = []
        for word in sorted(PRODUCTS, key=len, reverse=True):
            for match in re.finditer(r"\b" + re.escape(word) + r"\b", norm):
                if not any(s <= match.start() < e for s, e in starts):
                    starts.append((match.start(), match.end()))
        starts.sort()
        if len(starts) < 2 or len({PRODUCTS[norm[s:e]] for s, e in starts}) < 2:
            pieces.append(line)
            continue
        cuts = [0]
        for s, _ in starts[1:]:
            before = re.search(r"(\d[\d.,]*)\s*(?:" + QTY_UNITS + r")?\s*(?:de\s+)?$", norm[:s])
            cuts.append(before.start() if before and s - before.start() < 20 else s)
        cuts.append(len(line))
        pieces += [line[a:b].strip(" ,.y") for a, b in zip(cuts, cuts[1:]) if line[a:b].strip(" ,.y")]
    return pieces or [text.strip()]


def parse_one(piece: str) -> dict | None:
    text = normalize(piece).replace("’", "'")
    product = next((PRODUCTS[w] for w in sorted(PRODUCTS, key=len, reverse=True) if re.search(r"\b" + re.escape(w) + r"\b", text)), None)
    if product is None:
        return None
    rest = text
    words = [product]
    understood = []

    size = SIZE.search(rest)
    size_text = None
    if size:
        size_text = size.group(0).strip()
        words.append(size_text)
        understood.append(f"tamaño {size_text}")
        rest = rest.replace(size.group(0), " ")
    elif (din := DIN.search(rest)):
        size_text = din.group(1).upper()
        words.append(din.group(1))
        understood.append(f"tamaño {size_text}")
        rest = rest.replace(din.group(0), " ")

    grams = GRAMS.search(rest)
    if grams:
        words.append(f"{grams.group(1)}g")
        understood.append(f"{grams.group(1)} g/m²")
        rest = rest.replace(grams.group(0), " ")

    max_days = None
    if (days := DAYS.search(rest)):
        max_days = int(days.group(1))
        understood.append(f"entrega en {max_days} días como máximo")
        rest = rest.replace(days.group(0), " ")

    sides = 2 if TWO_SIDES.search(rest) else 1 if ONE_SIDE.search(rest) else None
    if sides:
        understood.append("las dos caras" if sides == 2 else "una cara")
        rest = (TWO_SIDES if sides == 2 else ONE_SIDE).sub(" ", rest)

    finishes = []
    for word, term in FINISHES.items():
        if re.search(r"\b" + re.escape(word) + r"\b", rest) and term not in finishes:
            finishes.append(term)
    if finishes:  # a preference, not a search word: pages rarely name every finish, so it is shown but does not empty the results
        understood.append("acabado " + ", ".join(finishes) + " (compruébalo en cada ficha)")

    quantity = None
    near = re.search(r"(\d[\d.,]*)\s*" + QTY_UNITS + r"?\s*(?:de\s+)?(?:" + "|".join(re.escape(w) for w in PRODUCTS) + r")\b", rest)
    if near:
        quantity = clean_number(near.group(1))
    if quantity is None and (units := re.search(r"(\d[\d.,]*)\s*" + QTY_UNITS + r"\b", rest)):
        quantity = clean_number(units.group(1))
    if quantity is None:
        numbers = [n for n in (clean_number(m) for m in re.findall(r"\d[\d.,]*", rest)) if n]
        quantity = numbers[0] if numbers else None
    if quantity:
        understood.insert(0, f"{quantity} uds.")

    return {"text": piece.strip(), "product": product, "query": " ".join(words), "quantity": quantity, "sides": sides, "max_days": max_days, "finishes": finishes,
            "understood": f"{product} · " + " · ".join(understood) if understood else product}


def parse_request(text: str) -> list[dict]:
    """The products asked for in a customer's text, each with what could be understood (quantity may be None)."""
    return [item for piece in split_items(text) if (item := parse_one(piece))]


