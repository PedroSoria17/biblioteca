-- ============================================================================
-- Esquema de base de datos: Libreria en linea (PostgreSQL)
-- Ver justificacion de dependencias funcionales/multivaluadas y normalizacion
-- en data/db_design_solution.md
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

-- Mantiene fecha_actualizacion al dia en cada UPDATE.
CREATE OR REPLACE FUNCTION fn_set_fecha_actualizacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_libros_set_fecha_actualizacion
    BEFORE UPDATE ON libros
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_fecha_actualizacion();

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

-- A lo sumo una imagen marcada como portada por libro.
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
