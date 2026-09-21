-- ============================================================================
-- login_microservice.sql
-- Extensiones de esquema para el nuevo microservicio de login/autenticacion
-- (apps/services/login), que se conecta a la MISMA base library_db ya
-- utilizada por el monolito (apps/web-monolito01) y el servicio SOAP
-- (apps/services/soap).
--
-- Este script SOLO agrega estructuras nuevas. No modifica, renombra,
-- elimina ni recrea ninguna tabla, columna, restriccion o fila existente
-- (en particular, `usuarios` de data/01_schema.sql permanece intacta: la
-- tabla que crea aqui abajo, `usuario_detalle`, la EXTIENDE via una relacion
-- 1:1 en vez de modificarla). No contiene DROP DATABASE, DROP TABLE,
-- DROP ROLE, TRUNCATE, DELETE ni UPDATE sobre datos existentes.
--
-- Requisito previo: `usuarios` (data/01_schema.sql) y, si se desea otorgar
-- privilegios automaticamente, el rol `library_user`
-- (data/00_create_database.sql) deben existir antes de ejecutar este script.
--
-- Aplicar con, por ejemplo:
--   psql -U <admin> -d library_db -f data/login_microservice.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- usuario_detalle: informacion adicional 1:1 para usuarios registrados a
-- traves del nuevo microservicio (nombre desglosado en nombre/apellidos y
-- estado de verificacion del correo). No duplica el email: ya vive en
-- usuarios.email. usuario_id es a la vez PK y FK, lo que garantiza la
-- relacion 1:1 con usuarios.
-- ----------------------------------------------------------------------------
CREATE TABLE usuario_detalle (
    usuario_id          BIGINT PRIMARY KEY
        REFERENCES usuarios (usuario_id) ON DELETE CASCADE,
    nombre               VARCHAR(100) NOT NULL,
    apellido_paterno     VARCHAR(100) NOT NULL,
    apellido_materno     VARCHAR(100),
    email_verificado     BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_creacion       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Los usuarios legados (creados antes del nuevo microservicio) no tendran
-- fila en esta tabla. El servicio de login no debe bloquear su
-- autenticacion por esa sola ausencia (ver apps/services/login/README.md).

-- ----------------------------------------------------------------------------
-- usuario_verificacion_email: tokens de verificacion de correo emitidos por
-- POST /register. Solo se almacena el hash del token (nunca el valor en
-- texto plano) junto con su expiracion y, una vez usado, la fecha en que se
-- verifico.
-- ----------------------------------------------------------------------------
CREATE TABLE usuario_verificacion_email (
    verificacion_id      BIGSERIAL PRIMARY KEY,
    usuario_id            BIGINT NOT NULL
        REFERENCES usuarios (usuario_id) ON DELETE CASCADE,
    token_hash             VARCHAR(128) NOT NULL UNIQUE,
    fecha_expiracion      TIMESTAMPTZ NOT NULL,
    fecha_verificacion   TIMESTAMPTZ,
    fecha_creacion         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Acelera "buscar tokens pendientes de un usuario"; la busqueda por
-- token_hash ya queda indexada por la restriccion UNIQUE de arriba.
CREATE INDEX ix_usuario_verificacion_email_usuario_id
    ON usuario_verificacion_email (usuario_id);

-- ----------------------------------------------------------------------------
-- Privilegios: library_user es el rol de aplicacion definido en
-- data/00_create_database.sql (PARTE A). Si estas tablas se crearon en una
-- sesion donde ya estaban activos los ALTER DEFAULT PRIVILEGES de la
-- PARTE B de ese script, estos GRANT son redundantes pero inofensivos. El
-- bloque se salta por completo (sin error) si ese rol no existe todavia,
-- por ejemplo si el microservicio de login usara un rol de aplicacion
-- propio en vez de library_user: en ese caso, otorga los privilegios
-- equivalentes a ese rol por separado.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'library_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON usuario_detalle, usuario_verificacion_email
            TO library_user;

        GRANT USAGE, SELECT
            ON SEQUENCE usuario_verificacion_email_verificacion_id_seq
            TO library_user;
    END IF;
END $$;

COMMIT;
