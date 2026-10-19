-- Снимок схемы до студенческих изменений: проверяем обновление существующей БД.
-- Этот тестовый файл не заменяет db/init.sql и не содержит решения.
CREATE TABLE resources (
    id integer PRIMARY KEY,
    name text NOT NULL
);
CREATE TABLE bookings (
    id uuid PRIMARY KEY,
    resource_id integer NOT NULL REFERENCES resources(id),
    client_id text NOT NULL,
    hold_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'CONFIRMED' CHECK (status = 'CONFIRMED'),
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO resources(id, name) VALUES
    (1, 'Место в аудитории 101'),
    (2, 'Место в аудитории 102'),
    (3, 'Место в аудитории 103');
