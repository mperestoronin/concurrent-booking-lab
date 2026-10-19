import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from redis import Redis

from app.config import Settings
from app.hooks import Hooks
from app.main import create_app
from app.repository import Repository


@pytest.fixture(scope="session")
def isolated_settings():
    database_url = os.getenv("TEST_DATABASE_URL")
    redis_url = os.getenv("TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.fail("Нужны TEST_DATABASE_URL и TEST_REDIS_URL; запустите tests через Compose")
    schema = f"lab_test_{uuid4().hex}"
    settings = Settings(database_url, redis_url, schema=schema, key_prefix=f"{schema}:")
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        repository = Repository(settings)
        probe_id = uuid4()
        with repository.connect() as conn:
            conn.execute((Path(__file__).parent / "fixtures/starter_schema.sql").read_text(
                encoding="utf-8"))
            conn.execute("""INSERT INTO bookings(id, resource_id, client_id, hold_id)
                VALUES (%s,3,'migration-probe',%s)""", (probe_id, uuid4()))
            before = conn.execute("SELECT * FROM bookings WHERE id=%s", (probe_id,)).fetchone()
        repository.migrate()
        with repository.connect() as conn:
            probe = conn.execute("SELECT * FROM bookings WHERE id=%s", (probe_id,)).fetchone()
        assert probe and all(probe.get(key) == value for key, value in before.items()), (
            "Миграция потеряла или изменила существующую бронь")
        yield settings
    finally:
        try:
            with Redis.from_url(redis_url, socket_timeout=3, socket_connect_timeout=3) as redis:
                for key in redis.scan_iter(match=f"{schema}:*"):
                    redis.delete(key)
        finally:
            with psycopg.connect(database_url, autocommit=True, connect_timeout=5) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def settings(isolated_settings):
    # Своя схема на запуск, свой префикс на каждый сценарий; DB 0 приложения не трогаем.
    return replace(isolated_settings, key_prefix=f"{isolated_settings.schema}:{uuid4().hex}:")


@pytest.fixture
def hooks():
    return Hooks()


@pytest.fixture
def client(settings, hooks):
    application = create_app(settings, hooks)
    with Repository(settings).connect() as conn:
        conn.execute("TRUNCATE bookings")
    try:
        with TestClient(application, raise_server_exceptions=False) as api:
            yield api
    finally:
        with Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3) as redis:
            for key in redis.scan_iter(match=f"{settings.key_prefix}*"):
                redis.delete(key)


@pytest.fixture
def service(client):
    return client.app.state.service
