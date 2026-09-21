-- ============================================================================
-- Ejercicio 03 - Views y routines del modulo SOAP
-- Requiere ejecutar primero: sql/soap_module.sql
-- NO modifica las tablas existentes del monolito.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Vista contractual interna del catalogo clasificable.
-- Evita que Python conozca joins del modelo 4FN.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW soap_module.vw_catalogo_clasificable AS
SELECT
    l.isbn,
    l.titulo AS titulo_libro,
    cat.nombre AS categoria,
    c.concepto_id,
    c.nombre AS concepto,
    lc.definicion
FROM public.libro_concepto AS lc
JOIN public.libros AS l
    ON l.isbn = lc.isbn
JOIN public.conceptos AS c
    ON c.concepto_id = lc.concepto_id
JOIN public.categorias AS cat
    ON cat.categoria_id = l.categoria_id;


-- ----------------------------------------------------------------------------
-- Obtener o actualizar clasificador por correo.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION soap_module.fn_clasificador_guardar(
    p_nombre VARCHAR,
    p_apellidos VARCHAR,
    p_correo VARCHAR
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF btrim(p_nombre) = ''
       OR btrim(p_apellidos) = ''
       OR btrim(p_correo) = '' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P1000',
            MESSAGE = 'INVALID_REQUEST';
    END IF;

    INSERT INTO soap_module.clasificadores (
        nombre,
        apellidos,
        correo
    )
    VALUES (
        btrim(p_nombre),
        btrim(p_apellidos),
        lower(btrim(p_correo))
    )
    ON CONFLICT (lower(correo))
    DO UPDATE SET
        nombre = EXCLUDED.nombre,
        apellidos = EXCLUDED.apellidos
    RETURNING clasificador_id
    INTO v_id;

    RETURN v_id;
END;
$$;


-- ----------------------------------------------------------------------------
-- Registrar que una aplicacion cliente realizo una peticion.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION soap_module.fn_cliente_registrar_peticion(
    p_tipo_cliente VARCHAR,
    p_identificador VARCHAR
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF btrim(p_tipo_cliente) = ''
       OR btrim(p_identificador) = '' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P1000',
            MESSAGE = 'INVALID_REQUEST';
    END IF;

    INSERT INTO soap_module.clientes_servidos (
        tipo_cliente,
        identificador,
        numero_peticiones
    )
    VALUES (
        btrim(p_tipo_cliente),
        btrim(p_identificador),
        1
    )
    ON CONFLICT (tipo_cliente, identificador)
    DO UPDATE SET
        numero_peticiones =
            soap_module.clientes_servidos.numero_peticiones + 1,
        ultima_peticion = now()
    RETURNING cliente_id
    INTO v_id;

    RETURN v_id;
END;
$$;


-- ----------------------------------------------------------------------------
-- Conceptos pendientes.
--
-- La regla de duplicidad actual es por (clasificador, concepto), por lo que
-- el catalogo usa una sola representacion libro-concepto por concepto.
-- DISTINCT ON selecciona un contexto reproducible (ISBN menor).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION soap_module.fn_conceptos_pendientes(
    p_clasificador_id BIGINT,
    p_limite INTEGER DEFAULT 50
)
RETURNS TABLE (
    isbn VARCHAR(20),
    titulo_libro VARCHAR(300),
    categoria VARCHAR(80),
    concepto_id BIGINT,
    concepto VARCHAR(150),
    definicion TEXT,
    total_pendientes BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH catalogo AS (
        SELECT DISTINCT ON (v.concepto_id)
            v.isbn,
            v.titulo_libro,
            v.categoria,
            v.concepto_id,
            v.concepto,
            v.definicion
        FROM soap_module.vw_catalogo_clasificable AS v
        ORDER BY v.concepto_id, v.isbn
    ),
    pendientes AS (
        SELECT c.*
        FROM catalogo AS c
        WHERE NOT EXISTS (
            SELECT 1
            FROM soap_module.clasificaciones_cloud AS cc
            WHERE cc.clasificador_id = p_clasificador_id
              AND cc.concepto_id = c.concepto_id
        )
    )
    SELECT
        p.isbn,
        p.titulo_libro,
        p.categoria,
        p.concepto_id,
        p.concepto,
        p.definicion,
        COUNT(*) OVER () AS total_pendientes
    FROM pendientes AS p
    ORDER BY p.titulo_libro, p.concepto
    LIMIT GREATEST(
        1,
        LEAST(COALESCE(p_limite, 50), 100)
    );
$$;


-- ----------------------------------------------------------------------------
-- Registrar clasificacion con errores de negocio distinguibles.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION soap_module.fn_registrar_clasificacion(
    p_clasificador_id BIGINT,
    p_isbn VARCHAR,
    p_concepto_id BIGINT,
    p_cliente_id BIGINT,
    p_modelo_cloud VARCHAR
)
RETURNS TIMESTAMPTZ
LANGUAGE plpgsql
AS $$
DECLARE
    v_fecha TIMESTAMPTZ;
BEGIN
    IF p_modelo_cloud NOT IN ('IaaS', 'PaaS', 'SaaS', 'FaaS') THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P1001',
            MESSAGE = 'INVALID_CLOUD_MODEL';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.conceptos
        WHERE concepto_id = p_concepto_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P1002',
            MESSAGE = 'CONCEPT_NOT_FOUND';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.libro_concepto
        WHERE isbn = p_isbn
          AND concepto_id = p_concepto_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P1003',
            MESSAGE = 'BOOK_CONCEPT_NOT_FOUND';
    END IF;

    BEGIN
        INSERT INTO soap_module.clasificaciones_cloud (
            clasificador_id,
            isbn,
            concepto_id,
            cliente_id,
            modelo_cloud
        )
        VALUES (
            p_clasificador_id,
            p_isbn,
            p_concepto_id,
            p_cliente_id,
            p_modelo_cloud
        )
        RETURNING fecha_clasificacion
        INTO v_fecha;

    EXCEPTION
        WHEN unique_violation THEN
            RAISE EXCEPTION USING
                ERRCODE = 'P1004',
                MESSAGE = 'DUPLICATE_CLASSIFICATION';
    END;

    RETURN v_fecha;
END;
$$;


-- ----------------------------------------------------------------------------
-- Progreso del usuario.
-- El total del catalogo se mide por conceptos distintos, consistente con
-- UNIQUE(clasificador_id, concepto_id).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION soap_module.fn_progreso_usuario(
    p_clasificador_id BIGINT
)
RETURNS TABLE (
    total_catalogo BIGINT,
    total_clasificados BIGINT,
    total_pendientes BIGINT,
    porcentaje_completado NUMERIC(5, 2)
)
LANGUAGE sql
STABLE
AS $$
    WITH catalogo AS (
        SELECT COUNT(DISTINCT concepto_id)::BIGINT AS total
        FROM public.libro_concepto
    ),
    progreso AS (
        SELECT COUNT(*)::BIGINT AS clasificados
        FROM soap_module.clasificaciones_cloud
        WHERE clasificador_id = p_clasificador_id
    )
    SELECT
        c.total AS total_catalogo,
        p.clasificados AS total_clasificados,
        GREATEST(c.total - p.clasificados, 0)::BIGINT
            AS total_pendientes,
        CASE
            WHEN c.total = 0 THEN 0.00::NUMERIC(5, 2)
            ELSE ROUND(
                (p.clasificados::NUMERIC / c.total::NUMERIC) * 100,
                2
            )::NUMERIC(5, 2)
        END AS porcentaje_completado
    FROM catalogo AS c
    CROSS JOIN progreso AS p;
$$;


-- Documentacion
COMMENT ON VIEW soap_module.vw_catalogo_clasificable IS
    'Proyeccion minima del catalogo real utilizada por el contrato SOAP.';

COMMENT ON FUNCTION soap_module.fn_clasificador_guardar IS
    'Crea o actualiza un clasificador identificado por correo.';

COMMENT ON FUNCTION soap_module.fn_cliente_registrar_peticion IS
    'Registra/incrementa una peticion atendida para una aplicacion cliente SOAP.';

COMMENT ON FUNCTION soap_module.fn_conceptos_pendientes IS
    'Devuelve conceptos aun no clasificados por un clasificador.';

COMMENT ON FUNCTION soap_module.fn_registrar_clasificacion IS
    'Valida y registra una clasificacion Cloud.';

COMMENT ON FUNCTION soap_module.fn_progreso_usuario IS
    'Calcula el progreso de clasificacion por conceptos distintos.';

COMMIT;


-- ============================================================================
-- PRIVILEGIOS
-- Ejecutar como administrador DESPUES de crear library_soap_user.
-- ============================================================================
-- GRANT SELECT ON soap_module.vw_catalogo_clasificable TO library_soap_user;
-- GRANT EXECUTE ON ALL ROUTINES IN SCHEMA soap_module TO library_soap_user;
