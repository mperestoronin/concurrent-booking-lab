from uuid import UUID

import pytest
import psycopg
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from tests.helpers import assert_error, count, hold


@pytest.mark.case("S01")
def test_dependencies(client, service, monkeypatch):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": "ok", "redis": "ok"}

    def postgres_unavailable():
        raise psycopg.OperationalError("Учебный сбой PostgreSQL")

    def redis_unavailable():
        raise RedisConnectionError("Учебный сбой Redis")

    def redis_command_error():
        raise ResponseError("Учебная ошибка команды Redis")

    with monkeypatch.context() as patch:
        patch.setattr(service.repository, "connect", postgres_unavailable)
        assert_error(client.get("/health"), 503, "DEPENDENCY_UNAVAILABLE")
    with monkeypatch.context() as patch:
        patch.setattr(service.redis, "ping", redis_unavailable)
        assert_error(client.get("/health"), 503, "DEPENDENCY_UNAVAILABLE")
    with monkeypatch.context() as patch:
        patch.setattr(service.redis, "ping", redis_command_error)
        assert_error(client.get("/health"), 500, "INTERNAL_ERROR")
    assert client.get("/health").status_code == 200


@pytest.mark.case("S02")
def test_seed(client):
    response = client.get("/resources")
    assert response.status_code == 200
    assert {r["resourceId"] for r in response.json()} >= {1, 2, 3}
    assert all(not r["booked"] for r in response.json())


@pytest.mark.case("S03")
def test_sequential(client, service):
    request = hold(client)
    UUID(request["holdId"])
    response = client.post("/bookings", json=request)
    assert response.status_code == 201, response.text
    UUID(response.json()["bookingId"])
    assert response.json()["status"] == "CONFIRMED"
    assert count(service) == 1
    assert client.get(f'/bookings/{response.json()["bookingId"]}').json() == response.json()


@pytest.mark.case("S04")
def test_validation(client):
    invalid = [
        {}, {"resourceId": True, "clientId": "alice", "ttlSeconds": 5},
        {"resourceId": 1, "clientId": "", "ttlSeconds": 5},
        {"resourceId": 1, "clientId": "alice", "ttlSeconds": 0},
        {"resourceId": 1, "clientId": "alice", "ttlSeconds": 61},
        {"resourceId": "1", "clientId": "alice", "ttlSeconds": 5},
        {"resourceId": 1, "clientId": "alice", "ttlSeconds": 5, "extra": 1},
    ]
    for body in invalid:
        assert_error(client.post("/holds", json=body), 422, "VALIDATION_ERROR")
    assert_error(client.post("/holds", content="{", headers={"Content-Type": "application/json"}),
                 422, "VALIDATION_ERROR")
    assert_error(client.post("/bookings", json={"resourceId": 1, "clientId": "alice", "holdId": "bad"}),
                 422, "VALIDATION_ERROR")
    assert_error(client.get("/missing"), 404, "NOT_FOUND")
    assert_error(client.get("/bookings/not-a-uuid"), 422, "VALIDATION_ERROR")
    response = client.get("/holds")
    assert_error(response, 405, "METHOD_NOT_ALLOWED")
    assert "POST" in response.headers["allow"]
    for resource, ttl in [(2, 1), (3, 60)]:
        hold(client, resource=resource, ttl=ttl)


@pytest.mark.case("S05")
def test_public_contract(client):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert set(paths) == {"/health", "/resources", "/holds", "/bookings", "/bookings/{booking_id}"}
    assert_error(client.post("/debug/barrier"), 404, "NOT_FOUND")
    for route, method in [("/holds", "post"), ("/bookings", "post"), ("/holds", "delete")]:
        responses = paths[route][method]["responses"]
        for status in ["409", "422", "500", "503"]:
            assert responses[status]["content"]["application/json"]["schema"]["$ref"].endswith(
                "/ErrorResponse")
    assert set(spec["components"]["schemas"]["ErrorResponse"]["properties"]) == {"error"}
