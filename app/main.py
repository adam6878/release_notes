from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import engine, metadata
from app.routers import releases_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ponytail: create_all can race when replicas start together; use Alembic + a migration Job in prod
    metadata.create_all(engine)
    yield


app = FastAPI(title="Release Notes", lifespan=lifespan)

app.include_router(releases_router, prefix="/api/releases")

# Mount last: "/" would otherwise shadow the routes above.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")
