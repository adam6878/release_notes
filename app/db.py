from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)

from app.config import settings

# Postgres in k8s (postgresql+psycopg://...); SQLite for local dev and tests.
engine = create_engine(settings.database_url, pool_pre_ping=True)

metadata = MetaData()
releases = Table(
    "releases",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("version", String(50), nullable=False, unique=True),
    Column("title", String(200), nullable=False),
    Column("author", String(100), nullable=False),
    Column("notes", String(500), nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)),
)
