"""Stats API — anomaly rates and system health metrics."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats() -> dict:
    """Get anomaly statistics. Implementation in Sprint 4."""
    return {"message": "Implementation in Sprint 4"}
