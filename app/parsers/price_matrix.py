"""Strict offline parser for the field paths reported by the user.

The array envelope is provisional until checked against a complete real capture.
Unknown fields are tolerated; absent/invalid known fields fail the whole batch.
"""
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.price import Price


class MatrixError(ValueError):
    pass


def identifier(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise MatrixError("Expected nonempty string or integer identifier")
    return str(value)


def amount(value: Any) -> Decimal:
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise MatrixError("Money must be a decimal string, integer or Decimal; never float")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise MatrixError("Invalid decimal amount") from exc
    if not result.is_finite() or result < 0:
        raise MatrixError("Money must be finite and nonnegative")
    return result


ES_MONEY = re.compile(r"^(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s?€$")


def es_money(value: Any) -> Decimal:
    """Parse a formatted Spanish amount such as '1.234,56 €' (the only form some fields have)."""
    match = ES_MONEY.match(value.replace(" ", " ").strip()) if isinstance(value, str) else None
    if not match:
        raise MatrixError("Unrecognised formatted amount")
    return Decimal(match.group(1).replace(".", "") + "." + match.group(2))


def money_field(final: dict, name: str) -> Decimal | None:
    """Numeric `<name>_value` if present, else a plain decimal `<name>`, else formatted text."""
    if f"{name}_value" in final:
        return amount(final[f"{name}_value"])
    if name not in final:
        return None
    value = final[name]
    return es_money(value) if isinstance(value, str) and "€" in value else amount(value)


def parse_matrix(raw: str) -> list[Price]:
    try:
        data = json.loads(raw, parse_float=Decimal,
                          parse_constant=lambda _: (_ for _ in ()).throw(MatrixError("Nonfinite JSON")))
    except json.JSONDecodeError as exc:
        raise MatrixError("Invalid JSON") from exc
    if not isinstance(data, list) or not data:
        raise MatrixError("Expected a nonempty price-matrix array")
    result: list[Price] = []
    seen: set[tuple[str, str]] = set()
    quantities: dict[str, int] = {}
    for index, row in enumerate(data):
        try:
            qid = identifier(row["quantity"]["id"])
            # Real public pages nest the offers in quantity; the first reported shape had them on the row.
            shipping = row["quantity"].get("shipping_type", row.get("shipping_type"))
            if not isinstance(shipping, list) or not shipping:
                raise MatrixError("Expected nonempty shipping_type array")
            for offer in shipping:
                price = offer["price"]
                q = amount(price["quantity_value"])
                if q <= 0 or q != q.to_integral_value():
                    raise MatrixError("quantity_value must be a positive integer")
                if qid in quantities and quantities[qid] != int(q):
                    raise MatrixError("Conflicting quantity values for the same ID")
                quantities[qid] = int(q)
                final = price["final_prices"]
                kind = identifier(offer["delivery_type"])
                key = (qid, kind)
                if key in seen:
                    raise MatrixError("Duplicate quantity/delivery offer")
                seen.add(key)
                days = identifier(offer["delivery_days"])
                label = offer.get("delivery_text_translated", "")  # absent on the public product page
                if not isinstance(label, str):
                    raise MatrixError("Expected translated delivery text")
                product_net = amount(final["product_net_value"])
                total_net = amount(final["total_net_value"])
                shipping_net = money_field(final, "shipping_net")
                if shipping_net is None:
                    raise MatrixError("shipping_net missing")
                if shipping_net != total_net - product_net:
                    raise MatrixError("shipping_net does not equal total_net - product_net")
                vat = money_field(final, "total_vat")
                if vat is None:
                    raise MatrixError("total_vat missing")
                parsed = Price(qid, int(q), kind, days, label, product_net, total_net,
                               amount(final["total_gross_value"]), shipping_net, vat)
                if abs(parsed.total_net + parsed.total_vat - parsed.total_gross) > Decimal("0.01"):
                    raise MatrixError("Inconsistent net + VAT versus gross (tolerance 0.01)")
                result.append(parsed)
        except (KeyError, TypeError, MatrixError) as exc:
            raise MatrixError(f"row[{index}]: {exc}") from exc
    return result
