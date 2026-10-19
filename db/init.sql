CREATE TABLE IF NOT EXISTS resources (
    id integer PRIMARY KEY,
    name text NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    id uuid PRIMARY KEY,
    resource_id integer NOT NULL REFERENCES resources(id),
    client_id text NOT NULL,
    hold_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'CONFIRMED' CHECK (status = 'CONFIRMED'),
    created_at timestamptz NOT NULL DEFAULT now()
    -- TODO B: здесь пока нет окончательной защиты resource_id от дубликатов.
);
INSERT INTO resources(id, name) VALUES
    (1, 'Место в аудитории 101'),
    (2, 'Место в аудитории 102'),
    (3, 'Место в аудитории 103')
ON CONFLICT (id) DO NOTHING;
