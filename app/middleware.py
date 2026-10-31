import logging
import time
from http import HTTPStatus

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from app import LATENCY, REQUESTS, log

# Probes and scrapes arrive every few seconds: count them, don't log them.
QUIET_PATHS = {"/healthz", "/readyz", "/metrics"}


def metric_path(request: Request) -> str:
    # Only paths that matched an API route become labels; 404s and UI files share "other".
    return request.url.path if "route" in request.scope else "other"


async def observe_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
    start = time.perf_counter()
    status: int = HTTPStatus.INTERNAL_SERVER_ERROR  # stays 500 if the handler raises
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception as exc:
        request.state.error = repr(exc)
        raise
    finally:
        duration = time.perf_counter() - start
        path = metric_path(request)
        REQUESTS.labels(request.method, path, status).inc()
        LATENCY.labels(request.method, path).observe(duration)
        if request.url.path not in QUIET_PATHS:
            fields: dict[str, object] = {
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round(duration * 1000, 1),
            }
            # Set by the exception handler in main.py, or above when the handler crashed.
            if error := getattr(request.state, "error", None):
                fields["error"] = error
            level = {4: logging.WARNING, 5: logging.ERROR}.get(status // 100, logging.INFO)
            log.log(level, "", extra={"fields": fields})  # no text: the fields say it all
    return response
