"""Последовательный пример через настоящий HTTP API; работает внутри контейнера."""
import argparse
import json

import httpx


def main():
    parser = argparse.ArgumentParser(description="Показать последовательное бронирование")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--resource", type=int, default=1)
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=10) as client:
        response = client.post("/holds", json={"resourceId": args.resource, "clientId": "alice",
                                               "ttlSeconds": 60})
        print("Удержание:", response.status_code, response.text)
        response.raise_for_status()
        response = client.post("/bookings", json={"resourceId": args.resource, "clientId": "alice",
                                                  "holdId": response.json()["holdId"]})
        print("Бронирование:", response.status_code, response.text)
        response.raise_for_status()
        print("Проверка SQL через GET:", json.dumps(client.get(
            f'/bookings/{response.json()["bookingId"]}').json(), ensure_ascii=False))


if __name__ == "__main__":
    main()
