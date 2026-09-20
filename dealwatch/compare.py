from dataclasses import dataclass
from decimal import Decimal

from . import fees
from .fees import money
from .models import Promo, amount, today

D = Decimal


@dataclass(frozen=True)
class Estimate:
    app: str
    name: str
    subtotal: D
    service: D
    small_order: D
    delivery: D
    discount: D
    tax: D
    tip: D
    total: D
    low: D
    high: D
    promo: Promo | None
    excluded: tuple[str, ...]


def compare(restaurant, order_total, promos=(), *, new_customer_apps=(), tip="0", on=None, fee_model=None,
            distance_km=None):
    subtotal, tip = money(amount(order_total)), money(amount(tip))
    if subtotal <= 0:
        raise ValueError("Order total must be greater than zero")
    if not restaurant.strip():
        raise ValueError("Restaurant/dish must not be empty")
    if distance_km is not None:
        try:
            distance_km = float(distance_km)
        except (TypeError, ValueError):
            raise ValueError("distance_km must be a number") from None
        if distance_km < 0:
            raise ValueError("distance_km must not be negative")
    on = on or today()
    result = []
    for app, fee in (fee_model if fee_model is not None else fees.FEES).items():
        service = max(fee.service_min, money(subtotal * fee.service_rate))
        if fee.service_max is not None:
            service = min(service, fee.service_max)
        small = fee.small_order_fee if subtotal < fee.small_order_threshold else D(0)
        if distance_km is None:
            delivery = money((fee.delivery_low + fee.delivery_high) / 2)
        else:
            delivery = fees.delivery_for_distance(fee, distance_km)
        eligible, excluded = [], []
        for promo in promos:
            if promo.app != app:
                continue
            reason = promo.exclusion(subtotal, restaurant, app in new_customer_apps, on, fees.MAX_PROMO_AGE_DAYS)
            if reason:
                excluded.append(f"{promo.code}: {reason} [{promo.source_url}]")
            else:
                eligible.append(promo)

        def price(promo, delivery_fee):
            discount = D(0)
            if promo:
                if promo.discount_type == "free_delivery":
                    discount = delivery_fee
                elif promo.discount_type == "fixed":
                    discount = min(subtotal, amount(promo.value))
                else:
                    discount = min(subtotal, money(subtotal * amount(promo.value) / 100))
                if promo.cap is not None:
                    discount = min(discount, amount(promo.cap))
            base = subtotal + service + small + delivery_fee
            tax = money((base if fees.TAX_ON_PRE_DISCOUNT else base - discount) * fees.TAX_RATE)
            return money(base - discount + tax + tip), money(discount), tax

        # Include the no-promo option; never stack. Stable code tie-break.
        candidates = [None] + sorted(eligible, key=lambda p: p.code)
        best = min(candidates, key=lambda p: price(p, delivery)[0])
        total, discount, tax = price(best, delivery)
        result.append(Estimate(app, fee.name, subtotal, service, small, delivery, discount, tax, tip,
                               total, price(best, fee.delivery_low)[0], price(best, fee.delivery_high)[0],
                               best, tuple(excluded)))
    return sorted(result, key=lambda row: (row.total, row.name))
