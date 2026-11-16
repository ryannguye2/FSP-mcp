"""MCP server for the Flight Schedule Pro API (read-only)."""
import asyncio
import os

import httpx
from mcp.server.fastmcp import FastMCP

BASE = "https://usc-api.flightschedulepro.com"
API_KEY = os.environ["FSP_API_KEY"]
OPERATOR_ID = os.environ["FSP_OPERATOR_ID"]
URL_TOKEN = os.environ["FSP_URL_TOKEN"]  # secret path segment; requests to any other path get a 404

mcp = FastMCP(
    "flight-schedule-pro",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
    streamable_http_path=f"/{URL_TOKEN}/mcp",
)

# FSP allows 300 calls per 5 minutes per key, so calls are serialized.
_lock = asyncio.Lock()


async def _get(api: str, path: str, params: dict | None = None):
    url = f"{BASE}/{api}/v1.0/operators/{OPERATOR_ID}/{path.lstrip('/')}"
    params = {k: v for k, v in (params or {}).items() if v is not None}
    async with _lock, httpx.AsyncClient(timeout=30) as client:
        for _ in range(2):
            r = await client.get(url, params=params, headers={"x-subscription-key": API_KEY})
            if r.status_code == 429:
                await asyncio.sleep(int(r.headers.get("Retry-After", "5")))
                continue
            r.raise_for_status()
            return r.json()
    raise RuntimeError("Rate limited by Flight Schedule Pro")


@mcp.tool()
async def list_aircraft(limit: int = 100, offset: int = 0, fields: str | None = None):
    """List aircraft. fields is a comma-separated list, e.g. 'name,tailNumber'."""
    return await _get("core", "aircraft", {"limit": limit, "offset": offset, "fields": fields})


@mcp.tool()
async def get_aircraft(aircraft_id: str):
    """Get one aircraft by ID."""
    return await _get("core", f"aircraft/{aircraft_id}")


@mcp.tool()
async def list_flights(limit: int = 100, offset: int = 0, sort_by: str = "startTime", filters: dict | None = None):
    """List flights. filters maps field to value, e.g. {'startTime': 'gt:2026-11-15'}."""
    return await _get("scheduling", "flights", {"limit": limit, "offset": offset, "sortBy": sort_by, **(filters or {})})


@mcp.tool()
async def list_resource(api: str, resource: str, limit: int = 100, offset: int = 0, filters: dict | None = None):
    """Generic read for any endpoint. api is core, scheduling, training or reporting;
    resource is a path like 'users', 'instructors', 'reservations' or 'squawks'."""
    if api not in {"core", "scheduling", "training", "reporting"}:
        raise ValueError("api must be core, scheduling, training or reporting")
    return await _get(api, resource, {"limit": limit, "offset": offset, **(filters or {})})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
