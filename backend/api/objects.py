"""Objects API — track entity state history."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/objects", tags=["objects"])


@router.get("/{object_id}")
def get_object(object_id: str) -> dict:
    """Get an object's state trail. Implementation in Sprint 4."""
    return {"object_id": object_id, "message": "Implementation in Sprint 4"}
