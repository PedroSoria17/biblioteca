-- ============================================================================
-- Ejercicio 03 - Modulo SOAP para clasificacion Cloud
-- Archivo: soap_module.sql
-- Base existente: library_db (Ejercicio 02)
-- Objetivo: agregar persistencia propia del modulo SOAP SIN modificar
-- las tablas funcionales existentes del monolito Node.js.
-- ============================================================================

BEGIN;

-- Aisla los objetos del nuevo modulo respecto al esquema public del monolito.
CREATE SCHEMA IF NOT EXISTS soap_module;

-- ----------------------------------------------------------------------------
-- 1) CLASIFICADORES
-- Representa a la persona que utiliza un cliente SOAP para clasificar conceptos.
-- NO reutiliza public.usuarios del monolito.
-- El correo funciona como identidad logica del clasificador.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS soap_module.clasificadores (
    clasificador_id BIGSERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    apellidos       VARCHAR(150) NOT NULL,
    correo          VARCHAR(255) NOT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_clasificadores_nombre_no_vacio
        CHECK (btrim(nombre) <> ''),

    CONSTRAINT ck_clasificadores_apellidos_no_vacios
        CHECK (btrim(apellidos) <> ''),

    CONSTRAINT ck_clasificadores_correo_basico
        CHECK (
            btrim(correo) <> ''
            AND position('@' IN correo) > 1
        )
);

-- Un mismo correo no puede representar dos clasificadores.
-- LOWER evita duplicados por diferencias de mayusculas/minusculas.
CREATE UNIQUE INDEX IF NOT EXISTS ux_clasificadores_correo_ci
    ON soap_module.clasificadores (lower(correo));


-- ----------------------------------------------------------------------------
-- 2) CLIENTES_SERVIDOS
-- Representa la aplicacion/instancia cliente SOAP, NO a la persona.
-- Ejemplos conceptuales:
--   tipo_cliente = 'desktop-python' / identificador = 'tkinter-596630'
--   tipo_cliente = 'java-wsimport'  / identificador = 'interop-596630'
-- Permite contabilizar peticiones atendidas por cada cliente.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS soap_module.clientes_servidos (
    cliente_id          BIGSERIAL PRIMARY KEY,
    tipo_cliente        VARCHAR(60) NOT NULL,
    identificador       VARCHAR(120) NOT NULL,
    numero_peticiones   BIGINT NOT NULL DEFAULT 0,
    primera_peticion    TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultima_peticion     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_clientes_tipo_no_vacio
        CHECK (btrim(tipo_cliente) <> ''),

    CONSTRAINT ck_clientes_identificador_no_vacio
        CHECK (btrim(identificador) <> ''),

    CONSTRAINT ck_clientes_numero_peticiones
        CHECK (numero_peticiones >= 0),

    CONSTRAINT uq_clientes_tipo_identificador
        UNIQUE (tipo_cliente, identificador)
);


-- ----------------------------------------------------------------------------
-- 3) CLASIFICACIONES_CLOUD
-- Registra la clasificacion IaaS/PaaS/SaaS/FaaS hecha por una persona.
--
-- La FK compuesta apunta a public.libro_concepto(isbn, concepto_id), que es
-- exactamente la relacion real del Ejercicio 02 donde vive la definicion.
--
-- Se usa ON DELETE CASCADE para NO bloquear las operaciones del monolito:
-- si el monolito elimina un libro o una relacion libro-concepto, PostgreSQL
-- puede limpiar la clasificacion SOAP asociada sin impedir el DELETE original.
-- Este comportamiento debe documentarse como trade-off de compartir BD.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS soap_module.clasificaciones_cloud (
    clasificacion_id    BIGSERIAL PRIMARY KEY,
    clasificador_id     BIGINT NOT NULL,
    isbn                VARCHAR(20) NOT NULL,
    concepto_id         BIGINT NOT NULL,
    cliente_id          BIGINT NOT NULL,
    modelo_cloud        VARCHAR(4) NOT NULL,
    fecha_clasificacion TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_clasificaciones_clasificador
        FOREIGN KEY (clasificador_id)
        REFERENCES soap_module.clasificadores(clasificador_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_clasificaciones_cliente
        FOREIGN KEY (cliente_id)
        REFERENCES soap_module.clientes_servidos(cliente_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_clasificaciones_libro_concepto
        FOREIGN KEY (isbn, concepto_id)
        REFERENCES public.libro_concepto(isbn, concepto_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_clasificaciones_modelo_cloud
        CHECK (modelo_cloud IN ('IaaS', 'PaaS', 'SaaS', 'FaaS')),

    -- Requisito literal del ejercicio:
    -- el mismo clasificador no puede registrar dos veces el mismo concepto.
    CONSTRAINT uq_clasificaciones_clasificador_concepto
        UNIQUE (clasificador_id, concepto_id)
);

-- Consultas de progreso por clasificador.
CREATE INDEX IF NOT EXISTS ix_clasificaciones_clasificador_fecha
    ON soap_module.clasificaciones_cloud
       (clasificador_id, fecha_clasificacion DESC);

-- Tarea 1: ObtenerEstadisticasPorModelo.
CREATE INDEX IF NOT EXISTS ix_clasificaciones_modelo_cloud
    ON soap_module.clasificaciones_cloud (modelo_cloud);

-- Integracion y verificacion por libro/concepto.
CREATE INDEX IF NOT EXISTS ix_clasificaciones_libro_concepto
    ON soap_module.clasificaciones_cloud (isbn, concepto_id);


-- ----------------------------------------------------------------------------
-- DOCUMENTACION EN EL CATALOGO DE POSTGRESQL
-- ----------------------------------------------------------------------------
COMMENT ON SCHEMA soap_module IS
    'Objetos propios del modulo SOAP del Ejercicio 03.';

COMMENT ON TABLE soap_module.clasificadores IS
    'Personas que clasifican conceptos mediante clientes SOAP; independiente de public.usuarios.';

COMMENT ON TABLE soap_module.clasificaciones_cloud IS
    'Clasificaciones Cloud IaaS/PaaS/SaaS/FaaS vinculadas al catalogo real del monolito.';

COMMENT ON TABLE soap_module.clientes_servidos IS
    'Aplicaciones/instancias cliente SOAP y contador de peticiones atendidas.';

COMMIT;

-- ============================================================================
-- MINIMO PRIVILEGIO - EJECUTAR COMO ADMINISTRADOR DESPUES DE CREAR EL ROLE
-- ============================================================================
-- No guardar una contrasena real en este archivo.
-- Crear el role y asignarle la contrasena fuera del repositorio, por ejemplo
-- mediante \password desde psql.
--
-- ROLE sugerido: library_soap_user
--
-- GRANT CONNECT ON DATABASE library_db TO library_soap_user;
-- GRANT USAGE ON SCHEMA public TO library_soap_user;
-- GRANT USAGE ON SCHEMA soap_module TO library_soap_user;
--
-- -- Solo lectura de los datos del monolito que necesita SOAP.
-- GRANT SELECT ON public.libros TO library_soap_user;
-- GRANT SELECT ON public.conceptos TO library_soap_user;
-- GRANT SELECT ON public.libro_concepto TO library_soap_user;
-- GRANT SELECT ON public.categorias TO library_soap_user;
--
-- -- Lecturas adicionales requeridas por el catalogo REST bilingue
-- -- (01_prompt_bilingue.md): GET /books, /books/{isbn}, /books-with-images.
-- GRANT SELECT ON public.formatos TO library_soap_user;
-- GRANT SELECT ON public.imagenes_libro TO library_soap_user;
--
-- -- Tablas propias del modulo.
-- GRANT SELECT, INSERT, UPDATE ON soap_module.clasificadores TO library_soap_user;
-- GRANT SELECT, INSERT, UPDATE ON soap_module.clientes_servidos TO library_soap_user;
-- GRANT SELECT, INSERT ON soap_module.clasificaciones_cloud TO library_soap_user;
--
-- -- Secuencias BIGSERIAL del modulo.
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA soap_module TO library_soap_user;
--
-- IMPORTANTE:
-- No otorgar SELECT sobre public.usuarios ni acceso general a todas las tablas
-- del monolito. Tampoco otorgar CREATE/ALTER/DROP al usuario de la aplicacion.
