from fastapi import APIRouter, HTTPException
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app import ReleaseIn, ReleaseOut, engine, releases

router = APIRouter(prefix="/api/releases", tags=["releases"])


@router.get("", response_model=list[ReleaseOut])
def list_releases():
    with engine.connect() as conn:
        rows = conn.execute(select(releases).order_by(releases.c.created_at.desc(), releases.c.id.desc()))
        return [dict(r._mapping) for r in rows]


@router.post("", status_code=201, response_model=ReleaseOut)
def create_release(body: ReleaseIn):
    try:
        with engine.begin() as conn:
            row = conn.execute(insert(releases).values(**body.model_dump()).returning(releases)).one()
    except IntegrityError:
        raise HTTPException(409, "version already exists")
    return dict(row._mapping)
