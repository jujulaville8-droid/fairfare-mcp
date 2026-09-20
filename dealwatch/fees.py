"""Editable CAD modelling assumptions, reviewed 2026-09-20.

These are planning defaults, NOT published Toronto price quotes. Public help
pages describe variable fees and do not establish a universal Toronto rate.
Keep every fee/tax assumption here. Delivery midpoint determines ranking;
the low/high values give scenarios, not statistical confidence bounds.
"""
from dataclasses import dataclass
from decimal import Decimal as D


@dataclass(frozen=True)
class Fee:
    name: str
    service_rate: D
    delivery_low: D
    delivery_high: D
    small_order_threshold: D
    small_order_fee: D
    source: str
    service_min: D = D("0")
    service_max: D | None = None


FEES = {
    "doordash": Fee("DoorDash", D("0.15"), D("0.99"), D("5.99"), D("12"), D("2"),
        "https://help.doordash.com/en-ca/consumers/article/what-fees-do-i-pay"),
    "uber_eats": Fee("Uber Eats", D("0.15"), D("0.99"), D("5.99"), D("10"), D("2"),
        "https://help.uber.com/ca-ES/merchants-and-restaurants/article/how-do-customer-delivery-fees-work?nodeId=56eeed53-c24e-4216-a30b-1f5ef879d0f9"),
    "skip": Fee("SkipTheDishes", D("0.10"), D("1.99"), D("5.99"), D("0"), D("0"),
        "https://www.skipthedishes.com/faq"),
}
# Simplified Ontario restaurant-meal scenario; not a tax engine.
TAX_RATE = D("0.13")
# Conservative: estimate tax on food before discounts plus modelled fees.
TAX_ON_PRE_DISCOUNT = True
MAX_PROMO_AGE_DAYS = 7
