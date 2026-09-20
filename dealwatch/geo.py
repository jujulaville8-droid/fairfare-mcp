"""Location helpers for FairFare: geocoding + nearby restaurant discovery.

No API keys needed: Nominatim (geocoding) and Overpass (OpenStreetMap) are
free for light use. Results are approximate OpenStreetMap data - whether a
restaurant is actually listed on DoorDash, Uber Eats or SkipTheDishes is NOT
checked here.
"""
import json
import math
import time
import urllib.parse
import urllib.request

USER_AGENT = "FairFare/0.2 (Toronto food-delivery estimates)"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"
# Overpass mirrors: the main instance 504s under load, so fall through the list.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]
SEARCH_RADIUS_M = 5000

# Rough Greater Toronto Area bounding box (min_lon, min_lat, max_lon, max_lat).
# FairFare is a Toronto product: prefer results inside it, but never exclude
# out-of-area queries entirely.
GTA_BBOX = (-79.9, 43.4, -78.9, 44.1)

# User wording -> OpenStreetMap `cuisine` tag value.
CUISINES = {
    "thai": "thai",
    "chinese": "chinese",
    "indian": "indian",
    "italian": "italian",
    "japanese": "japanese",
    "sushi": "sushi",
    "korean": "korean",
    "vietnamese": "vietnamese",
    "mexican": "mexican",
    "pizza": "pizza",
    "burgers": "burger",
    "burger": "burger",
    "bbq": "bbq",
    "caribbean": "caribbean",
    "greek": "greek",
    "turkish": "turkish",
    "lebanese": "lebanese",
    "middle eastern": "middle_eastern",
    "portuguese": "portuguese",
    "spanish": "spanish",
    "french": "french",
    "american": "american",
    "seafood": "seafood",
    "vegan": "vegan",
    "vegetarian": "vegetarian",
    "breakfast": "breakfast",
    "brunch": "brunch",
    "dessert": "dessert",
    "ice cream": "ice_cream",
    "bakery": "bakery",
    "coffee": "coffee_shop",
}


def normalize_cuisine(cuisine: str) -> str:
    key = " ".join(cuisine.strip().lower().split())
    if not key:
        raise ValueError("Cuisine must not be empty")
    return CUISINES.get(key, key.replace(" ", "_"))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two lat/lon points."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _get(url: str, params: dict | None = None, timeout: int = 20) -> dict | list:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _post(url: str, data: dict, timeout: int = 30) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _post_with_retry(url: str, data: dict, timeout: int = 45,
                     retries: int = 2) -> dict:
    """POST with retries: the Overpass API 504s under load fairly often."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return _post(url, data, timeout=timeout)
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def _photon_geocode(location: str, bbox: tuple | None) -> tuple[float, float, str] | None:
    """Geocode via Photon (komoot.io). Returns None when nothing matches."""
    params = {"q": location, "limit": 3}
    if bbox:
        params["bbox"] = ",".join(str(v) for v in bbox)
    data = _get(PHOTON_URL, params)
    for feat in data.get("features", []):
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        label = _photon_label(feat.get("properties") or {}, location)
        return (lat, lon, label)
    return None


def _photon_label(props: dict, fallback: str) -> str:
    parts = []
    for key in ("name", "street", "district", "city", "state", "country"):
        val = props.get(key)
        if val and val not in parts:
            parts.append(val)
    housenumber = props.get("housenumber")
    if housenumber and parts:
        parts[0] = f"{housenumber} {parts[0]}"
    return ", ".join(parts) if parts else fallback


def _nominatim_geocode(location: str) -> tuple[float, float, str] | None:
    attempts = [
        {"format": "jsonv2", "q": location, "limit": 1, "countrycodes": "ca"},
        {"format": "jsonv2", "q": f"{location}, Canada", "limit": 1,
         "countrycodes": "ca"},
        {"format": "jsonv2", "q": location, "limit": 1},
    ]
    for params in attempts:
        try:
            results = _get(GEOCODE_URL, params)
        except Exception:
            continue
        if results:
            best = results[0]
            return (float(best["lat"]), float(best["lon"]),
                    best.get("display_name", location))
    return None


def geocode(location: str) -> tuple[float, float, str]:
    """Turn a postal code / address / neighbourhood into (lat, lon, label).

    Photon first (handles bare Canadian postal codes far better than
    Nominatim, which sometimes returns a bogus Alberta fallback), biased to
    the GTA; then Photon without the bias; then the Nominatim query chain.
    """
    location = location.strip()
    if not location:
        raise ValueError("Location must not be empty")
    last_error: Exception | None = None
    for bbox in (GTA_BBOX, None):
        try:
            hit = _photon_geocode(location, bbox)
        except Exception as exc:
            last_error = exc
            continue
        if hit:
            return hit
    try:
        hit = _nominatim_geocode(location)
    except Exception as exc:
        last_error = exc
    else:
        if hit:
            return hit
    detail = f": {last_error}" if last_error else ""
    raise ValueError(f"No match found for location {location!r}{detail}")


def find_nearby(lat: float, lon: float, cuisine: str,
                radius_m: int = SEARCH_RADIUS_M, limit: int = 10) -> list[dict]:
    """Restaurants near (lat, lon) tagged with the cuisine. Sorted by distance."""
    tag = normalize_cuisine(cuisine)
    query = (
        "[out:json][timeout:25];"
        f"(node[\"amenity\"=\"restaurant\"][\"cuisine\"~\"^{tag}$\",i]"
        f"(around:{radius_m},{lat},{lon});"
        f"way[\"amenity\"=\"restaurant\"][\"cuisine\"~\"^{tag}$\",i]"
        f"(around:{radius_m},{lat},{lon}););"
        "out center 20;"
    )
    tried: list[str] = []
    for url in OVERPASS_URLS:
        try:
            data = _post_with_retry(url, {"data": query})
            break
        except Exception as exc:
            tried.append(f"{url}: {exc}")
    else:
        raise ValueError(
            "Restaurant search failed (all Overpass mirrors busy): "
            + "; ".join(tried)
        ) from None
    spots = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        plat = el.get("lat") or (el.get("center") or {}).get("lat")
        plon = el.get("lon") or (el.get("center") or {}).get("lon")
        if plat is None or plon is None:
            continue
        addr = " ".join(p for p in (
            tags.get("addr:housenumber"), tags.get("addr:street")) if p) or tags.get(
            "addr:full", "")
        spots.append({
            "name": name,
            "address": addr,
            "distance_km": round(haversine_km(lat, lon, plat, plon), 1),
            "lat": plat,
            "lon": plon,
        })
    spots.sort(key=lambda s: s["distance_km"])
    return spots[: max(limit, 1)]
