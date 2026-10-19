import argparse

from redis import Redis

from app.config import Settings
from app.repository import Repository


def main():
    parser = argparse.ArgumentParser(description="Удалить брони только локального учебного стенда")
    parser.add_argument("--confirm-local-reset", action="store_true", required=True)
    parser.parse_args()
    settings = Settings.from_env()
    with Repository(settings).connect() as conn:
        conn.execute("TRUNCATE bookings")
    with Redis.from_url(settings.redis_url) as redis:
        for key in redis.scan_iter(match=f"{settings.key_prefix}hold:*"):
            redis.delete(key)
    print("Учебные брони и удержания удалены; ресурсы и миграции сохранены")


if __name__ == "__main__":
    main()
