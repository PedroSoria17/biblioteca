-- ============================================================================
-- 07_microservices_auth_orders_payments.sql
-- Migracion para la actividad de microservicios (login, books/soap, users,
-- authors, orders, payments) sobre la MISMA base library_db.
--
-- Agrega:
--   1. roles                 (USER=1, ADMIN=2)
--   2. usuarios.role_id      (FK a roles) + backfill desde es_administrador
--      + sincronizacion automatica role_id <-> es_administrador
--   3. pedidos               (orders)
--   4. pedido_detalle        (order items, con precio historico)
--   5. pagos                 (payments)
--   6. indices, constraints, triggers y GRANT a library_user
--
-- Reglas de esta migracion:
--   - NO modifica data/01_schema.sql ni ningun script anterior.
--   - NO borra tablas, columnas ni filas. es_administrador se CONSERVA:
--     el monolito Node (apps/web-monolito01) y sus funciones/procedures
--     (04_stored_procedures.sql) siguen usandolo tal cual.
--   - La regla "a lo sumo un administrador" sigue garantizada por
--     ux_usuarios_un_solo_administrador (01_schema.sql). role_id queda
--     amarrado a es_administrador con un CHECK + trigger, asi que tampoco
--     puede haber dos role_id = ADMIN.
--   - Idempotente: puede ejecutarse varias veces sin error ni efectos
--     adicionales (IF NOT EXISTS, ON CONFLICT DO NOTHING, bloques DO que
--     verifican pg_constraint/pg_proc antes de crear).
--   - Todo corre en UNA transaccion: si algo falla, no queda nada a medias.
--
-- Requisitos previos (orden documentado en 01_schema.sql):
--   01_schema.sql, 06_views.sql, 04_stored_procedures.sql, 05_triggers.sql
--   y, si se usa el microservicio de login, login_microservice.sql.
--   Requiere PostgreSQL 12+ (columna GENERATED ... STORED).
--
-- Aplicar con un usuario administrativo (el dueno de las tablas), NO con
-- library_user (que no tiene privilegios DDL):
--   psql -U <admin> -d library_db -v ON_ERROR_STOP=1 \
--        -f data/07_microservices_auth_orders_payments.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. roles
-- role_id NO es SERIAL: los valores son fijos porque viajan en el claim
-- role_id del JWT y los microservicios los comparan como constantes
-- (apps/services/shared/library_shared/roles.py).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    role_id      SMALLINT PRIMARY KEY CHECK (role_id > 0),
    codigo       VARCHAR(30) NOT NULL UNIQUE CHECK (codigo = upper(codigo) AND codigo <> ''),
    descripcion  VARCHAR(255)
);

INSERT INTO roles (role_id, codigo, descripcion) VALUES
    (1, 'USER',  'Usuario registrado: consulta el catalogo y gestiona sus propios pedidos y pagos.'),
    (2, 'ADMIN', 'Administrador: gestion completa de libros, autores, usuarios, pedidos y pagos.')
ON CONFLICT (role_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. usuarios.role_id
-- ADD COLUMN con DEFAULT constante (PostgreSQL 11+) no reescribe la tabla:
-- todas las filas existentes quedan con role_id = 1 (USER) y el backfill de
-- abajo corrige solo al administrador.
-- ----------------------------------------------------------------------------
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS role_id SMALLINT NOT NULL DEFAULT 1;

-- Backfill: solo toca filas inconsistentes, asi que re-ejecutarlo no pisa
-- roles futuros (p. ej. un role_id = 3 asignado a un usuario no admin).
UPDATE usuarios SET role_id = 2 WHERE es_administrador AND role_id <> 2;
UPDATE usuarios SET role_id = 1 WHERE NOT es_administrador AND role_id = 2;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_usuarios_role' AND conrelid = 'usuarios'::regclass
    ) THEN
        ALTER TABLE usuarios
            ADD CONSTRAINT fk_usuarios_role
            FOREIGN KEY (role_id) REFERENCES roles (role_id) ON DELETE RESTRICT;
    END IF;

    -- Invariante: es_administrador y role_id = ADMIN dicen siempre lo mismo.
    -- Junto con ux_usuarios_un_solo_administrador, impide dos ADMIN.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_usuarios_role_admin_sync' AND conrelid = 'usuarios'::regclass
    ) THEN
        ALTER TABLE usuarios
            ADD CONSTRAINT ck_usuarios_role_admin_sync
            CHECK (es_administrador = (role_id = 2));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_usuarios_role_id ON usuarios (role_id);

-- Sincronizacion role_id <-> es_administrador.
-- Necesidad real (criterio de 05_triggers.sql): el monolito sigue escribiendo
-- SOLO es_administrador (fn_usuario_crear, sp_usuario_transferir_administracion)
-- y los microservicios escribiran role_id. Sin este trigger, cualquiera de
-- los dos caminos violaria ck_usuarios_role_admin_sync. No es expresable con
-- un DEFAULT ni con una columna generada, porque ambas columnas deben seguir
-- siendo escribibles.
--   INSERT: admin si cualquiera de las dos lo indica.
--   UPDATE: manda la columna que cambio; si cambian ambas, manda
--           es_administrador (contrato historico del monolito).
CREATE OR REPLACE FUNCTION fn_usuarios_sincronizar_rol()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.es_administrador OR NEW.role_id = 2 THEN
            NEW.es_administrador := TRUE;
            NEW.role_id := 2;
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.es_administrador IS DISTINCT FROM OLD.es_administrador THEN
        IF NEW.es_administrador THEN
            NEW.role_id := 2;
        ELSIF NEW.role_id = 2 THEN
            NEW.role_id := 1;
        END IF;
    ELSIF NEW.role_id IS DISTINCT FROM OLD.role_id THEN
        NEW.es_administrador := (NEW.role_id = 2);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_usuarios_sincronizar_rol ON usuarios;

CREATE TRIGGER trg_usuarios_sincronizar_rol
    BEFORE INSERT OR UPDATE OF es_administrador, role_id ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION fn_usuarios_sincronizar_rol();

-- ----------------------------------------------------------------------------
-- Funcion de fecha_actualizacion. 05_triggers.sql ya define
-- fn_set_fecha_actualizacion() para libros; se REUTILIZA. Solo se crea
-- (con el mismo cuerpo) si este script corre en una base sin 05_triggers.sql,
-- nunca se reemplaza la existente.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.proname = 'fn_set_fecha_actualizacion' AND n.nspname = 'public'
    ) THEN
        EXECUTE $f$
            CREATE FUNCTION fn_set_fecha_actualizacion()
            RETURNS TRIGGER AS $body$
            BEGIN
                NEW.fecha_actualizacion := now();
                RETURN NEW;
            END;
            $body$ LANGUAGE plpgsql
        $f$;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 3. pedidos (orders)
--
-- Estados (codigos estables en ingles, igual que los usara la API REST):
--   pending   -> creado, esperando pago (unico estado editable).
--   paid      -> existe un pago aprobado por el total.
--   completed -> entregado / cerrado.
--   cancelled -> cancelado (desde pending o paid, con reembolso).
-- Las transiciones validas las aplicara el microservicio orders; la base
-- solo garantiza que el estado sea uno de estos valores.
--
-- total se mantiene AUTOMATICAMENTE desde pedido_detalle (trigger de abajo):
-- se guarda para poder listar pedidos sin sumar lineas, pero nunca puede
-- divergir de la suma de subtotales.
--
-- ON DELETE RESTRICT hacia usuarios: el historial de compras no se borra en
-- cascada. Un usuario CON pedidos no puede eliminarse fisicamente (debe
-- desactivarse con usuarios.activo = FALSE).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pedidos (
    pedido_id            BIGSERIAL PRIMARY KEY,
    usuario_id           BIGINT NOT NULL
        CONSTRAINT fk_pedidos_usuario REFERENCES usuarios (usuario_id) ON DELETE RESTRICT,
    estado               VARCHAR(20) NOT NULL DEFAULT 'pending'
        CONSTRAINT ck_pedidos_estado CHECK (estado IN ('pending', 'paid', 'completed', 'cancelled')),
    total                NUMERIC(12,2) NOT NULL DEFAULT 0
        CONSTRAINT ck_pedidos_total CHECK (total >= 0),
    fecha_creacion       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pedidos_usuario_id ON pedidos (usuario_id);
CREATE INDEX IF NOT EXISTS ix_pedidos_estado ON pedidos (estado);

DROP TRIGGER IF EXISTS trg_pedidos_set_fecha_actualizacion ON pedidos;

CREATE TRIGGER trg_pedidos_set_fecha_actualizacion
    BEFORE UPDATE ON pedidos
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_fecha_actualizacion();

-- ----------------------------------------------------------------------------
-- 4. pedido_detalle (order items)
--
-- precio_unitario es el precio AL MOMENTO DE LA COMPRA (copiado de
-- libros.precio dentro de la transaccion que crea el pedido); no se lee de
-- libros despues, asi un cambio de precio no altera pedidos historicos.
-- subtotal es una columna generada: se deriva siempre de cantidad *
-- precio_unitario, sin poder quedar inconsistente.
--
-- PK (pedido_id, isbn): un libro aparece una sola vez por pedido (se
-- incrementa cantidad en vez de repetir la linea).
-- ON DELETE RESTRICT hacia libros: un libro ya vendido no puede borrarse
-- fisicamente sin perder historial.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pedido_detalle (
    pedido_id        BIGINT NOT NULL
        CONSTRAINT fk_pedido_detalle_pedido REFERENCES pedidos (pedido_id) ON DELETE CASCADE,
    isbn             VARCHAR(20) NOT NULL
        CONSTRAINT fk_pedido_detalle_libro REFERENCES libros (isbn) ON DELETE RESTRICT,
    cantidad         INTEGER NOT NULL
        CONSTRAINT ck_pedido_detalle_cantidad CHECK (cantidad > 0),
    precio_unitario  NUMERIC(10,2) NOT NULL
        CONSTRAINT ck_pedido_detalle_precio CHECK (precio_unitario >= 0),
    subtotal         NUMERIC(12,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED,
    PRIMARY KEY (pedido_id, isbn)
);

-- "En que pedidos aparece este libro" (la PK ya cubre la busqueda por pedido).
CREATE INDEX IF NOT EXISTS ix_pedido_detalle_isbn ON pedido_detalle (isbn);

CREATE OR REPLACE FUNCTION fn_pedidos_recalcular_total()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        UPDATE pedidos
           SET total = (SELECT COALESCE(SUM(subtotal), 0) FROM pedido_detalle WHERE pedido_id = OLD.pedido_id)
         WHERE pedido_id = OLD.pedido_id;
    END IF;

    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        UPDATE pedidos
           SET total = (SELECT COALESCE(SUM(subtotal), 0) FROM pedido_detalle WHERE pedido_id = NEW.pedido_id)
         WHERE pedido_id = NEW.pedido_id;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pedido_detalle_recalcular_total ON pedido_detalle;

CREATE TRIGGER trg_pedido_detalle_recalcular_total
    AFTER INSERT OR UPDATE OR DELETE ON pedido_detalle
    FOR EACH ROW
    EXECUTE FUNCTION fn_pedidos_recalcular_total();

-- ----------------------------------------------------------------------------
-- 5. pagos (payments)
--
-- Estados:
--   pending  -> registrado, sin confirmar.
--   approved -> confirmado (requiere fecha_pago).
--   rejected -> rechazado.
--   refunded -> reembolsado (de un pago antes aprobado).
-- Un pedido puede tener varios intentos de pago (p. ej. uno rechazado y
-- otro aprobado), pero a lo sumo UN pago aprobado (indice unico parcial).
--
-- referencia: identificador unico del pago (lo genera el microservicio
-- payments o la pasarela); evita registrar dos veces la misma operacion.
--
-- No se guarda usuario_id: se obtiene via pedidos.usuario_id (evita
-- duplicar el dato y que diverja).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pagos (
    pago_id              BIGSERIAL PRIMARY KEY,
    pedido_id            BIGINT NOT NULL
        CONSTRAINT fk_pagos_pedido REFERENCES pedidos (pedido_id) ON DELETE RESTRICT,
    monto                NUMERIC(12,2) NOT NULL
        CONSTRAINT ck_pagos_monto CHECK (monto > 0),
    metodo_pago          VARCHAR(30) NOT NULL
        CONSTRAINT ck_pagos_metodo CHECK (metodo_pago IN ('credit_card', 'debit_card', 'bank_transfer', 'cash')),
    estado               VARCHAR(20) NOT NULL DEFAULT 'pending'
        CONSTRAINT ck_pagos_estado CHECK (estado IN ('pending', 'approved', 'rejected', 'refunded')),
    referencia           VARCHAR(100) NOT NULL
        CONSTRAINT uq_pagos_referencia UNIQUE,
    fecha_pago           TIMESTAMPTZ,
    fecha_creacion       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_pagos_fecha_pago CHECK (
        (estado IN ('approved', 'refunded') AND fecha_pago IS NOT NULL)
        OR estado IN ('pending', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS ix_pagos_pedido_id ON pagos (pedido_id);
CREATE INDEX IF NOT EXISTS ix_pagos_estado ON pagos (estado);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pagos_un_aprobado_por_pedido
    ON pagos (pedido_id)
    WHERE estado = 'approved';

DROP TRIGGER IF EXISTS trg_pagos_set_fecha_actualizacion ON pagos;

CREATE TRIGGER trg_pagos_set_fecha_actualizacion
    BEFORE UPDATE ON pagos
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_fecha_actualizacion();

-- ----------------------------------------------------------------------------
-- 6. Privilegios para library_user (mismo patron que login_microservice.sql).
-- Redundante si la PARTE B de 00_create_database.sql ya dejo default
-- privileges, pero inofensivo. Se omite sin error si el rol no existe.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'library_user') THEN
        -- roles es un catalogo fijo: solo lectura para la aplicacion.
        GRANT SELECT ON roles TO library_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON pedidos, pedido_detalle, pagos TO library_user;
        GRANT USAGE, SELECT ON SEQUENCE pedidos_pedido_id_seq, pagos_pago_id_seq TO library_user;
    END IF;
END $$;

COMMIT;

-- ============================================================================
-- Verificacion manual (no forma parte de la migracion):
--
--   SELECT * FROM roles ORDER BY role_id;
--   SELECT role_id, es_administrador, count(*) FROM usuarios GROUP BY 1, 2;
--   -- Debe devolver 0 filas:
--   SELECT usuario_id FROM usuarios WHERE es_administrador <> (role_id = 2);
--   \d usuarios
--   \d pedidos
--   \d pedido_detalle
--   \d pagos
-- ============================================================================
