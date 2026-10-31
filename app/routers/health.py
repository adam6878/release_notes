from http import HTTPStatus

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import engine, log

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as e:
        log.warning("database not ready", extra={"fields": {"error": str(e)}})
        raise HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "database unavailable")
    return {"status": "ready"}
