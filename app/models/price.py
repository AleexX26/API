from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Price:
    quantity_id: str
    quantity_value: int
    delivery_type: str
    delivery_days: str
    delivery_text: str
    product_net: Decimal
    total_net: Decimal
    total_gross: Decimal
    shipping_net: Decimal
    total_vat: Decimal
    # Unknown: the supplied field list contains no shipping VAT breakdown.
    shipping_gross: Decimal | None = None

    @property
    def unit_product_net(self) -> Decimal:
        """Product net per physical unit, excluding shipping; no currency rounding."""
        return self.product_net / self.quantity_value
