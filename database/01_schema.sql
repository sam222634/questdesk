-- ============================================================================
-- QuestDesk - Módulo 1: Esquema Relacional Normalizado (PostgreSQL 16)
-- ============================================================================

-- 1. Catálogo de Colas / Áreas
CREATE TABLE IF NOT EXISTS ticket_queues (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) UNIQUE NOT NULL,      -- 'general', 'infra', 'dev', 'personal'
    prefix VARCHAR(10) UNIQUE NOT NULL,    -- 'GEN', 'INF', 'DEV', 'PER'
    name VARCHAR(100) NOT NULL,
    description TEXT,
    next_seq INT NOT NULL DEFAULT 1,       -- Contador secuencial por cola
    is_active BOOLEAN DEFAULT TRUE
);

-- 2. Catálogo de Estados
CREATE TABLE IF NOT EXISTS ticket_statuses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,      -- 'NEW', 'ASSIGNED', 'IN_PROGRESS', 'BLOCKED', 'RESOLVED', 'CLOSED'
    is_closed BOOLEAN DEFAULT FALSE,
    sort_order INT DEFAULT 0
);

-- 3. Catálogo de Prioridades
CREATE TABLE IF NOT EXISTS ticket_priorities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(30) UNIQUE NOT NULL,      -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    weight INT NOT NULL DEFAULT 1
);

-- 4. Entidad Central: Tickets
CREATE TABLE IF NOT EXISTS tickets (
    id BIGSERIAL PRIMARY KEY,
    ticket_code VARCHAR(30) UNIQUE NOT NULL, -- ej: "DEV-0001"
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    queue_id INT NOT NULL REFERENCES ticket_queues(id),
    status_id INT NOT NULL REFERENCES ticket_statuses(id),
    priority_id INT NOT NULL REFERENCES ticket_priorities(id),
    estimated_points INT DEFAULT 1 CHECK (estimated_points >= 1 AND estimated_points <= 10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Submódulo de Origen (Aislamiento de procedencia / Correo / CLI / Web)
CREATE TABLE IF NOT EXISTS ticket_sources (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT UNIQUE NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    channel VARCHAR(30) NOT NULL,          -- 'EMAIL', 'CLI', 'WEB_UI', 'API'
    sender_email VARCHAR(255),
    message_id VARCHAR(255) UNIQUE,        -- RFC Message-ID para evitar duplicar correos
    raw_headers JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Submódulo de Tiempos y Cuantificación
CREATE TABLE IF NOT EXISTS ticket_work_logs (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_minutes INT GENERATED ALWAYS AS (
        CASE
            WHEN ended_at IS NOT NULL THEN GREATEST(1, EXTRACT(EPOCH FROM (ended_at - started_at))::INT / 60)
            ELSE NULL
        END
    ) STORED,
    notes TEXT
);

-- 7. Submódulo de Documentos y Bitácora Markdown
CREATE TABLE IF NOT EXISTS ticket_documents (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    doc_type VARCHAR(50) NOT NULL,         -- 'MARKDOWN_BITACORA', 'LOG_FILE', 'EXTERNAL_URL'
    uri VARCHAR(1000) NOT NULL,            -- ej: "bitacoras/DEV-0001.md"
    sync_status VARCHAR(30) DEFAULT 'SYNCED',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (ticket_id, uri)
);

-- 8. Trazabilidad e Historial Inmutable (Auditoría)
CREATE TABLE IF NOT EXISTS ticket_audit_log (
    id BIGSERIAL PRIMARY KEY,
    ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,           -- 'CREATED', 'STATUS_CHANGED', 'PRIORITY_CHANGED', 'TIME_LOGGED'
    old_value JSONB,
    new_value JSONB,
    actor VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status_id);
CREATE INDEX IF NOT EXISTS idx_tickets_queue ON tickets(queue_id);
CREATE INDEX IF NOT EXISTS idx_tickets_code ON tickets(ticket_code);
CREATE INDEX IF NOT EXISTS idx_work_logs_ticket ON ticket_work_logs(ticket_id);

-- ============================================================================
-- Triggers: Actualización de timestamps y Bus de Eventos nativo (pg_notify)
-- ============================================================================
CREATE OR REPLACE FUNCTION set_ticket_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tickets_updated_at ON tickets;
CREATE TRIGGER trg_tickets_updated_at
BEFORE UPDATE ON tickets
FOR EACH ROW EXECUTE FUNCTION set_ticket_updated_at();

CREATE OR REPLACE FUNCTION notify_ticket_event()
RETURNS TRIGGER AS $$
DECLARE
    payload JSON;
    event_name TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        event_name := 'ticket.created';
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.status_id IS DISTINCT FROM NEW.status_id THEN
            event_name := 'ticket.status_changed';
        ELSE
            event_name := 'ticket.updated';
        END IF;
    END IF;

    payload := json_build_object(
        'event', event_name,
        'ticket_id', NEW.id,
        'ticket_code', NEW.ticket_code,
        'status_id', NEW.status_id,
        'queue_id', NEW.queue_id,
        'priority_id', NEW.priority_id,
        'estimated_points', NEW.estimated_points,
        'timestamp', NOW()
    );

    PERFORM pg_notify('ticket_events', payload::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ticket_events ON tickets;
CREATE TRIGGER trg_ticket_events
AFTER INSERT OR UPDATE ON tickets
FOR EACH ROW EXECUTE FUNCTION notify_ticket_event();

-- ============================================================================
-- Datos Semilla Iniciales (Catálogos Base)
-- ============================================================================
INSERT INTO ticket_queues (slug, prefix, name, description) VALUES
    ('general', 'GEN', 'General', 'Cola general de tareas y pendientes'),
    ('infra', 'INF', 'Infraestructura y Sistemas', 'Servidores, redes, despliegues y soporte'),
    ('dev', 'DEV', 'Desarrollo', 'Código, corrección de bugs y arquitectura'),
    ('personal', 'PER', 'Personal', 'Responsabilidades y objetivos personales')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO ticket_statuses (name, is_closed, sort_order) VALUES
    ('NEW', FALSE, 10),
    ('ASSIGNED', FALSE, 20),
    ('IN_PROGRESS', FALSE, 30),
    ('BLOCKED', FALSE, 40),
    ('RESOLVED', TRUE, 50),
    ('CLOSED', TRUE, 60)
ON CONFLICT (name) DO NOTHING;

INSERT INTO ticket_priorities (name, weight) VALUES
    ('LOW', 1),
    ('MEDIUM', 2),
    ('HIGH', 3),
    ('CRITICAL', 5)
ON CONFLICT (name) DO NOTHING;
