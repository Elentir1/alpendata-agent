"""Check release/database compatibility without migrating or exposing database details."""

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError


def release_head() -> str:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("application_migrations_missing")
    return head


def database_ready(engine, expected: str) -> bool:
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_heads() == (expected,)
    except SQLAlchemyError:
        return False


def health_router(engine, expected: str) -> APIRouter:
    router = APIRouter()

    @router.get("/health/live")
    def live():
        return {"status": "ok"}

    @router.get("/health/ready")
    def ready():
        available = database_ready(engine, expected)
        return JSONResponse(
            {"status": "ready" if available else "unavailable"}, status_code=200 if available else 503
        )

    return router
