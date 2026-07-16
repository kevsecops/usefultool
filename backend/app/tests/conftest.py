"""Pytest configuration and fixtures."""

import os
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/usefultool_test"


def _require_test_database_url() -> str:
    """Never run drop_all() against a non-test database (e.g. .env usefultool)."""
    url = (
        os.environ.pop("DATABASE_URL", None)
        or os.environ.get("PYTEST_DATABASE_URL")
        or DEFAULT_TEST_DATABASE_URL
    )
    db_name = urlparse(url).path.lstrip("/").split("/")[0]
    if not db_name.endswith("_test"):
        raise SystemExit(
            f"Refusing to run tests against database '{db_name}': name must end with '_test'. "
            "Tests call Base.metadata.drop_all() and will destroy all data. "
            "Set PYTEST_DATABASE_URL to a dedicated test database."
        )
    return url


os.environ["DATABASE_URL"] = _require_test_database_url()
os.environ["DEMO_MODE"] = "true"
os.environ["NINA_FALLBACK_TO_FIXTURES"] = "false"
os.environ.setdefault("LLM_ENABLED", "false")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("FIXTURES_DIR", str(Path(__file__).resolve().parents[3] / "fixtures"))

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

get_settings.cache_clear()
settings = get_settings()


@pytest.fixture(autouse=True)
def _reset_test_env() -> Generator[None, None, None]:
    """Ensure each test starts in demo/fixture mode unless it overrides env."""
    os.environ["DEMO_MODE"] = "true"
    os.environ["NINA_FALLBACK_TO_FIXTURES"] = "false"
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url, pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = TestingSessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
