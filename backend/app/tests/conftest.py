"""Pytest configuration and fixtures."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/usefultool_test",
)
os.environ.setdefault("FIXTURES_DIR", str(Path(__file__).resolve().parents[3] / "fixtures"))

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

get_settings.cache_clear()
settings = get_settings()


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
