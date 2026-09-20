"""Offline tests for geo helpers, distance-scaled fees and compare(distance_km).

Run: python3 -m tests.test_geo   (also collected by pytest when installed)
"""
from decimal import Decimal as D

from dealwatch import fees
from dealwatch.compare import compare
from dealwatch.geo import haversine_km, normalize_cuisine


def test_haversine_zero():
    assert haversine_km(43.7, -79.4, 43.7, -79.4) == 0.0


def test_haversine_one_degree_latitude():
    # 1 degree of latitude ~= 111.2 km
    d = haversine_km(43.0, -79.4, 44.0, -79.4)
    assert 110.0 < d < 112.5, d


def test_haversine_symmetry():
    a = haversine_km(43.7, -79.4, 43.65, -79.38)
    b = haversine_km(43.65, -79.38, 43.7, -79.4)
    assert a == b and a > 0


def test_normalize_cuisine():
    assert normalize_cuisine("Thai") == "thai"
    assert normalize_cuisine("  BURGERS ") == "burger"
    assert normalize_cuisine("sushi") == "sushi"
    assert normalize_cuisine("Middle Eastern") == "middle_eastern"
    try:
        normalize_cuisine("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("empty cuisine should raise")


def test_delivery_for_distance_endpoints():
    fee = fees.FEES["doordash"]
    assert fees.delivery_for_distance(fee, 0) == fee.delivery_low
    assert fees.delivery_for_distance(fee, 10) == fee.delivery_high
    assert fees.delivery_for_distance(fee, 99) == fee.delivery_high
    assert fees.delivery_for_distance(fee, -3) == fee.delivery_low


def test_delivery_for_distance_midpoint():
    fee = fees.FEES["skip"]
    mid = fees.delivery_for_distance(fee, 5)
    expected = (fee.delivery_low + fee.delivery_high) / 2
    assert abs(mid - expected) <= D("0.01"), (mid, expected)


def test_delivery_for_distance_monotonic():
    fee = fees.FEES["uber_eats"]
    prev = D("-1")
    for km in (0, 1, 2.5, 5, 7.5, 10, 15):
        cur = fees.delivery_for_distance(fee, km)
        assert cur >= prev, (km, cur, prev)
        prev = cur


def test_compare_distance_scales_delivery():
    near = {r.app: r.delivery for r in compare("Thai Palace", 30, distance_km=1)}
    far = {r.app: r.delivery for r in compare("Thai Palace", 30, distance_km=9)}
    for app in near:
        assert far[app] > near[app], (app, near[app], far[app])


def test_compare_distance_changes_total():
    near = {r.app: r.total for r in compare("Thai Palace", 30, distance_km=1)}
    flat = {r.app: r.total for r in compare("Thai Palace", 30)}
    assert any(near[a] != flat[a] for a in near)


def test_compare_distance_rejects_negative():
    try:
        compare("Thai Palace", 30, distance_km=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative distance_km should raise")


def test_compare_distance_rejects_garbage():
    try:
        compare("Thai Palace", 30, distance_km="far")
    except ValueError:
        pass
    else:
        raise AssertionError("non-numeric distance_km should raise")


TESTS = [v for k, v in sorted(globals().items())
         if k.startswith("test_") and callable(v)]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 - tiny runner, report everything
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        else:
            print(f"ok {t.__name__}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
