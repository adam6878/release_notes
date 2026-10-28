from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def metrics():
    # ponytail: counters live per process; run one uvicorn worker per pod and let k8s scale pods
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
