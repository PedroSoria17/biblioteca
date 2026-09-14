-- ============================================================================
-- 01_schema.sql
-- Esquema de base de datos: Libreria en linea (PostgreSQL) - library_db
--
-- Version final para el Ejercicio 02. Parte de sql/schema.sql (version
-- historica conservada como evidencia) y separa de forma ordenada la funcion
-- y el trigger de auditoria de fecha, que ahora viven en db/05_triggers.sql.
--
-- Orden de instalacion real (corregido en la auditoria del Prompt 04: varias
-- functions de 04_stored_procedures.sql leen vistas de 06_views.sql, asi que
-- las vistas deben existir primero). Los nombres de archivo 00-06 identifican
-- el ENTREGABLE, no el orden literal de ejecucion:
--   00_create_database.sql   (Partes A y B, con usuario administrativo)
--   01_schema.sql            (este archivo)
--   02_seed_30_per_table.sql (solo sobre una base limpia; ver advertencia en su encabezado)
--   06_views.sql             (antes de 04: varias functions dependen de estas vistas)
--   04_stored_procedures.sql
--   05_triggers.sql
--   00_create_database.sql   (Parte C, repetible, ya con tablas/rutinas creadas)
--
-- 03_all_quieries_before_stored_procedures.sql es documental (snapshot del
-- SQL previo a la migracion) y nunca se ejecuta como parte de este lote.
--
-- Ver justificacion de dependencias funcionales/multivaluadas y normalizacion
-- en data/db_design_solution.md.
--
-- Ejecutar conectado a la base library_db (ver db/00_create_database.sql).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Usuarios registrados. Como maximo un usuario puede ser administrador
-- (se garantiza con un indice unico parcial, no con una regla de aplicacion).
-- ----------------------------------------------------------------------------
CREATE TABLE usuarios (
    usuario_id       BIGSERIAL PRIMARY KEY,
    nombre_completo  VARCHAR(150) NOT NULL,
    email            VARCHAR(255) NOT NULL UNIQUE,
    password_hash    VARCHAR(255) NOT NULL,
    es_administrador BOOLEAN NOT NULL DEFAULT FALSE,
    activo           BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Garantiza que exista a lo sumo un administrador en todo el sistema.
-- Regla de negocio critica: se resuelve a nivel de base (indice unico
-- parcial), no solo en la aplicacion, para que se cumpla incluso si una
-- operacion administrativa o manual intenta saltarse la validacion de Node.
CREATE UNIQUE INDEX ux_usuarios_un_solo_administrador
    ON usuarios (es_administrador)
    WHERE es_administrador;

-- ----------------------------------------------------------------------------
-- Catalogos independientes: formato y categoria.
-- Se modelan como tablas separadas (no una tabla generica "tipo") porque
-- representan dominios distintos y evolucionan de forma independiente.
-- ----------------------------------------------------------------------------
CREATE TABLE formatos (
    formato_id   SMALLSERIAL PRIMARY KEY,
    nombre       VARCHAR(50) NOT NULL UNIQUE   -- ej: Tapa dura, Tapa blanda, Digital, Audiolibro
);

CREATE TABLE categorias (
    categoria_id SMALLSERIAL PRIMARY KEY,
    nombre       VARCHAR(80) NOT NULL UNIQUE   -- ej: Infantil, Academico, Comic, Adulto
);

CREATE TABLE generos (
    genero_id    SMALLSERIAL PRIMARY KEY,
    nombre       VARCHAR(80) NOT NULL UNIQUE   -- ej: Fantasia, Terror, Romance, Historia
);

CREATE TABLE autores (
    autor_id     BIGSERIAL PRIMARY KEY,
    nombre       VARCHAR(120) NOT NULL,
    apellido     VARCHAR(120) NOT NULL,
    pais         VARCHAR(80)
);

CREATE TABLE conceptos (
    concepto_id  BIGSERIAL PRIMARY KEY,
    nombre       VARCHAR(150) NOT NULL UNIQUE  -- termino/concepto reutilizable entre libros
);

-- ----------------------------------------------------------------------------
-- Libro: atributos de valor unico determinados funcionalmente por el ISBN.
-- Autor, genero, imagenes y conceptos NO viven aqui: son dependencias
-- multivaluadas independientes entre si (isbn ->> autor | genero | imagen | concepto),
-- por lo que se separan en tablas puente para cumplir 4FN.
-- ----------------------------------------------------------------------------
CREATE TABLE libros (
    isbn              VARCHAR(20) PRIMARY KEY
        CHECK (isbn ~ '^(97[89])?[0-9]{9}[0-9X]$|^(97[89]-)?[0-9]{1,5}-[0-9]{1,7}-[0-9]{1,7}-[0-9X]$'),
    titulo            VARCHAR(300) NOT NULL,
    anio_publicacion  SMALLINT NOT NULL CHECK (anio_publicacion BETWEEN 1450 AND 2100),
    precio            NUMERIC(10,2) NOT NULL CHECK (precio >= 0),
    stock             INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    formato_id        SMALLINT NOT NULL REFERENCES formatos(formato_id) ON DELETE RESTRICT,
    categoria_id      SMALLINT NOT NULL REFERENCES categorias(categoria_id) ON DELETE RESTRICT,
    fecha_creacion    TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_libros_titulo ON libros USING gin (to_tsvector('spanish', titulo));

-- NOTA: la funcion fn_set_fecha_actualizacion() y el trigger
-- trg_libros_set_fecha_actualizacion que mantienen libros.fecha_actualizacion
-- al dia se crean en db/05_triggers.sql, DESPUES de este script, para
-- mantener separadas la definicion de estructura (aqui) y los triggers.
-- La columna fecha_actualizacion ya queda declarada arriba para que ese
-- trigger pueda ejecutarse sin cambios adicionales al esquema.

-- ----------------------------------------------------------------------------
-- Un libro puede tener varios autores y un autor varios libros (N:M).
-- ----------------------------------------------------------------------------
CREATE TABLE libro_autor (
    isbn       VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    autor_id   BIGINT NOT NULL REFERENCES autores(autor_id) ON DELETE RESTRICT,
    orden      SMALLINT NOT NULL DEFAULT 1,  -- orden de aparicion del autor en el libro
    PRIMARY KEY (isbn, autor_id)
);

-- ----------------------------------------------------------------------------
-- Un libro puede pertenecer a varios generos (N:M).
-- ----------------------------------------------------------------------------
CREATE TABLE libro_genero (
    isbn       VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    genero_id  SMALLINT NOT NULL REFERENCES generos(genero_id) ON DELETE RESTRICT,
    PRIMARY KEY (isbn, genero_id)
);

-- ----------------------------------------------------------------------------
-- Un libro puede tener varias imagenes (1:N). La imagen depende solo del libro.
-- ----------------------------------------------------------------------------
CREATE TABLE imagenes_libro (
    imagen_id         BIGSERIAL PRIMARY KEY,
    isbn              VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    url               VARCHAR(500) NOT NULL,
    texto_alternativo VARCHAR(255),
    orden             SMALLINT NOT NULL DEFAULT 1,
    es_portada        BOOLEAN NOT NULL DEFAULT FALSE
);

-- A lo sumo una imagen marcada como portada por libro. Regla de integridad
-- resuelta con indice unico parcial (declarativo) en vez de un trigger,
-- siguiendo la guia de usar la herramienta declarativa mas apropiada.
CREATE UNIQUE INDEX ux_imagenes_una_portada_por_libro
    ON imagenes_libro (isbn)
    WHERE es_portada;

-- ----------------------------------------------------------------------------
-- Un libro puede definir muchos conceptos y el mismo concepto puede repetirse
-- en distintos libros con una definicion propia: la definicion depende de la
-- combinacion (isbn, concepto_id), no de isbn ni de concepto_id por separado.
-- ----------------------------------------------------------------------------
CREATE TABLE libro_concepto (
    isbn         VARCHAR(20) NOT NULL REFERENCES libros(isbn) ON DELETE CASCADE,
    concepto_id  BIGINT NOT NULL REFERENCES conceptos(concepto_id) ON DELETE RESTRICT,
    definicion   TEXT NOT NULL,
    PRIMARY KEY (isbn, concepto_id)
);

COMMIT;
