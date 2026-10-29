from fastapi import APIRouter

from app import settings

router = APIRouter(prefix="/api/version", tags=["version"])


@router.get("")
def version() -> dict[str, str]:
    return {"version": settings.app_version}
