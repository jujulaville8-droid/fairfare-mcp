# Food Deal-Watch v0.1

Compare **estimated** Toronto delivery totals for DoorDash, Uber Eats and
SkipTheDishes using public coupon pages and editable fee assumptions. Python
3.11+; no runtime dependencies. No login, checkout, delivery-app API, or menu
scraping. A restaurant/dish is a label: v0.1 cannot establish that an app sells
that dish, serves that restaurant/address, or charges the same menu price.

## Run

```bash
cd ~/workspace/food-deal-watch
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m dealwatch compare "restaurant name" --order-total 25
pytest -q
```

In the delivered workspace `.venv` is already prepared with Python and pytest,
so just activate it and run the last two commands. Shell network access is
blocked here; the test dependencies were copied from an existing local Python
3.12 environment. On another machine, use the normal installation above.
Running `python3 -m dealwatch ...` from this directory also works without installing.

`--order-total` is the **food subtotal**, before fees, tax, discounts and tip.
Currency is CAD. Existing customer eligibility is the default. To model your
first order on a particular app, explicitly name it:

```bash
python -m dealwatch compare "Noodle House" --order-total 40 --new-customer uber_eats
python -m dealwatch compare "pizza" --order-total 25 --tip 4
```

`--new-customer` accepts `doordash`, `uber_eats`, or `skip` and can be repeated.
It describes eligibility; it does not create accounts. Memberships are not modelled.

To compare for a real address instead of the flat fee midpoint, find nearby
restaurants first, then pass a result's distance into the comparison —
delivery fees scale with distance (nearby ≈ low end, 10+ km ≈ high end):

```bash
python -m dealwatch find thai --location "M5V 1J1" --limit 5
python -m dealwatch compare "Pai Downtown" --order-total 30 --distance-km 0.7 --location "M5V 1J1"
```

`find` uses free OpenStreetMap data (Photon geocoding + Overpass). Whether a
restaurant is actually listed on a delivery app is **not** checked — verify in
the app before ordering.

With the September 20, 2026 snapshot and defaults, the $25 example ranks:

| App | Estimated total | Promo |
| --- | ---: | --- |
| SkipTheDishes | $35.58 | none found (eligible, documented) |
| DoorDash | $36.43 | none found (eligible, documented) |
| Uber Eats | $36.43 | none eligible at $25 |

For a qualifying **first Uber Eats order of $40**, the snapshot applies
`FIRSTEATS30` and estimates $25.92. These are reproducible model outputs, not
observed checkout quotes. Date-sensitive eligibility changes as snapshots age.
Ties sort by app name; overlapping fee ranges mean the winner is uncertain.

## Refresh public promos

```bash
python -m dealwatch refresh
python -m dealwatch compare "restaurant name" --order-total 25 --refresh
# Alternative cache locations:
python -m dealwatch refresh --output /tmp/food-promos.json
python -m dealwatch compare "restaurant name" --order-total 25 --promos /tmp/food-promos.json
```

Refresh writes `promos.local.json` in the current directory. Compare uses an
explicit `--promos` path, otherwise the local cache if present, otherwise the
bundled snapshot. Compare does **not** silently contact the internet. It prints
cache location, source URLs, observation dates, rejected offers and refresh errors.
The bundled snapshot remains unchanged when using the default refresh command.

The collector requests only the pages in `dealwatch/collector.py:SOURCES` and
those hosts' `robots.txt`. It uses a descriptive user agent, 15-second request
timeouts and a 2 MB response limit. It refuses redirects, respects robots
exclusions, executes no JavaScript, follows no coupon/affiliate/order links,
stores no cookies, and never bypasses a challenge or login. A robots fetch
failure also prevents the page fetch. These conservative choices can prevent
collection from otherwise publicly browsable pages.

Each source reports success or failure independently. A successful refresh
replaces that source's codes; a failed fetch/parse preserves its original
observations without changing their dates. The CLI `refresh` exits 1 for any
source failure, 0 for complete success. `compare` can still produce fee-only or
cached estimates after a failed refresh and prints that failure; invalid
arguments/cache data exit 2. Cache writes use an atomic file replacement.

## What was actually found

The bundled `dealwatch/data/promos.json` contains structured facts transcribed
from public pages opened through the browsing tool on **2026-09-20**. It is
explicitly marked `browser_snapshot`: it is not a claim that the Python HTTP
collector completed a live refresh in this restricted workspace.

* [Uber's Canadian promotional-card terms](https://www.uber.com/ca/en/blog/can-promo-cards/):
  `FIRSTEATS30`, $30 off, $40 food minimum, first-time users, Canada, expiry
  2026-12-31. This is the documented restaurant offer. The separate grocery
  offer is excluded. Redemption is still subject to Uber's exclusions and
  availability; no checkout validation was performed.
* [Love Coupons Canada — Skip](https://www.lovecoupons.ca/skipthedishes):
  visible codes `K5248WMzwj` (advertised $7 first-order saving) and
  `UALDVQ95BLY5` (advertised $5 Subway combo saving). Their complete minimum,
  expiry and Toronto eligibility are not established. They are stored as
  **unverified candidates**, never auto-applied.
* [Love Coupons Canada — DoorDash](https://www.lovecoupons.ca/doordash) and
  [Uber Eats](https://www.lovecoupons.ca/ubereats): the inspected listings did
  not expose usable restaurant coupon codes with complete Toronto terms.
* Additional public research included [DoorDash's September Prime offer](https://help.doordash.com/en-us/consumers/article/amazon-prime-video-x-dashpass-lto-terms-and-conditions-september-2026)
  and [selected-restaurant offer](https://help.doordash.com/en-us/consumers/article/get-25-percent-off-your-first-order-of-25-dollars-or-more-max-12-terms-and-conditions).
  These are account-targeted offers without a public usable code in those terms;
  neither is applied. They are research references, not automatic adapters.

No currently valid, fully documented Toronto restaurant code was established
for DoorDash or Skip from the checked sources. **“None found” is scoped to
those sources and your eligibility, not proof that no offers exist anywhere.**
A coupon site's “verified” badge or rolling month in its title is insufficient.
The collector does not reconstruct masked codes or invent expiry dates.

## Data and eligibility

Every promo stores `code`, `app`, `discount_type` (`fixed`, `percent`, or
`free_delivery`), `value`, `minimum_order`, `expires`, `region`, `observed_on`,
`source_url`, `status`, optional `cap`/`starts`, first-order eligibility,
restaurant restrictions, and a short terms summary. Unknown values are `null`.
Percent values use 0–100. Amounts are decimal strings, not binary floats.

Only `documented` offers with known minimum and expiry, a Toronto-compatible
region (`CA`, `CA-ON`, `Toronto`), matching restaurant restrictions, and a
satisfied first-order requirement can affect totals. Expiry is inclusive in
Toronto's calendar date. Observations older than **7 days** or in the future
are excluded, even when the published expiry is later. Source refresh failures
are shown separately and never reset freshness.

The Uber adapter extracts the restaurant code and explicit terms from its
public page, separating grocery promotions. The Love Coupons adapter extracts
complete visible codes from individual offer sections but **always** stores
these as candidates: v0.1 does not infer missing restrictions. Promoting a new
candidate requires a source-specific adapter/review that encodes all relevant
terms, not flipping its status alone. If page structure changes, review the
adapter and tests. Parsers are deliberately narrow, not a general coupon crawler.

## Fee model

Edit **`dealwatch/fees.py`** to change all fee and tax assumptions. Defaults:

| App | Service estimate | Delivery scenario | Small-order estimate |
| --- | --- | --- | --- |
| DoorDash | 15% of food subtotal | $0.99–$5.99 | $2 below $12 |
| Uber Eats | 15% of food subtotal | $0.99–$5.99 | $2 below $10 |
| SkipTheDishes | 10% of food subtotal | $1.99–$5.99 | $0 modelled |

**These are configurable planning assumptions, not a verified Toronto tariff.**
[DoorDash's fee help](https://help.doordash.com/en-ca/consumers/article/what-fees-do-i-pay)
explains variable fees without one universal rate.
[Uber's public fee explanation](https://help.uber.com/ca-ES/merchants-and-restaurants/article/how-do-customer-delivery-fees-work?nodeId=56eeed53-c24e-4216-a30b-1f5ef879d0f9)
provides the 15%/$2-under-$10 reference, but does not establish that those
numbers apply to every Toronto order.
[Skip's FAQ](https://www.skipthedishes.com/faq) describes delivery/service fees
without substantiating a universal 10% rate. DoorDash and Skip service rates,
all delivery ranges, and unconfirmed small-order fees are explicit assumptions.
Service-fee floors/caps are supported but unset by default.

The midpoint delivery fee determines ranking. Each row also shows low/high
**total** scenarios for the same chosen promo. Service fees use the original
food subtotal; the best single eligible promo is applied without stacking.
Food discounts cannot exceed the food subtotal. Delivery discounts reduce
only the delivery component. Money rounds half-up to cents.

```
base = food + service + delivery + small-order fee
estimated tax = 13% × base                  # before the promo by default
estimated total = base - best promo + estimated tax + flat tip
```

The conservative pre-discount tax basis is configurable with
`TAX_ON_PRE_DISCOUNT`. This is a simplified Ontario restaurant-meal scenario,
not a tax engine. It omits item-specific taxes, coupon tax treatment differences,
menu markups, memberships, priority delivery, bags, regulatory/distance/surge
surcharges, and fees not explicitly modelled. The ranges reflect delivery
variation only; they are not guaranteed lower/upper bounds on actual prices.

## Tests and maintenance

```bash
pytest -q
```

Tests cover known totals, ranking changes, ties, capped percentages, discount
clamping, no stacking, expiry/minimum/freshness boundaries, customer and
restaurant restrictions, invalid amounts, small orders, tips, fee configuration,
parser extraction, missing terms, hidden codes, challenge pages, cache retention,
robots/redirect restrictions, HTTP transport with mocked responses, and CLI
integration. Fixture codes are synthetic and never enter the shipped cache.
Live network tests are intentionally separate from deterministic unit tests.

To add an app:

1. Add a stable app key and `Fee` entry in `fees.py`, with cited reference and
   clearly labelled assumptions. The CLI choices and ranking use this registry.
2. Add a public source to `collector.py:SOURCES` and a narrow adapter. Never use
   an ordering endpoint. Store unknown terms as unverified; encode new
   restrictions in `Promo.exclusion` before permitting them in estimates.
3. Add source-shaped parser fixtures and comparison tests; refresh and review
   the stored facts, region, expiry, and source citations.

To update an existing fee, edit its one registry entry. To support a new public
coupon source, add an adapter and tests; do not relax extraction to treat random
page text or masked suffixes as promo codes.

## v0.2

* More public sources and per-source change detection, with an explicit review
  workflow for complete terms and targeted/restaurant-specific eligibility.
* User-entered app-specific menu subtotals, actual fee overrides and memberships;
  authorized partner APIs could add price/availability data without scraping.
* Dish/restaurant matching from permitted catalogues, budget-aware basket
  suggestions, and timezone-aware intraday promotions.
* Broader tax/surcharge scenarios, scheduled refreshes, notifications, and a
  small web interface showing confidence and source freshness.

No version needs automated logins, checkout scraping, or order placement.
