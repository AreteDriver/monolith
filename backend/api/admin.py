"""Operator-only admin endpoints.

All routes under `/api/admin/*` require the `X-Admin-Key` header to match
`settings.admin_key` (MONOLITH_ADMIN_KEY). If the admin key is not
configured, every admin endpoint returns 403.
"""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _require_admin(request: Request) -> None:
    """Gate an admin request. Raises HTTPException(403) on failure."""
    settings = request.app.state.settings
    admin_key = getattr(settings, "admin_key", "")
    if not admin_key:
        raise HTTPException(403, "Admin endpoint not configured.")
    provided = request.headers.get("X-Admin-Key", "")
    if not provided or provided != admin_key:
        raise HTTPException(403, "Invalid admin key.")


@router.post("/admin/universe-reset")
async def universe_reset(request: Request) -> dict:
    """Flush polled world-data tables after a Frontier universe reset.

    EVE Frontier cycle transitions invalidate orbital zones, feral-AI events,
    tribe rosters, and static reference data. This endpoint calls the existing
    `WorldPoller.flush_polled_data()` and returns per-table row counts deleted.

    Chain-side tables (`chain_events`, `objects`, `world_states`) are NOT
    touched here — those are managed by the chain poll loop and table prune
    job, and wiping them requires a separate decision about object-ID
    re-discovery.

    Re-seeding happens naturally: the static_data_loop (1h) and orbital_zones
    poll will refill tables on their next cycle. No inline re-poll is
    triggered to keep this endpoint idempotent and cheap.
    """
    _require_admin(request)
    poller = request.app.state.world_poller
    flushed = poller.flush_polled_data()
    return {
        "flushed": flushed,
        "total_rows": sum(flushed.values()),
        "message": (
            "Polled world data cleared. Static data + orbital zones will "
            "repopulate on the next scheduled poll."
        ),
    }
