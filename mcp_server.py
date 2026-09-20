"""FairFare MCP server — Toronto food-delivery deal watch as a custom connector.

Exposes the dealwatch engine over Streamable HTTP so it can be added as a
custom connector (Customize -> Connectors -> Add custom connector).

Run locally:
    python mcp_server.py            # http://127.0.0.1:8000/mcp

Deploy:
    Respects the PORT env var. See Dockerfile for a container deploy.
"""

import os
import secrets
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from dealwatch.collector import load, refresh
from dealwatch.compare import compare
from dealwatch.fees import FEES

HERE = Path(__file__).parent
BUNDLED = HERE / "dealwatch" / "data" / "promos.json"
LOCAL = HERE / "promos.local.json"

mcp = FastMCP(
    name="FairFare",
    instructions=(
        "Toronto food-delivery deal comparison across DoorDash, Uber Eats and "
        "SkipTheDishes. All totals are ESTIMATES built from a dated snapshot of "
        "public promo pages plus editable fee assumptions — never live checkout "
        "quotes. The same menu price is assumed on every app; restaurant/dish "
        "availability on each app is NOT checked."
    ),
)


def _snapshot():
    path = LOCAL if LOCAL.exists() else BUNDLED
    return load(path), path.name


@mcp.tool()
def compare_delivery_prices(
    restaurant: str,
    order_subtotal: float,
    tip: float = 0.0,
    new_customer_apps: list[str] | None = None,
) -> str:
    """Rank estimated Toronto delivery totals across DoorDash, Uber Eats, SkipTheDishes.

    Estimates only: uses a dated public-promo snapshot and fee assumptions, assumes
    the same food price on every app, and does not check restaurant availability or
    real checkout prices. `restaurant` is just a label for the comparison.
    `new_customer_apps` may contain any of: doordash, uber_eats, skip.
    """
    valid = [a for a in (new_customer_apps or []) if a in FEES]
    data, snapshot_name = _snapshot()
    rows = compare(
        restaurant, order_subtotal, data["promos"],
        new_customer_apps=valid, tip=tip,
    )
    lines = [
        f"FairFare estimate - Toronto - {rows[0].subtotal:.2f} CAD food subtotal",
        f"Promo snapshot: {snapshot_name} (dated - refresh when stale)",
        "Estimates only: same menu price assumed on all apps; availability not checked.",
        "",
    ]
    for rank, row in enumerate(rows, 1):
        promo = row.promo.code if row.promo else "none found"
        lines.append(
            f"{rank}. {row.name}: ~${row.total:.2f} "
            f"(range ${row.low:.2f}-${row.high:.2f}) - promo: {promo}"
        )
        lines.append(
            f"   food ${row.subtotal:.2f} + service ${row.service:.2f} "
            f"+ delivery ${row.delivery:.2f} + small-order ${row.small_order:.2f} "
            f"- promo ${row.discount:.2f} + tax ${row.tax:.2f} + tip ${row.tip:.2f}"
        )
        if row.promo:
            lines.append(f"   source: {row.promo.source_url}")
    if len(rows) > 1 and rows[0].high >= min(r.low for r in rows[1:]):
        lines.append("Fee ranges overlap - real delivery fees could change the ranking.")
    return "\n".join(lines)


@mcp.tool()
def refresh_promo_snapshot() -> str:
    """Re-fetch the public promo/coupon pages and save a fresh dated snapshot."""
    data = load(LOCAL if LOCAL.exists() else BUNDLED)
    data = refresh(LOCAL, data)
    bad = [s for s in data["sources"] if s["status"] == "error"]
    ok = len(data["sources"]) - len(bad)
    msg = f"Refreshed {ok} sources OK, {len(bad)} failed."
    if bad:
        msg += " Failures: " + "; ".join(f"{s['id']}: {s.get('error')}" for s in bad)
    return msg


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    token = os.environ.get("AUTH_TOKEN", "")

    app = mcp.streamable_http_app()

    if token:

        class BearerAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.headers.get("authorization", "") != f"Bearer {token}":
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(BearerAuth)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
