from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]


class Repository:
    def __init__(self, settings):
        self.settings = settings

    def connect(self):
        # Имя схемы берётся из настроек теста, а не из HTTP-запроса.
        conn = psycopg.connect(self.settings.database_url, row_factory=dict_row,
                               connect_timeout=5)
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.settings.schema)))
        return conn

    def migrate(self):
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema()))")
            conn.execute((ROOT / "db/init.sql").read_text())
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY)")
            for path in sorted((ROOT / "db/migrations").glob("*.sql")):
                if not conn.execute("SELECT 1 FROM schema_migrations WHERE name=%s", (path.name,)).fetchone():
                    conn.execute(path.read_text())
                    conn.execute("INSERT INTO schema_migrations VALUES (%s)", (path.name,))

    def resource_exists(self, resource_id):
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM resources WHERE id=%s", (resource_id,)).fetchone() is not None

    def has_booking(self, resource_id):
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM bookings WHERE resource_id=%s", (resource_id,)).fetchone() is not None

    def list_resources(self):
        with self.connect() as conn:
            return conn.execute('''SELECT r.id AS "resourceId", r.name,
                EXISTS(SELECT 1 FROM bookings b WHERE b.resource_id=r.id) AS booked
                FROM resources r ORDER BY r.id''').fetchall()

    def insert_booking(self, booking_id, request):
        # Контекст соединения делает COMMIT при успехе и ROLLBACK при исключении.
        with self.connect() as conn:
            conn.execute("""INSERT INTO bookings(id, resource_id, client_id, hold_id)
                VALUES (%s, %s, %s, %s)""",
                         (booking_id, request.resourceId, request.clientId, request.holdId))

    def get_booking(self, booking_id):
        with self.connect() as conn:
            return conn.execute('''SELECT id AS "bookingId", resource_id AS "resourceId", status
                FROM bookings WHERE id=%s''', (booking_id,)).fetchone()
