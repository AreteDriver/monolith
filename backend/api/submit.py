"""Submit API — player bug submission tool."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/submit", tags=["submit"])


@router.post("")
def submit_observation() -> dict:
    """Player submits a bug observation. Implementation in Sprint 4."""
    return {"message": "Implementation in Sprint 4"}
