-- ============================================================================
-- 00_create_database.sql
-- Preparacion de la base library_db y del usuario de aplicacion library_user
-- para un despliegue desde cero del Ejercicio 02.
--
-- Este script NUNCA contiene una contraseña real y NUNCA ejecuta operaciones
-- destructivas (no hay DROP DATABASE ni DROP ROLE). No usa "postgres" como
-- usuario de aplicacion: library_user solo recibe los privilegios minimos
-- que la aplicacion Node.js necesita para operar (RNF-12).
--
-- El script esta dividido en TRES partes que se ejecutan en momentos
-- distintos, con un usuario administrativo (ej. "postgres"), porque los
-- GRANT sobre tablas/secuencias/rutinas concretas solo tienen sentido una
-- vez que esos objetos existen:
--
--   PARTE A - una sola vez, conectado a la base de mantenimiento
--             (normalmente "postgres"), ANTES de db/01_schema.sql:
--             crea la base library_db y el rol library_user.
--
--   PARTE B - una sola vez, conectado YA a library_db, tambien ANTES de
--             db/01_schema.sql: privilegios sobre la base/schema y
--             privilegios POR DEFECTO para objetos que se creen despues
--             (asi, cuando 01_schema.sql / 04_stored_procedures.sql corran
--             con el usuario administrativo, library_user ya queda con
--             acceso automatico a lo que se cree).
--
--   PARTE C - repetible, conectado a library_db, DESPUES de haber corrido
--             db/01_schema.sql y db/04_stored_procedures.sql (o cada vez que
--             se agreguen objetos nuevos fuera de una sesion que ya tenia
--             los default privileges de la PARTE B activos): otorga acceso
--             explicito sobre los objetos que YA existen, ya que
--             ALTER DEFAULT PRIVILEGES solo aplica a objetos creados
--             DESPUES de definirse.
--
-- Manejo de contraseña (RNF-02):
--   Este script NO trae la contraseña de library_user escrita. Se pasa como
--   variable de psql en el momento de ejecutar, por ejemplo:
--
--     export LIBRARY_USER_PASSWORD='valor-secreto-fuera-del-repositorio'
--     psql -U postgres -d postgres \
--          -v app_password="$LIBRARY_USER_PASSWORD" \
--          -f db/00_create_database.sql
--
--   La sintaxis :'app_password' interpola esa variable como literal SQL de
--   forma segura (no es concatenacion de texto); si se ejecuta sin -v, psql
--   fallara con un error claro en vez de crear el rol sin contraseña.
--
-- Idempotencia: CREATE DATABASE y CREATE ROLE fallaran con un error de
-- "ya existe" si se re-ejecutan sobre un entorno ya preparado. Eso es
-- intencional (evita silenciosamente recrear/perder configuracion); si ya
-- existen, omite esas dos sentencias puntuales y continua con el resto del
-- script, o usa ALTER ROLE library_user WITH PASSWORD :'app_password'; para
-- rotar la contraseña de un rol existente.
-- ============================================================================


-- ============================================================================
-- PARTE A -- ejecutar UNA VEZ con un usuario administrativo (ej. "postgres"),
-- conectado a la base de mantenimiento (normalmente "postgres"), ANTES de
-- db/01_schema.sql.
-- ============================================================================

CREATE DATABASE library_db;

-- Rol de aplicacion, sin privilegios de superusuario, sin capacidad de crear
-- bases/roles nuevos. LOGIN habilita la conexion desde Node.js (`pg`).
-- La contraseña llega mediante la variable psql "app_password" (ver
-- encabezado); este archivo nunca contiene un valor real.
CREATE ROLE library_user WITH LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;


-- ============================================================================
-- PARTE B -- ejecutar UNA VEZ con un usuario administrativo, conectado YA a
-- library_db (por ejemplo agregando \connect library_db antes de esta parte,
-- o ejecutando el script de nuevo con -d library_db), ANTES de
-- db/01_schema.sql.
-- ============================================================================

-- \connect library_db

-- Permite a library_user conectarse a esta base y usar el schema public
-- (donde vive todo el modelo). No se otorga CREATE sobre la base ni el
-- schema: library_user no necesita crear tablas nuevas, solo operar sobre
-- las que ya definen db/01_schema.sql y db/04_stored_procedures.sql.
GRANT CONNECT ON DATABASE library_db TO library_user;
GRANT USAGE ON SCHEMA public TO library_user;

-- Privilegios POR DEFECTO para objetos que este mismo usuario administrativo
-- cree DESPUES de este punto (tablas de 01_schema.sql, secuencias de las
-- columnas *SERIAL, funciones/procedures de 04_stored_procedures.sql).
-- Si "FOR ROLE" se omite, PostgreSQL usa el rol que ejecuta la sentencia
-- (el usuario administrativo), que es exactamente quien va a crear esos
-- objetos en los pasos siguientes.
-- Minimo privilegio: solo lectura/escritura de filas (no DDL) sobre tablas,
-- solo lo necesario para usar columnas *SERIAL sobre secuencias, y solo
-- ejecucion sobre rutinas.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO library_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO library_user;

-- ON ROUTINES cubre tanto FUNCTION como PROCEDURE (PostgreSQL 11+).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT EXECUTE ON ROUTINES TO library_user;


-- ============================================================================
-- PARTE C -- ejecutar con un usuario administrativo, conectado a library_db,
-- DESPUES de aplicar db/01_schema.sql, db/06_views.sql y db/04_stored_procedures.sql
-- (orden final documentado en el encabezado de db/01_schema.sql), y de
-- nuevo cada vez que se agreguen objetos que no hayan heredado la PARTE B,
-- (por ejemplo si otro rol distinto al que corrio la PARTE B crea tablas).
-- Es idempotente en si misma (repetirla no es destructivo), aunque las
-- sentencias de la PARTE A no deben repetirse tal cual (ver nota de
-- idempotencia arriba).
-- ============================================================================

-- \connect library_db

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO library_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO library_user;
GRANT EXECUTE ON ALL ROUTINES IN SCHEMA public TO library_user;

-- Las vistas de db/06_views.sql (vw_catalogo_libros, vw_libro_autores, etc.)
-- son objetos de solo lectura sobre las tablas base; PostgreSQL las incluye
-- dentro de "ALL TABLES IN SCHEMA public", asi que quedan cubiertas por el
-- primer GRANT de esta parte sin una sentencia adicional.

-- No se otorgan privilegios de DDL (CREATE/ALTER/DROP) ni TRUNCATE a
-- library_user: la aplicacion Node.js solo necesita leer y escribir filas y
-- ejecutar las rutinas de db/04_stored_procedures.sql, nunca modificar la
-- estructura del esquema.
