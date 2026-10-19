import json
import os
import subprocess
import sys
import threading
from uuid import UUID, uuid4

import psycopg
import pytest

from app.models import BookingRequest
from tests.helpers import assert_error, count, expire, hold, parallel


@pytest.mark.case("B01")
def test_hold_and_confirm(client, service):
    request = hold(client)
    token = UUID(request["holdId"])
    assert token.version == 4
    raw = json.loads(service.redis.get(service.key(1)))
    assert raw == {"holdId": str(token), "clientId": "alice"}
    assert 0 < service.redis.pttl(service.key(1)) <= 30000
    response = client.post("/bookings", json=request)
    assert response.status_code == 201, response.text
    with service.repository.connect() as conn:
        rows = conn.execute("SELECT * FROM bookings").fetchall()
    assert len(rows) == 1
    assert rows[0]["id"] == UUID(response.json()["bookingId"])
    assert rows[0]["hold_id"] == token and rows[0]["client_id"] == "alice"


@pytest.mark.case("B02")
def test_concurrent_holds(client, service, hooks):
    gate = threading.Barrier(2, timeout=8)
    hooks.after_hold_read = gate.wait
    responses = parallel(*[
        lambda owner=owner: client.post("/holds", json={"resourceId": 1, "clientId": owner,
                                                       "ttlSeconds": 30})
        for owner in ["alice", "bob"]
    ])
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409], f"Должен победить один клиент, получено {statuses}"
    winner = next(r.json() for r in responses if r.status_code == 201)
    loser = next(r for r in responses if r.status_code == 409)
    assert_error(loser, 409, "RESOURCE_HELD")
    assert json.loads(service.redis.get(service.key(1)))["holdId"] == winner["holdId"]
    assert count(service) == 0


@pytest.mark.case("B03")
def test_expired(client, service):
    old = hold(client, ttl=1)
    expire(service)
    assert_error(client.post("/bookings", json=old), 409, "HOLD_EXPIRED_OR_INVALID")
    assert count(service) == 0
    new = hold(client, owner="bob")
    assert new["holdId"] != old["holdId"]
    assert_error(client.post("/bookings", json=old), 409, "HOLD_EXPIRED_OR_INVALID")
    assert json.loads(service.redis.get(service.key(1)))["holdId"] == new["holdId"]
    assert client.post("/bookings", json=new).status_code == 201
    assert count(service) == 1
    old_same_owner = hold(client, resource=2)
    expire(service, resource=2)
    new_same_owner = hold(client, resource=2)
    assert new_same_owner["holdId"] != old_same_owner["holdId"]
    assert_error(client.post("/bookings", json=old_same_owner), 409, "HOLD_EXPIRED_OR_INVALID")
    assert count(service, resource=2) == 0
    assert client.post("/bookings", json=new_same_owner).status_code == 201


@pytest.mark.case("B04")
def test_ownership(client, service):
    owned = hold(client)
    other = hold(client, resource=2, owner="alice")
    before = {resource: service.redis.get(service.key(resource)) for resource in [1, 2, 3]}
    invalid = [dict(owned, holdId=str(uuid4())), dict(owned, clientId="bob"),
               dict(owned, holdId=other["holdId"]),
               {"resourceId": 3, "clientId": "alice", "holdId": owned["holdId"]}]
    for request in invalid:
        assert_error(client.post("/bookings", json=request), 409, "HOLD_EXPIRED_OR_INVALID")
    assert count(service) == 0
    with service.repository.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM bookings").fetchone()["n"] == 0
    assert before == {resource: service.redis.get(service.key(resource)) for resource in before}
    assert client.post("/bookings", json=owned).status_code == 201


@pytest.mark.case("B05")
def test_repeat(client, service):
    owned = hold(client)
    assert client.post("/bookings", json=owned).status_code == 201
    assert_error(client.post("/bookings", json=owned), 409, "RESOURCE_ALREADY_BOOKED")
    assert count(service) == 1


@pytest.mark.case("B06")
def test_concurrent_confirm(client, service, hooks):
    owned = hold(client)
    hooks.before_booking_insert = threading.Barrier(2, timeout=8).wait
    results = parallel(lambda: client.post("/bookings", json=owned),
                       lambda: client.post("/bookings", json=owned))
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    assert_error(next(r for r in results if r.status_code == 409), 409, "RESOURCE_ALREADY_BOOKED")
    assert count(service) == 1, "В PostgreSQL оказались две подтверждённые брони"


@pytest.mark.case("B07")
def test_database_invariant(client, service):
    gate = threading.Barrier(2, timeout=8)

    def insert():
        try:
            with service.repository.connect() as conn:
                gate.wait()
                conn.execute("""INSERT INTO bookings(id,resource_id,client_id,hold_id)
                    VALUES (%s,1,'direct-sql',%s)""", (uuid4(), uuid4()))
            return "committed"
        except psycopg.errors.UniqueViolation:
            return "unique-conflict"

    results = parallel(insert, insert)
    assert sorted(results) == ["committed", "unique-conflict"], results
    assert count(service) == 1


@pytest.mark.case("B08")
def test_database_conflict_response(client, service, hooks, monkeypatch):
    owned = hold(client)

    def competing_commit():
        with service.repository.connect() as conn:
            conn.execute("""INSERT INTO bookings(id,resource_id,client_id,hold_id)
                VALUES (%s,1,'competitor',%s)""", (uuid4(), uuid4()))

    # Реальный commit после проверки отсутствия брони, до INSERT сервиса.
    hooks.before_booking_insert = competing_commit
    assert_error(client.post("/bookings", json=owned), 409, "RESOURCE_ALREADY_BOOKED")
    assert count(service) == 1
    assert client.get("/health").status_code == 200, "Ошибка не должна оставлять транзакцию сломанной"
    hooks.before_booking_insert = lambda: None
    other = hold(client, resource=2)
    with service.repository.connect() as conn:
        existing_id = conn.execute("SELECT id FROM bookings WHERE resource_id=1").fetchone()["id"]
    original_insert = service.repository.insert_booking

    def duplicate_primary_key(booking_id, request):
        original_insert(existing_id, request)

    # Реальное нарушение другого ограничения нельзя выдавать за занятый ресурс.
    monkeypatch.setattr(service.repository, "insert_booking", duplicate_primary_key)
    assert_error(client.post("/bookings", json=other), 500, "INTERNAL_ERROR")
    assert count(service, resource=2) == 0
    assert client.get("/health").status_code == 200


@pytest.mark.case("B09")
def test_process_restart(client, service, settings):
    owned = hold(client)
    response = client.post("/bookings", json=owned)
    assert response.status_code == 201
    path = f'/bookings/{response.json()["bookingId"]}'
    # Два отдельных интерпретатора, два запуска ASGI lifespan, те же PG/Redis.
    script = """
import json, os
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
with TestClient(create_app(Settings(**json.loads(os.environ['RESTART_SETTINGS'])))) as c:
    r = c.get(os.environ['RESTART_PATH'])
    assert r.status_code == 200, r.text
    print(r.text)
"""
    from dataclasses import asdict
    env = dict(os.environ, RESTART_SETTINGS=json.dumps(asdict(settings)), RESTART_PATH=path)
    for _ in range(2):
        process = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True,
                                 text=True, timeout=20)
        assert process.returncode == 0, process.stderr
        assert json.loads(process.stdout) == response.json()
    assert count(service) == 1


@pytest.mark.case("B10")
def test_unavailable_resources(client, service):
    owned = hold(client)
    assert_error(client.post("/holds", json={"resourceId": 1, "clientId": "alice", "ttlSeconds": 5}),
                 409, "RESOURCE_HELD")
    assert client.post("/bookings", json=owned).status_code == 201
    assert_error(client.post("/bookings", json=dict(owned, holdId=str(uuid4()))),
                 409, "RESOURCE_ALREADY_BOOKED")
    assert_error(client.post("/holds", json={"resourceId": 1, "clientId": "bob", "ttlSeconds": 5}),
                 409, "RESOURCE_ALREADY_BOOKED")
    assert_error(client.post("/holds", json={"resourceId": 999, "clientId": "alice", "ttlSeconds": 5}),
                 404, "RESOURCE_NOT_FOUND")
    assert_error(client.post("/bookings", json=dict(owned, resourceId=999)),
                 404, "RESOURCE_NOT_FOUND")
    assert_error(client.get(f"/bookings/{uuid4()}"), 404, "BOOKING_NOT_FOUND")
    assert count(service) == 1


@pytest.mark.case("E01")
def test_release(client, service, hooks):
    old = hold(client)
    assert_error(client.request("DELETE", "/holds", json=dict(old, holdId=str(uuid4()))),
                 409, "HOLD_EXPIRED_OR_INVALID")
    assert service.redis.exists(service.key(1))
    assert_error(client.request("DELETE", "/holds", json=dict(old, clientId="bob")),
                 409, "HOLD_EXPIRED_OR_INVALID")
    assert client.request("DELETE", "/holds", json=old).status_code == 204
    assert service.redis.get(service.key(1)) is None
    assert_error(client.request("DELETE", "/holds", json=old), 409, "HOLD_EXPIRED_OR_INVALID")
    assert_error(client.request("DELETE", "/holds", json=dict(old, resourceId=999)),
                 404, "RESOURCE_NOT_FOUND")
    confirmed = hold(client, resource=2)
    service.repository.insert_booking(uuid4(), BookingRequest(**confirmed))
    assert client.request("DELETE", "/holds", json=confirmed).status_code == 204
    assert service.redis.get(service.key(2)) is None
    assert count(service, resource=2) == 1, "Освобождение удержания не отменяет SQL-бронь"
    old = hold(client)
    expire(service)
    new = hold(client, owner="bob")
    assert_error(client.request("DELETE", "/holds", json=old), 409, "HOLD_EXPIRED_OR_INVALID")
    assert json.loads(service.redis.get(service.key(1)))["holdId"] == new["holdId"]
    assert client.request("DELETE", "/holds", json=new).status_code == 204
    old = hold(client)
    successor = {}

    def rotate():
        # Точка ДО атомарного compare-and-delete, ПОСЛЕ предварительного GET, если он есть.
        expire(service)
        successor.update(hold(client, owner="bob"))

    hooks.before_release_delete = rotate
    assert_error(client.request("DELETE", "/holds", json=old), 409, "HOLD_EXPIRED_OR_INVALID")
    assert json.loads(service.redis.get(service.key(1)))["holdId"] == successor["holdId"]
    assert count(service) == 0


@pytest.mark.case("E02")
def test_ttl_after_authorization(client, service, hooks):
    alice = hold(client, ttl=1)
    authorized = threading.Event()
    resume = threading.Event()
    lock = threading.Lock()
    first = True

    def pause_first():
        nonlocal first
        with lock:
            selected = first
            first = False
        if selected:
            authorized.set()
            assert resume.wait(timeout=10), "Клиент A не дождался разрешения продолжить"

    hooks.after_authorization = pause_first
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/bookings", json=alice)
        try:
            assert authorized.wait(timeout=5), "Клиент A не прошёл авторизацию"
            expire(service)
            bob = hold(client, owner="bob")
            result_b = client.post("/bookings", json=bob)
            assert result_b.status_code == 201, result_b.text
        finally:
            resume.set()
        result_a = pending.result(timeout=10)
    assert_error(result_a, 409, "RESOURCE_ALREADY_BOOKED")
    assert count(service) == 1
    with service.repository.connect() as conn:
        row = conn.execute("SELECT client_id, hold_id FROM bookings WHERE resource_id=1").fetchone()
    assert row["client_id"] == "bob" and str(row["hold_id"]) == bob["holdId"]
