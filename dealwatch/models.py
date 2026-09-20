from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def today() -> date:
    return datetime.now(ZoneInfo("America/Toronto")).date()


def amount(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Amounts must be finite non-negative numbers") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Amounts must be finite non-negative numbers")
    return result


@dataclass(frozen=True)
class Promo:
    code: str
    app: str
    discount_type: str
    value: str
    minimum_order: str | None
    expires: str | None
    region: str
    observed_on: str
    source_url: str
    status: str = "unverified"
    cap: str | None = None
    starts: str | None = None
    new_customer_only: bool = False
    restaurants: tuple[str, ...] = ()
    terms: str = ""

    def __post_init__(self):
        if self.discount_type not in {"fixed", "percent", "free_delivery"}:
            raise ValueError("Unknown discount type")
        if self.status not in {"documented", "unverified"}:
            raise ValueError("Unknown promo status")
        if not self.code or not self.source_url.startswith("https://"):
            raise ValueError("Promo requires a code and HTTPS citation")
        amount(self.value)
        if self.discount_type == "percent" and amount(self.value) > 100:
            raise ValueError("Percentage cannot exceed 100")
        for value in (self.minimum_order, self.cap):
            if value is not None:
                amount(value)
        for value in (self.expires, self.starts, self.observed_on):
            if value is not None:
                date.fromisoformat(value)

    def exclusion(self, subtotal, restaurant, new_customer, on, max_age) -> str | None:
        if self.status != "documented":
            return "unverified terms/region; excluded"
        if self.region not in {"CA", "CA-ON", "Toronto"}:
            return "not valid in Toronto"
        age = (on - date.fromisoformat(self.observed_on)).days
        if age < 0 or age > max_age:
            return "stale or future observation; refresh required"
        if self.expires is None:
            return "expiry unknown"
        if on > date.fromisoformat(self.expires):
            return "expired"
        if self.starts and on < date.fromisoformat(self.starts):
            return "not started"
        if self.minimum_order is None:
            return "minimum order unknown"
        if subtotal < amount(self.minimum_order):
            return f"requires ${amount(self.minimum_order):.2f} food subtotal"
        if self.new_customer_only and not new_customer:
            return "first-time customers only"
        if self.restaurants and restaurant.casefold().strip() not in {r.casefold() for r in self.restaurants}:
            return "restricted to other restaurants"
        return None
