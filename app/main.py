from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app import configure_logging, engine, metadata, observe_requests, settings
from app.routers import health_router, metrics_router, releases_router, version_router

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    # ponytail: create_all can race when replicas start together; use Alembic + a migration Job in prod
    metadata.create_all(engine)
    yield


app = FastAPI(title="Release Notes", lifespan=lifespan)

app.middleware("http")(observe_requests)


@app.exception_handler(HTTPException)
async def log_http_error(request: Request, exc: HTTPException) -> Response:
    request.state.error = exc.detail
    return await http_exception_handler(request, exc)


app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(releases_router)
app.include_router(version_router)

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")
