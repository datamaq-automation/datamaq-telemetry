from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["Sistema"])


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
