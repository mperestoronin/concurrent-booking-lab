import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    schema: str = "public"
    key_prefix: str = "booking-lab:"

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.getenv("DATABASE_URL", "postgresql://booking:local-lab-only@localhost/booking"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        )
