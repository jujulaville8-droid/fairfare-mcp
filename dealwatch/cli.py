import argparse
from decimal import InvalidOperation
from pathlib import Path
import sys

from .collector import load, refresh
from .compare import compare
from .fees import FEES
from . import geo

BUNDLED = Path(__file__).parent / "data" / "promos.json"
LOCAL = Path("promos.local.json")


def _run_find(args) -> int:
    try:
        lat, lon, label = geo.geocode(args.location)
    except (OSError, ValueError) as exc:
        print(f"dealwatch: {exc}", file=sys.stderr)
        return 2
    where = label.split(",")[0]
    print(f"Restaurants serving {args.cuisine.strip().lower()} near {where} "
          f"(within {geo.SEARCH_RADIUS_M // 1000} km, closest first):")
    print("App availability NOT checked - verify in the delivery app.")
    try:
        spots = geo.find_nearby(lat, lon, args.cuisine, limit=args.limit)
    except (OSError, ValueError) as exc:
        print(f"dealwatch: {exc}", file=sys.stderr)
        return 2
    if not spots:
        print("No matches found. Try a broader cuisine or a nearby neighbourhood.")
        return 0
    for i, s in enumerate(spots, 1):
        addr = f" - {s['address']}" if s["address"] else ""
        print(f"{i}. {s['name']}{addr} - ~{s['distance_km']} km away")
        print(f"   compare with: --distance-km {s['distance_km']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Toronto food-delivery estimates from public promos (CAD)")
    commands = parser.add_subparsers(dest="command", required=True)
    comp = commands.add_parser("compare", help="Rank estimated totals; does not contact delivery apps")
    comp.add_argument("restaurant", help="Restaurant or dish label; availability is not checked")
    comp.add_argument("--order-total", required=True, help="Food subtotal before taxes and fees in CAD")
    comp.add_argument("--tip", default="0", help="Flat CAD tip on every app (default: 0)")
    comp.add_argument("--new-customer", action="append", choices=list(FEES), default=[], metavar="APP",
                      help="Eligible for first-order offers on APP; repeat per app")
    comp.add_argument("--promos", type=Path, help="Use this cache instead of local/bundled data")
    comp.add_argument("--refresh", action="store_true", help="Refresh public pages before comparison")
    comp.add_argument("--distance-km", default=None,
                      help="Restaurant distance in km; scales delivery fees instead of the flat midpoint")
    comp.add_argument("--location", default=None,
                      help="Label for where the order is going (postal code, address, neighbourhood)")
    find = commands.add_parser("find", help="Find nearby restaurants by cuisine (OpenStreetMap data)")
    find.add_argument("cuisine", help='Cuisine, e.g. "thai", "sushi", "pizza"')
    find.add_argument("--location", required=True, help="Postal code, address or neighbourhood (Toronto area)")
    find.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")
    ref = commands.add_parser("refresh", help="Fetch configured public promo/coupon pages")
    ref.add_argument("--output", type=Path, default=LOCAL)
    args = parser.parse_args(argv)
    try:
        if args.command == "find":
            return _run_find(args)
        if args.command == "refresh":
            old = load(args.output if args.output.exists() else BUNDLED)
            data = refresh(args.output, old)
            for source in data["sources"]:
                print(f"{source['id']}: {source['status']} — {source.get('error', str(source.get('count', 0)) + ' codes')}")
            print(f"Saved dated cache: {args.output}")
            return 1 if any(s["status"] == "error" for s in data["sources"]) else 0
        path = args.promos or (LOCAL if LOCAL.exists() else BUNDLED)
        data = load(path)
        if args.refresh:
            path = args.promos or LOCAL
            data = refresh(path, data)
        rows = compare(args.restaurant, args.order_total, data["promos"],
                       new_customer_apps=args.new_customer, tip=args.tip,
                       distance_km=args.distance_km)
        where = args.location.strip() if args.location and args.location.strip() else "Toronto"
        print(f"{where} • {args.restaurant} • CAD food subtotal ${rows[0].subtotal:.2f}")
        if args.distance_km is not None:
            print(f"Delivery fees scaled for ~{float(args.distance_km):.1f} km restaurant distance.")
        print(f"Dated public-source cache: {path}")
        print("Estimates only: same food price on each app; restaurant/dish availability not checked.")
        print("Includes estimated 13% tax and stated tip; standard fees, no membership benefits.")
        print("Rank  App                Estimate     Delivery-range total   Promo")
        for rank, row in enumerate(rows, 1):
            promo = row.promo.code if row.promo else "none found (eligible, documented)"
            print(f"{rank:>4}  {row.name:<18} ${row.total:>7.2f}     ${row.low:.2f}–${row.high:.2f}          {promo}")
            print(f"      Food ${row.subtotal:.2f} + service ${row.service:.2f} + delivery ${row.delivery:.2f}"
                  f" + small-order ${row.small_order:.2f} - promo ${row.discount:.2f} + tax ${row.tax:.2f} + tip ${row.tip:.2f}")
            if row.promo:
                print(f"      Source: {row.promo.source_url}")
                print(f"      Observed {row.promo.observed_on}; expires {row.promo.expires}; {row.promo.terms}")
            for excluded in row.excluded:
                print(f"      Not applied: {excluded}")
        if len(rows) > 1 and rows[0].high >= min(r.low for r in rows[1:]):
            print("Fee ranges overlap; actual delivery fees could change the ranking.")
        for source in data["sources"]:
            print(f"Source {source['id']}: {source['status']}; observed {source.get('observed_on', 'see retained promo dates')}; {source['url']}")
            if source["status"] == "error":
                print(f"  Refresh failed: {source['error']}; retained data is not live.", file=sys.stderr)
        print("No login or checkout validation. 'None found' describes checked sources, not all available offers.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
        print(f"dealwatch: {exc}", file=sys.stderr)
        return 2
