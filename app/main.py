from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import configure_logging, engine, log, metadata, observe_requests, settings
from app.routers import health_router, metrics_router, releases_router, version_router

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ponytail: create_all can race when replicas start together; use Alembic + a migration Job in prod
    metadata.create_all(engine)
    log.info("startup complete")
    yield
    log.info("shutting down")


app = FastAPI(title="Release Notes", lifespan=lifespan)

app.middleware("http")(observe_requests)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(releases_router)
app.include_router(version_router)

# Mount last: "/" would otherwise shadow the routes above.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")
