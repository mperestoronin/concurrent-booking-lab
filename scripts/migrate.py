from app.config import Settings
from app.repository import Repository

if __name__ == "__main__":
    Repository(Settings.from_env()).migrate()
    print("Схема и миграции применены")
