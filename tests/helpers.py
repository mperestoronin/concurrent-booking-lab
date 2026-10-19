import time
from concurrent.futures import ThreadPoolExecutor


def hold(client, resource=1, owner="alice", ttl=30):
    result = client.post("/holds", json={"resourceId": resource, "clientId": owner,
                                        "ttlSeconds": ttl})
    assert result.status_code == 201, result.text
    assert set(result.json()) == {"resourceId", "holdId", "expiresInSeconds"}
    assert result.json()["resourceId"] == resource
    assert result.json()["expiresInSeconds"] == ttl
    return {"resourceId": resource, "clientId": owner, "holdId": result.json()["holdId"]}


def count(service, resource=1):
    with service.repository.connect() as conn:
        return conn.execute("SELECT count(*) AS n FROM bookings WHERE resource_id=%s",
                            (resource,)).fetchone()["n"]


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def parallel(*calls):
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(call) for call in calls]
        return [future.result(timeout=20) for future in futures]


def expire(service, resource=1):
    # Настоящее истечение Redis; wall-clock ожидание ограничено 3 секундами.
    key = service.key(resource)
    assert service.redis.pexpire(key, 30), "Нет ключа для проверки TTL"
    deadline = time.monotonic() + 3
    while service.redis.exists(key) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert service.redis.get(key) is None, "Redis не удалил истёкший ключ"
