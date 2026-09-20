"""Small, conservative public-page adapters. No app APIs, links, or logins."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.robotparser import RobotFileParser

from .models import Promo, today

USER_AGENT = "FoodDealWatch/0.1"
MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class Source:
    id: str
    app: str
    url: str
    adapter: str


SOURCES = (
    Source("uber_official", "uber_eats", "https://www.uber.com/ca/en/blog/can-promo-cards/", "uber"),
    Source("uber_coupons", "uber_eats", "https://www.lovecoupons.ca/ubereats", "love"),
    Source("door_coupons", "doordash", "https://www.lovecoupons.ca/doordash", "love"),
    Source("skip_coupons", "skip", "https://www.lovecoupons.ca/skipthedishes", "love"),
)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if not self.hidden and tag in {"h1", "h2", "h3", "h4", "p", "div", "li", "br", "button"}:
            self.parts.append("\n")
        if not self.hidden and tag in {"h2", "h3", "h4"}:
            self.parts.append("### ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {"h1", "h2", "h3", "h4", "p", "div", "li", "button"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible_text(document):
    if not re.search(r"<(?:html|div|p|h[1-6])\b", document, re.I):
        return document
    parser = VisibleText()
    parser.feed(document)
    return "".join(parser.parts)


def parse(source, document, observed_on):
    text = visible_text(document)
    if source.adapter == "uber":
        # Isolate the restaurant offer from the separate grocery promotion.
        blocks = re.split(r"Promo code\s*:", text, flags=re.I)
        promos = []
        for block in blocks[1:]:
            code = re.match(r'\s*[“"\']?([A-Z][A-Z0-9]+)', block)
            flat = " ".join(block.split())
            value = re.search(r"\$(\d+(?:\.\d+)?) off your first order", flat, re.I)
            minimum = re.search(r"\$(\d+(?:\.\d+)?) minimum order", flat, re.I)
            expiry = re.search(r"Expires (\d{1,2}/\d{1,2}/\d{4})", flat, re.I)
            if not (code and value and minimum and expiry):
                continue
            if "Valid only in Canada" not in flat or "First time users only" not in flat:
                continue
            promos.append(Promo(code.group(1), source.app, "fixed", value.group(1), minimum.group(1),
                datetime.strptime(expiry.group(1), "%m/%d/%Y").date().isoformat(), "CA", observed_on,
                source.url, status="documented", new_customer_only=True,
                terms="First Uber Eats order only; food subtotal minimum; fees/taxes excluded; no stacking. Exclusions may apply."))
        if not promos:
            raise ValueError("Official restaurant-promo structure/terms changed or offer removed; review adapter")
        return promos

    if "Coupon" not in text or "Get Offer" not in text and "Get Code" not in text:
        raise ValueError("Coupon page structure not recognized (possibly a challenge page)")
    promos = []
    for block in re.split(r"#{2,4}\s+", text):
        # Only a complete, visible code immediately preceding Get Code counts.
        match = re.search(r"(?:^|\n)\s*([A-Za-z0-9_-]{4,40})\s*\n\s*Get Code\b", block)
        heading = block.split("\n", 1)[0]
        value = re.search(r"(?:\$([0-9]+(?:\.[0-9]+)?)|([0-9]+)%)\s*[Oo]ff", heading)
        if not match or not value:
            continue
        minimum = re.search(r"(?:[Oo]ver|[Oo]rders? of|[Mm]inimum(?: spend)?)\s*(?:CA)?\$(\d+(?:\.\d+)?)", block)
        expiry = re.search(r"Expires (\d{1,2} [A-Za-z]+ \d{4})", block)
        expires = datetime.strptime(expiry.group(1), "%d %B %Y").date().isoformat() if expiry else None
        promos.append(Promo(match.group(1), source.app, "fixed" if value.group(1) else "percent",
            value.group(1) or value.group(2), minimum.group(1) if minimum else None, expires,
            "CA-unconfirmed", observed_on, source.url, new_customer_only="first order" in block.lower(),
            terms=f"Aggregator candidate: {heading.strip()}. Toronto eligibility and complete terms require review; never auto-applied."))
    return promos


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect refused; review the configured public URL")


def fetch(source):
    if source not in SOURCES:
        raise ValueError("Only configured public promo pages may be fetched")
    opener = build_opener(NoRedirect())

    def get(url):
        with opener.open(Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"}), timeout=15) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("Public page exceeded size limit")
            return body.decode("utf-8", errors="replace")

    parts = urlsplit(source.url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    robots = RobotFileParser()
    robots.parse(get(robots_url).splitlines())
    if not robots.can_fetch(USER_AGENT, source.url):
        raise ValueError("robots.txt disallows this public page")
    return get(source.url)


def load(path):
    raw = json.loads(Path(path).read_text())
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported promo cache schema")
    raw["promos"] = [Promo(**p) for p in raw["promos"]]
    return raw


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {**data, "promos": [asdict(p) for p in data["promos"]]}
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        json.dump(serializable, output, indent=2)
        output.write("\n")
        temporary = Path(output.name)
    temporary.replace(path)


def refresh(path, previous=None, *, fetcher=fetch, on=None):
    on = on or today()
    previous = previous or {"promos": [], "sources": []}
    promos, reports = [], []
    for source in SOURCES:
        report = {"id": source.id, "app": source.app, "url": source.url, "attempted_on": on.isoformat()}
        try:
            found = parse(source, fetcher(source), on.isoformat())
            promos.extend(found)
            report.update(status="ok", observed_on=on.isoformat(), count=len(found))
        except (OSError, ValueError) as exc:
            # Preserve provenance/date; failed fetches never make old offers fresh.
            retained = [p for p in previous["promos"] if p.source_url == source.url]
            promos.extend(retained)
            report.update(status="error", error=str(exc), retained=len(retained))
        reports.append(report)
    data = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "provenance": "Direct public-page refresh; source failures retain dated observations.",
            "promos": list({(p.app, p.code, p.source_url): p for p in promos}.values()), "sources": reports}
    save(path, data)
    return data
