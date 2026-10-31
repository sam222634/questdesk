-- ============================================================================
-- QuestDesk - Módulo 1: Vistas y Funciones Pequeñas Especializadas (SoC)
-- Cada función realiza una única responsabilidad sobre una tabla específica.
-- ============================================================================

-- Vista pre-ensamblada de resumen de tickets (jamás toca user_credentials)
CREATE OR REPLACE VIEW v_tickets_summary AS
SELECT
    t.id,
    t.ticket_code,
    t.title,
    t.description,
    q.slug AS queue_slug,
    q.name AS queue_name,
    s.name AS status_name,
    s.is_closed,
    p.name AS priority_name,
    p.weight AS priority_weight,
    t.assigned_user_id,
    u.user_uuid AS assignee_uuid,
    u.username AS assignee_username,
    u.display_name AS assignee_display_name,
    uh.manager_id AS assignee_manager_id,
    t.estimated_points,
    COALESCE((SELECT SUM(w.duration_minutes) FROM ticket_work_logs w WHERE w.ticket_id = t.id), 0)::INT AS total_minutes,
    (SELECT d.uri FROM ticket_documents d WHERE d.ticket_id = t.id AND d.doc_type = 'MARKDOWN_BITACORA' LIMIT 1) AS bitacora_uri,
    t.created_at,
    t.updated_at
FROM tickets t
JOIN ticket_queues q ON q.id = t.queue_id
JOIN ticket_statuses s ON s.id = t.status_id
JOIN ticket_priorities p ON p.id = t.priority_id
JOIN users u ON u.id = t.assigned_user_id
LEFT JOIN user_hierarchy uh ON uh.user_id = u.id;

-- ============================================================================
-- 0. Funciones Especializadas de Autenticación, Autorización y Usuarios
-- ============================================================================

-- 0.1 Autenticar en cada petición mediante hash SHA-256 de la API-Key
CREATE OR REPLACE FUNCTION fn_authenticate_by_key_hash(p_api_key_hash CHAR(64))
RETURNS TABLE (
    user_id INT,
    user_uuid UUID,
    username VARCHAR(50),
    display_name VARCHAR(100),
    role VARCHAR(20)
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id,
        u.user_uuid,
        u.username,
        u.display_name,
        COALESCE(uh.role, 'AGENT')::VARCHAR(20)
    FROM user_credentials uc
    JOIN users u ON u.id = uc.user_id
    LEFT JOIN user_hierarchy uh ON uh.user_id = u.id
    WHERE uc.api_key_hash = LOWER(BTRIM(p_api_key_hash))
      AND uc.is_revoked = FALSE
      AND u.is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Credencial inválida, revocada o usuario inactivo.'
            USING ERRCODE = 'invalid_authorization_specification';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 0.2 Resolver usuario destino por su UUID opaco (evita usar nombres en texto plano)
CREATE OR REPLACE FUNCTION fn_get_user_by_uuid(p_user_uuid UUID)
RETURNS TABLE (
    user_id INT,
    user_uuid UUID,
    username VARCHAR(50),
    display_name VARCHAR(100),
    role VARCHAR(20),
    manager_id INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id,
        u.user_uuid,
        u.username,
        u.display_name,
        COALESCE(uh.role, 'AGENT')::VARCHAR(20),
        uh.manager_id
    FROM users u
    LEFT JOIN user_hierarchy uh ON uh.user_id = u.id
    WHERE u.user_uuid = p_user_uuid AND u.is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El usuario con UUID "%" no existe o está inactivo.', p_user_uuid
            USING ERRCODE = 'no_data_found';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 0.3 Verificar si el solicitante tiene permiso sobre un ticket (Propio, Subordinado o ADMIN)
CREATE OR REPLACE FUNCTION fn_assert_ticket_access(
    p_ticket_assigned_user_id INT,
    p_requester_id INT,
    p_requester_role VARCHAR(20)
)
RETURNS VOID AS $$
DECLARE
    v_is_subordinate BOOLEAN;
BEGIN
    -- El ADMIN tiene visibilidad global
    IF UPPER(p_requester_role) = 'ADMIN' THEN
        RETURN;
    END IF;

    -- El dueño directo del ticket tiene acceso
    IF p_ticket_assigned_user_id = p_requester_id THEN
        RETURN;
    END IF;

    -- Verificar si el dueño del ticket es subordinado directo del solicitante
    SELECT EXISTS (
        SELECT 1
        FROM user_hierarchy uh
        WHERE uh.user_id = p_ticket_assigned_user_id
          AND uh.manager_id = p_requester_id
    ) INTO v_is_subordinate;

    IF v_is_subordinate THEN
        RETURN;
    END IF;

    RAISE EXCEPTION 'Acceso denegado: no tienes permisos para ver o modificar tickets de este usuario.'
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. Funciones de Catálogos y Reserva de Folio
-- ============================================================================

-- 1.1 Reservar siguiente folio secuencial de una cola activa (ej. "DEV-0001")
CREATE OR REPLACE FUNCTION fn_reserve_queue_folio(p_queue_slug VARCHAR(50))
RETURNS TABLE (
    queue_id INT,
    queue_slug VARCHAR(50),
    queue_name VARCHAR(100),
    ticket_code VARCHAR(30)
) AS $$
DECLARE
    v_row RECORD;
BEGIN
    UPDATE ticket_queues tq
    SET next_seq = tq.next_seq + 1
    WHERE LOWER(tq.slug) = LOWER(BTRIM(p_queue_slug)) AND tq.is_active = TRUE
    RETURNING tq.id, tq.slug, tq.prefix, tq.name, tq.next_seq - 1 AS seq_num
    INTO v_row;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La cola "%" no existe o está inactiva.', p_queue_slug
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY SELECT
        v_row.id,
        v_row.slug,
        v_row.name,
        (v_row.prefix || '-' || LPAD(v_row.seq_num::TEXT, 4, '0'))::VARCHAR(30);
END;
$$ LANGUAGE plpgsql;

-- 1.2 Obtener prioridad por nombre
CREATE OR REPLACE FUNCTION fn_get_priority(p_priority_name VARCHAR(30))
RETURNS TABLE (
    priority_id INT,
    priority_name VARCHAR(30),
    weight INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT tp.id, tp.name, tp.weight
    FROM ticket_priorities tp
    WHERE UPPER(tp.name) = UPPER(BTRIM(p_priority_name));

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La prioridad "%" no es válida.', p_priority_name
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 1.3 Obtener estado por nombre
CREATE OR REPLACE FUNCTION fn_get_status(p_status_name VARCHAR(50))
RETURNS TABLE (
    status_id INT,
    status_name VARCHAR(50),
    is_closed BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT ts.id, ts.name, ts.is_closed
    FROM ticket_statuses ts
    WHERE UPPER(ts.name) = UPPER(BTRIM(p_status_name));

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El estado "%" no es válido.', p_status_name
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 2. Funciones Especializadas de Escritura por Tabla
-- ============================================================================

-- 2.1 Insertar fila únicamente en la tabla tickets
CREATE OR REPLACE FUNCTION fn_insert_ticket(
    p_ticket_code VARCHAR(30),
    p_title VARCHAR(255),
    p_description TEXT,
    p_queue_id INT,
    p_status_id INT,
    p_priority_id INT,
    p_assigned_user_id INT,
    p_estimated_points INT
)
RETURNS TABLE (
    id BIGINT,
    ticket_code VARCHAR(30),
    title VARCHAR(255),
    description TEXT,
    assigned_user_id INT,
    estimated_points INT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    IF p_title IS NULL OR BTRIM(p_title) = '' THEN
        RAISE EXCEPTION 'El título del ticket no puede estar vacío.'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    IF p_description IS NULL OR BTRIM(p_description) = '' THEN
        RAISE EXCEPTION 'La descripción del ticket no puede estar vacía.'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY
    INSERT INTO tickets (
        ticket_code, title, description, queue_id, status_id, priority_id, assigned_user_id, estimated_points
    )
    VALUES (
        p_ticket_code, BTRIM(p_title), BTRIM(p_description), p_queue_id, p_status_id, p_priority_id, p_assigned_user_id, p_estimated_points
    )
    RETURNING tickets.id, tickets.ticket_code, tickets.title, tickets.description,
              tickets.assigned_user_id, tickets.estimated_points, tickets.created_at, tickets.updated_at;
END;
$$ LANGUAGE plpgsql;

-- 2.2 Validar anticipadamente que un Message-ID no esté duplicado antes de reservar folio
CREATE OR REPLACE FUNCTION fn_assert_unique_message_id(p_message_id VARCHAR(255) DEFAULT NULL)
RETURNS VOID AS $$
DECLARE
    v_clean_msg_id VARCHAR(255);
BEGIN
    v_clean_msg_id := NULLIF(BTRIM(p_message_id), '');

    IF v_clean_msg_id IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM ticket_sources ts WHERE ts.message_id = v_clean_msg_id) THEN
            RAISE EXCEPTION 'El correo con Message-ID "%" ya fue registrado previamente.', v_clean_msg_id
                USING ERRCODE = 'unique_violation';
        END IF;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 2.3 Insertar fila únicamente en ticket_sources
CREATE OR REPLACE FUNCTION fn_insert_source(
    p_ticket_id BIGINT,
    p_channel VARCHAR(30),
    p_sender_email VARCHAR(255) DEFAULT NULL,
    p_message_id VARCHAR(255) DEFAULT NULL,
    p_raw_headers JSONB DEFAULT NULL
)
RETURNS BIGINT AS $$
DECLARE
    v_source_id BIGINT;
    v_clean_msg_id VARCHAR(255);
BEGIN
    v_clean_msg_id := NULLIF(BTRIM(p_message_id), '');
    PERFORM fn_assert_unique_message_id(v_clean_msg_id);

    INSERT INTO ticket_sources (ticket_id, channel, sender_email, message_id, raw_headers)
    VALUES (p_ticket_id, UPPER(BTRIM(p_channel)), p_sender_email, v_clean_msg_id, p_raw_headers)
    RETURNING id INTO v_source_id;

    RETURN v_source_id;
END;
$$ LANGUAGE plpgsql;

-- 2.3 Insertar fila únicamente en ticket_documents
CREATE OR REPLACE FUNCTION fn_insert_document(
    p_ticket_id BIGINT,
    p_doc_type VARCHAR(50),
    p_uri VARCHAR(1000),
    p_sync_status VARCHAR(30) DEFAULT 'SYNCED'
)
RETURNS BIGINT AS $$
DECLARE
    v_doc_id BIGINT;
BEGIN
    INSERT INTO ticket_documents (ticket_id, doc_type, uri, sync_status)
    VALUES (p_ticket_id, UPPER(BTRIM(p_doc_type)), BTRIM(p_uri), UPPER(BTRIM(p_sync_status)))
    RETURNING id INTO v_doc_id;

    RETURN v_doc_id;
END;
$$ LANGUAGE plpgsql;

-- 2.4 Insertar fila únicamente en ticket_audit_log
CREATE OR REPLACE FUNCTION fn_insert_audit(
    p_ticket_id BIGINT,
    p_action VARCHAR(50),
    p_old_value JSONB,
    p_new_value JSONB,
    p_actor VARCHAR(100) DEFAULT 'system'
)
RETURNS BIGINT AS $$
DECLARE
    v_audit_id BIGINT;
BEGIN
    INSERT INTO ticket_audit_log (ticket_id, action, old_value, new_value, actor)
    VALUES (
        p_ticket_id,
        UPPER(BTRIM(p_action)),
        p_old_value,
        p_new_value,
        COALESCE(NULLIF(BTRIM(p_actor), ''), 'system')
    )
    RETURNING id INTO v_audit_id;

    RETURN v_audit_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 3. Funciones Especializadas de Estado, Delegación y Sesiones de Trabajo
-- ============================================================================

-- 3.1 Bloquear fila del ticket para transición segura (FOR UPDATE)
CREATE OR REPLACE FUNCTION fn_lock_ticket_by_code(p_ticket_code VARCHAR(30))
RETURNS TABLE (
    ticket_id BIGINT,
    ticket_code VARCHAR(30),
    current_status VARCHAR(50),
    assigned_user_id INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT t.id, t.ticket_code, s.name, t.assigned_user_id
    FROM tickets t
    JOIN ticket_statuses s ON s.id = t.status_id
    WHERE UPPER(t.ticket_code) = UPPER(BTRIM(p_ticket_code))
    FOR UPDATE OF t;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El ticket "%" no fue encontrado.', p_ticket_code
            USING ERRCODE = 'no_data_found';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 3.2 Actualizar columna status_id de un ticket
CREATE OR REPLACE FUNCTION fn_set_ticket_status(p_ticket_id BIGINT, p_status_id INT)
RETURNS VOID AS $$
BEGIN
    UPDATE tickets SET status_id = p_status_id WHERE id = p_ticket_id;
END;
$$ LANGUAGE plpgsql;

-- 3.3 Delegar / Reasignar un ticket a otro usuario
CREATE OR REPLACE FUNCTION fn_set_ticket_assignee(p_ticket_id BIGINT, p_new_user_id INT)
RETURNS VOID AS $$
BEGIN
    UPDATE tickets SET assigned_user_id = p_new_user_id WHERE id = p_ticket_id;
END;
$$ LANGUAGE plpgsql;

-- 3.4 Sincronizar sesión de tiempo automática en ticket_work_logs según el nuevo estado
CREATE OR REPLACE FUNCTION fn_sync_work_log_on_status(
    p_ticket_id BIGINT,
    p_user_id INT,
    p_status_name VARCHAR(50),
    p_is_closed BOOLEAN,
    p_notes TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    IF p_status_name = 'IN_PROGRESS' THEN
        IF NOT EXISTS (SELECT 1 FROM ticket_work_logs w WHERE w.ticket_id = p_ticket_id AND w.ended_at IS NULL) THEN
            INSERT INTO ticket_work_logs (ticket_id, user_id, notes)
            VALUES (p_ticket_id, p_user_id, COALESCE(p_notes, 'Sesión iniciada al activar ticket'));
        END IF;
    ELSIF p_is_closed OR p_status_name = 'BLOCKED' THEN
        UPDATE ticket_work_logs
        SET ended_at = NOW()
        WHERE ticket_id = p_ticket_id AND ended_at IS NULL;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 3.5 Registrar bloque de tiempo manual en ticket_work_logs
CREATE OR REPLACE FUNCTION fn_insert_work_log(
    p_ticket_id BIGINT,
    p_user_id INT,
    p_started_at TIMESTAMP WITH TIME ZONE,
    p_ended_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    p_notes TEXT DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    user_id INT,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_minutes INT,
    notes TEXT
) AS $$
BEGIN
    IF p_ended_at IS NOT NULL AND p_ended_at < COALESCE(p_started_at, NOW()) THEN
        RAISE EXCEPTION 'La fecha de término no puede ser anterior a la fecha de inicio.'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY
    INSERT INTO ticket_work_logs (ticket_id, user_id, started_at, ended_at, notes)
    VALUES (p_ticket_id, p_user_id, COALESCE(p_started_at, NOW()), p_ended_at, p_notes)
    RETURNING ticket_work_logs.id, ticket_work_logs.user_id, ticket_work_logs.started_at,
              ticket_work_logs.ended_at, ticket_work_logs.duration_minutes, ticket_work_logs.notes;
END;
$$ LANGUAGE plpgsql;
