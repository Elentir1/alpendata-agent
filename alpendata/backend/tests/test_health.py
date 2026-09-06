import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from alpendata_api.app import create_app
from alpendata_api.settings import Settings


def test_readiness_tracks_live_schema_and_redacts_database_errors(service):
    app, client = service
    assert client.get("/health/ready").json() == {"status": "ready"}
    with app.state.engine.begin() as db:
        version = db.scalar(text("SELECT version_num FROM alembic_version"))
        db.execute(text("UPDATE alembic_version SET version_num = 'incompatible'"))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/health/live").status_code == 200
    with app.state.engine.begin() as db:
        db.execute(text("UPDATE alembic_version SET version_num = :version"), {"version": version})
    assert client.get("/health/ready").status_code == 200
    with app.state.engine.begin() as db:
        db.execute(text("ALTER TABLE alembic_version RENAME COLUMN version_num TO unavailable_version"))
    try:
        assert client.get("/health/ready").status_code == 503
    finally:
        with app.state.engine.begin() as db:
            db.execute(text("ALTER TABLE alembic_version RENAME COLUMN unavailable_version TO version_num"))


def test_startup_refuses_unmigrated_database_without_changing_it(database_url):
    app = create_app(Settings(database_url=database_url))
    with pytest.raises(RuntimeError, match="^application_database_not_ready$"):
        with TestClient(app):
            pytest.fail("An incompatible application must not start")
    assert inspect(app.state.engine).get_table_names() == []
    app.state.engine.dispose()
