from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import engine, log

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    # Liveness: the process is up. No DB call, so a DB outage doesn't make k8s restart every pod.
    return {"status": "ok"}


@router.get("/readyz")
def readyz():
    # Readiness: the pod can serve traffic. Fails while the DB is unreachable, so k8s stops routing here.
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as e:
        log.warning("database not ready", extra={"fields": {"error": str(e)}})
        raise HTTPException(503, "database unavailable")
    return {"status": "ready"}
