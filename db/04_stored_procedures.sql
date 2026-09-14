-- ============================================================================
-- 04_stored_procedures.sql
-- Stored procedures y functions de library_db.
--
-- Ejecutar DESPUES de db/01_schema.sql y, obligatoriamente, DESPUES de
-- db/06_views.sql: varias funciones de lectura (fn_libros_listar,
-- fn_libro_autores_listar, fn_libro_generos_listar, fn_libro_conceptos_listar,
-- fn_usuarios_listar) hacen SELECT sobre las vistas de 06_views.sql para no
-- repetir el mismo JOIN en dos lugares. PostgreSQL permite compilar (CREATE
-- OR REPLACE FUNCTION) un cuerpo PL/pgSQL que referencia un objeto que aun no
-- existe -- solo lo resuelve en la PRIMERA llamada real -- pero para que el
-- orden de instalacion sea inequivoco y no dependa de ese comportamiento,
-- este archivo se instala DESPUES de db/06_views.sql (ver orden final
-- documentado en el encabezado de db/01_schema.sql).
--
-- Criterio usado en todo el archivo:
--   - CREATE FUNCTION ... RETURNS TABLE / RETURNS <tipo> cuando la aplicacion
--     necesita leer valores o conjuntos de filas.
--   - CREATE PROCEDURE cuando la operacion solo escribe y no necesita
--     devolver un conjunto de filas (se invoca con CALL).
--   - Cuando una operacion de escritura SI necesita devolver la fila
--     resultante (equivalente a "RETURNING *" en el codigo Node original),
--     se usa FUNCTION en vez de PROCEDURE, porque PostgreSQL no permite que
--     un PROCEDURE haga RETURN QUERY. Se documenta caso por caso.
--
-- Seguridad:
--   - Ninguna rutina construye SQL dinamico (no se usa EXECUTE con texto
--     concatenado). Las unicas rutinas "polimorficas" (fn_catalogo_*,
--     sp_catalogo_eliminar) resuelven la tabla destino con IF/ELSIF sobre un
--     conjunto fijo de valores literales controlados por el codigo Node
--     (nunca con datos crudos de un formulario), y cada rama ejecuta SQL
--     100% estatico.
--   - No se usa SECURITY DEFINER: estas rutinas corren con los privilegios
--     de quien las invoca (library_user), que ya tiene exactamente los
--     privilegios DML que necesita (ver db/00_create_database.sql). No hay
--     necesidad de elevar privilegios.
--   - Ninguna rutina expone password_hash salvo las que la aplicacion
--     necesita internamente para autenticar (fn_usuario_obtener,
--     fn_usuario_obtener_por_email), igual que en el codigo Node original;
--     esas filas nunca se renderizan en una vista EJS.
-- ============================================================================


-- ============================================================================
-- LIBROS
-- ============================================================================

-- fn_libros_listar: catalogo completo o filtrado por ISBN/titulo (RF-06).
-- p_busqueda NULL o '' => sin filtro. Se apoya en vw_catalogo_libros.
CREATE OR REPLACE FUNCTION fn_libros_listar(p_busqueda VARCHAR DEFAULT NULL)
RETURNS TABLE (
    isbn VARCHAR,
    titulo VARCHAR,
    anio_publicacion SMALLINT,
    precio NUMERIC,
    stock INTEGER,
    formato VARCHAR,
    categoria VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT v.isbn, v.titulo, v.anio_publicacion, v.precio, v.stock, v.formato, v.categoria
    FROM vw_catalogo_libros v
    WHERE p_busqueda IS NULL
       OR p_busqueda = ''
       OR v.titulo ILIKE '%' || p_busqueda || '%'
       OR v.isbn ILIKE '%' || p_busqueda || '%'
    ORDER BY v.titulo ASC;
END;
$$ LANGUAGE plpgsql STABLE;

-- fn_libro_obtener: un libro por ISBN con nombre de formato/categoria.
CREATE OR REPLACE FUNCTION fn_libro_obtener(p_isbn VARCHAR)
RETURNS TABLE (
    isbn VARCHAR,
    titulo VARCHAR,
    anio_publicacion SMALLINT,
    precio NUMERIC,
    stock INTEGER,
    formato_id SMALLINT,
    categoria_id SMALLINT,
    fecha_creacion TIMESTAMPTZ,
    fecha_actualizacion TIMESTAMPTZ,
    formato_nombre VARCHAR,
    categoria_nombre VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock,
           l.formato_id, l.categoria_id, l.fecha_creacion, l.fecha_actualizacion,
           f.nombre, c.nombre
    FROM libros l
    JOIN formatos f ON f.formato_id = l.formato_id
    JOIN categorias c ON c.categoria_id = l.categoria_id
    WHERE l.isbn = p_isbn;
END;
$$ LANGUAGE plpgsql STABLE;

-- fn_libro_crear: alta de libro (usa FUNCTION, no PROCEDURE, porque el
-- controlador Node necesita la fila insertada para redirigir a /editar).
CREATE OR REPLACE FUNCTION fn_libro_crear(
    p_isbn VARCHAR, p_titulo VARCHAR, p_anio_publicacion SMALLINT,
    p_precio NUMERIC, p_stock INTEGER, p_formato_id SMALLINT, p_categoria_id SMALLINT
)
RETURNS TABLE (
    isbn VARCHAR, titulo VARCHAR, anio_publicacion SMALLINT, precio NUMERIC,
    stock INTEGER, formato_id SMALLINT, categoria_id SMALLINT,
    fecha_creacion TIMESTAMPTZ, fecha_actualizacion TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, formato_id, categoria_id)
    VALUES (p_isbn, p_titulo, p_anio_publicacion, p_precio, p_stock, p_formato_id, p_categoria_id)
    RETURNING libros.isbn, libros.titulo, libros.anio_publicacion, libros.precio, libros.stock,
              libros.formato_id, libros.categoria_id, libros.fecha_creacion, libros.fecha_actualizacion;
END;
$$ LANGUAGE plpgsql;

-- fn_libro_actualizar: edicion de libro.
CREATE OR REPLACE FUNCTION fn_libro_actualizar(
    p_isbn VARCHAR, p_titulo VARCHAR, p_anio_publicacion SMALLINT,
    p_precio NUMERIC, p_stock INTEGER, p_formato_id SMALLINT, p_categoria_id SMALLINT
)
RETURNS TABLE (
    isbn VARCHAR, titulo VARCHAR, anio_publicacion SMALLINT, precio NUMERIC,
    stock INTEGER, formato_id SMALLINT, categoria_id SMALLINT,
    fecha_creacion TIMESTAMPTZ, fecha_actualizacion TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    UPDATE libros
    SET titulo = p_titulo, anio_publicacion = p_anio_publicacion, precio = p_precio,
        stock = p_stock, formato_id = p_formato_id, categoria_id = p_categoria_id
    WHERE libros.isbn = p_isbn
    RETURNING libros.isbn, libros.titulo, libros.anio_publicacion, libros.precio, libros.stock,
              libros.formato_id, libros.categoria_id, libros.fecha_creacion, libros.fecha_actualizacion;
END;
$$ LANGUAGE plpgsql;

-- sp_libro_eliminar: baja de libro (no necesita devolver filas -> PROCEDURE).
CREATE OR REPLACE PROCEDURE sp_libro_eliminar(p_isbn VARCHAR)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM libros WHERE isbn = p_isbn;
END;
$$;


-- ============================================================================
-- LIBRO_AUTOR
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_libro_autores_listar(p_isbn VARCHAR)
RETURNS TABLE (autor_id BIGINT, nombre VARCHAR, apellido VARCHAR, orden SMALLINT) AS $$
BEGIN
    RETURN QUERY
    SELECT v.autor_id, v.nombre, v.apellido, v.orden
    FROM vw_libro_autores v
    WHERE v.isbn = p_isbn
    ORDER BY v.orden ASC;
END;
$$ LANGUAGE plpgsql STABLE;

-- sp_libro_autor_agregar: upsert de la asociacion (equivalente al
-- ON CONFLICT DO UPDATE del modelo Node original).
CREATE OR REPLACE PROCEDURE sp_libro_autor_agregar(p_isbn VARCHAR, p_autor_id BIGINT, p_orden SMALLINT)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO libro_autor (isbn, autor_id, orden)
    VALUES (p_isbn, p_autor_id, COALESCE(p_orden, 1))
    ON CONFLICT (isbn, autor_id) DO UPDATE SET orden = EXCLUDED.orden;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_libro_autor_quitar(p_isbn VARCHAR, p_autor_id BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM libro_autor WHERE isbn = p_isbn AND autor_id = p_autor_id;
END;
$$;


-- ============================================================================
-- LIBRO_GENERO
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_libro_generos_listar(p_isbn VARCHAR)
RETURNS TABLE (genero_id SMALLINT, nombre VARCHAR) AS $$
BEGIN
    RETURN QUERY
    SELECT v.genero_id, v.genero
    FROM vw_libro_generos v
    WHERE v.isbn = p_isbn
    ORDER BY v.genero ASC;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE PROCEDURE sp_libro_genero_agregar(p_isbn VARCHAR, p_genero_id SMALLINT)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO libro_genero (isbn, genero_id)
    VALUES (p_isbn, p_genero_id)
    ON CONFLICT (isbn, genero_id) DO NOTHING;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_libro_genero_quitar(p_isbn VARCHAR, p_genero_id SMALLINT)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM libro_genero WHERE isbn = p_isbn AND genero_id = p_genero_id;
END;
$$;


-- ============================================================================
-- LIBRO_CONCEPTO (definicion propia del par isbn+concepto_id)
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_libro_conceptos_listar(p_isbn VARCHAR)
RETURNS TABLE (concepto_id BIGINT, nombre VARCHAR, definicion TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT v.concepto_id, v.concepto, v.definicion
    FROM vw_libro_conceptos v
    WHERE v.isbn = p_isbn
    ORDER BY v.concepto ASC;
END;
$$ LANGUAGE plpgsql STABLE;

-- sp_libro_concepto_agregar: upsert; nunca mueve la definicion a "conceptos".
CREATE OR REPLACE PROCEDURE sp_libro_concepto_agregar(p_isbn VARCHAR, p_concepto_id BIGINT, p_definicion TEXT)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO libro_concepto (isbn, concepto_id, definicion)
    VALUES (p_isbn, p_concepto_id, p_definicion)
    ON CONFLICT (isbn, concepto_id) DO UPDATE SET definicion = EXCLUDED.definicion;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_libro_concepto_quitar(p_isbn VARCHAR, p_concepto_id BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM libro_concepto WHERE isbn = p_isbn AND concepto_id = p_concepto_id;
END;
$$;


-- ============================================================================
-- IMAGENES_LIBRO
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_libro_imagenes_listar(p_isbn VARCHAR)
RETURNS TABLE (
    imagen_id BIGINT, url VARCHAR, texto_alternativo VARCHAR, orden SMALLINT, es_portada BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT i.imagen_id, i.url, i.texto_alternativo, i.orden, i.es_portada
    FROM imagenes_libro i
    WHERE i.isbn = p_isbn
    ORDER BY i.orden ASC;
END;
$$ LANGUAGE plpgsql STABLE;

-- fn_libro_imagen_agregar: encapsula, de forma atomica, la logica que antes
-- vivia como una transaccion explicita (BEGIN/COMMIT) en el modelo Node
-- (asociaciones.model.js -> agregarImagen): cuenta imagenes existentes,
-- decide si esta debe ser portada (lo pidieron o es la primera imagen del
-- libro), desmarca cualquier portada previa y luego inserta. Al ejecutarse
-- dentro de una sola funcion PL/pgSQL, todo el bloque corre en la misma
-- transaccion que el INSERT final: ya no se necesita un BEGIN/COMMIT manual
-- desde Node. La regla de "maximo una portada" queda ademas protegida por el
-- indice unico parcial de 01_schema.sql como ultima barrera.
CREATE OR REPLACE FUNCTION fn_libro_imagen_agregar(
    p_isbn VARCHAR, p_url VARCHAR, p_texto_alternativo VARCHAR,
    p_orden SMALLINT, p_es_portada BOOLEAN
)
RETURNS TABLE (
    imagen_id BIGINT, isbn VARCHAR, url VARCHAR, texto_alternativo VARCHAR,
    orden SMALLINT, es_portada BOOLEAN
) AS $$
DECLARE
    v_total INTEGER;
    v_marcar BOOLEAN;
BEGIN
    SELECT COUNT(*) INTO v_total FROM imagenes_libro WHERE imagenes_libro.isbn = p_isbn;
    v_marcar := COALESCE(p_es_portada, FALSE) OR v_total = 0;

    IF v_marcar THEN
        UPDATE imagenes_libro SET es_portada = FALSE WHERE imagenes_libro.isbn = p_isbn;
    END IF;

    RETURN QUERY
    INSERT INTO imagenes_libro (isbn, url, texto_alternativo, orden, es_portada)
    VALUES (p_isbn, p_url, p_texto_alternativo, COALESCE(p_orden, 1), v_marcar)
    RETURNING imagenes_libro.imagen_id, imagenes_libro.isbn, imagenes_libro.url,
              imagenes_libro.texto_alternativo, imagenes_libro.orden, imagenes_libro.es_portada;
END;
$$ LANGUAGE plpgsql;

-- sp_libro_imagen_marcar_portada: desmarca todas las imagenes del libro y
-- marca solo la indicada, de forma atomica (mismo motivo que la funcion
-- anterior: reemplaza el BEGIN/COMMIT manual de marcarPortada en Node).
CREATE OR REPLACE PROCEDURE sp_libro_imagen_marcar_portada(p_isbn VARCHAR, p_imagen_id BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE imagenes_libro SET es_portada = FALSE WHERE isbn = p_isbn;
    UPDATE imagenes_libro SET es_portada = TRUE WHERE imagen_id = p_imagen_id AND isbn = p_isbn;
END;
$$;

CREATE OR REPLACE FUNCTION fn_libro_imagen_obtener(p_imagen_id BIGINT)
RETURNS TABLE (
    imagen_id BIGINT, isbn VARCHAR, url VARCHAR, texto_alternativo VARCHAR,
    orden SMALLINT, es_portada BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT i.imagen_id, i.isbn, i.url, i.texto_alternativo, i.orden, i.es_portada
    FROM imagenes_libro i
    WHERE i.imagen_id = p_imagen_id;
END;
$$ LANGUAGE plpgsql STABLE;

-- fn_libro_imagen_actualizar: edita texto alternativo y orden (P0-03).
CREATE OR REPLACE FUNCTION fn_libro_imagen_actualizar(
    p_imagen_id BIGINT, p_texto_alternativo VARCHAR, p_orden SMALLINT
)
RETURNS TABLE (
    imagen_id BIGINT, isbn VARCHAR, url VARCHAR, texto_alternativo VARCHAR,
    orden SMALLINT, es_portada BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    UPDATE imagenes_libro
    SET texto_alternativo = p_texto_alternativo, orden = p_orden
    WHERE imagenes_libro.imagen_id = p_imagen_id
    RETURNING imagenes_libro.imagen_id, imagenes_libro.isbn, imagenes_libro.url,
              imagenes_libro.texto_alternativo, imagenes_libro.orden, imagenes_libro.es_portada;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE PROCEDURE sp_libro_imagen_eliminar(p_imagen_id BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM imagenes_libro WHERE imagen_id = p_imagen_id;
END;
$$;


-- ============================================================================
-- USUARIOS
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_usuarios_listar()
RETURNS TABLE (
    usuario_id BIGINT, nombre_completo VARCHAR, email VARCHAR,
    es_administrador BOOLEAN, activo BOOLEAN, fecha_registro TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT v.usuario_id, v.nombre_completo, v.email, v.es_administrador, v.activo, v.fecha_registro
    FROM vw_usuarios_resumen v
    ORDER BY v.fecha_registro DESC;
END;
$$ LANGUAGE plpgsql STABLE;

-- fn_usuario_obtener / fn_usuario_obtener_por_email SI incluyen
-- password_hash: son el equivalente exacto de "SELECT * FROM usuarios ..."
-- que el modelo Node ya ejecutaba para comparar contraseñas con bcrypt. El
-- valor nunca llega a una vista EJS (ver auth.controller.js / usuario.controller.js).
CREATE OR REPLACE FUNCTION fn_usuario_obtener(p_id BIGINT)
RETURNS TABLE (
    usuario_id BIGINT, nombre_completo VARCHAR, email VARCHAR, password_hash VARCHAR,
    es_administrador BOOLEAN, activo BOOLEAN, fecha_registro TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT u.usuario_id, u.nombre_completo, u.email, u.password_hash,
           u.es_administrador, u.activo, u.fecha_registro
    FROM usuarios u
    WHERE u.usuario_id = p_id;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION fn_usuario_obtener_por_email(p_email VARCHAR)
RETURNS TABLE (
    usuario_id BIGINT, nombre_completo VARCHAR, email VARCHAR, password_hash VARCHAR,
    es_administrador BOOLEAN, activo BOOLEAN, fecha_registro TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT u.usuario_id, u.nombre_completo, u.email, u.password_hash,
           u.es_administrador, u.activo, u.fecha_registro
    FROM usuarios u
    WHERE u.email = p_email;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION fn_usuario_crear(
    p_nombre_completo VARCHAR, p_email VARCHAR, p_password_hash VARCHAR, p_es_administrador BOOLEAN
)
RETURNS TABLE (
    usuario_id BIGINT, nombre_completo VARCHAR, email VARCHAR, password_hash VARCHAR,
    es_administrador BOOLEAN, activo BOOLEAN, fecha_registro TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    INSERT INTO usuarios (nombre_completo, email, password_hash, es_administrador)
    VALUES (p_nombre_completo, p_email, p_password_hash, COALESCE(p_es_administrador, FALSE))
    RETURNING usuarios.usuario_id, usuarios.nombre_completo, usuarios.email, usuarios.password_hash,
              usuarios.es_administrador, usuarios.activo, usuarios.fecha_registro;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_usuario_actualizar_perfil(
    p_id BIGINT, p_nombre_completo VARCHAR, p_email VARCHAR
)
RETURNS TABLE (
    usuario_id BIGINT, nombre_completo VARCHAR, email VARCHAR,
    es_administrador BOOLEAN, activo BOOLEAN, fecha_registro TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    UPDATE usuarios
    SET nombre_completo = p_nombre_completo, email = p_email
    WHERE usuarios.usuario_id = p_id
    RETURNING usuarios.usuario_id, usuarios.nombre_completo, usuarios.email,
              usuarios.es_administrador, usuarios.activo, usuarios.fecha_registro;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE PROCEDURE sp_usuario_actualizar_password(p_id BIGINT, p_password_hash VARCHAR)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE usuarios SET password_hash = p_password_hash WHERE usuario_id = p_id;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_usuario_actualizar_activo(p_id BIGINT, p_activo BOOLEAN)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE usuarios SET activo = p_activo WHERE usuario_id = p_id;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_usuario_eliminar(p_id BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM usuarios WHERE usuario_id = p_id;
END;
$$;

-- sp_usuario_transferir_administracion: valida el destino ANTES de tocar al
-- administrador actual, y solo entonces degrada/promueve dentro de la MISMA
-- transaccion implicita del procedure (reemplaza el BEGIN/COMMIT manual que
-- antes vivia en usuario.model.js). El indice unico parcial de 01_schema.sql
-- sigue siendo la barrera final que impide 0 o 2 administradores simultaneos.
--
-- Corregido en la ronda de cierre de gaps (Prompt 05): la version anterior
-- degradaba al administrador actual incondicionalmente y luego intentaba
-- promover al destino; si el destino no existia, la segunda UPDATE afectaba
-- 0 filas y el sistema quedaba con CERO administradores.
--
-- Validaciones, en orden:
--   1. SELECT ... FOR UPDATE bloquea la fila destino (evita una carrera con
--      otra transferencia concurrente) y en el mismo paso confirma que
--      existe.
--   2. Si no existe -> RAISE EXCEPTION, nada se modifica.
--   3. Si existe pero esta inactivo -> RAISE EXCEPTION, nada se modifica.
--   4. Caso D (destino ya es el administrador actual): no-op controlado. No
--      hay nada que transferir y asi se evita degradar y volver a promover
--      innecesariamente al unico administrador. Se documenta esta decision
--      aqui en vez de lanzar una excepcion porque no representa un estado
--      invalido: el resultado deseado (ese usuario es administrador) ya es
--      cierto.
--   5. Solo entonces se degrada al administrador actual y se promueve al
--      destino.
CREATE OR REPLACE PROCEDURE sp_usuario_transferir_administracion(p_id_nuevo_admin BIGINT)
LANGUAGE plpgsql AS $$
DECLARE
    v_activo BOOLEAN;
    v_ya_es_administrador BOOLEAN;
BEGIN
    SELECT activo, es_administrador
      INTO v_activo, v_ya_es_administrador
      FROM usuarios
     WHERE usuario_id = p_id_nuevo_admin
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El usuario destino (id=%) no existe.', p_id_nuevo_admin;
    END IF;

    IF NOT v_activo THEN
        RAISE EXCEPTION 'El usuario destino (id=%) esta inactivo y no puede ser administrador.', p_id_nuevo_admin;
    END IF;

    IF v_ya_es_administrador THEN
        RETURN;
    END IF;

    UPDATE usuarios SET es_administrador = FALSE WHERE es_administrador = TRUE;
    UPDATE usuarios SET es_administrador = TRUE WHERE usuario_id = p_id_nuevo_admin;
END;
$$;


-- ============================================================================
-- CATALOGOS SIMPLES: formatos, categorias, generos, conceptos
-- (misma forma: id + nombre UNIQUE). En vez de crear 4 x 5 = 20 rutinas casi
-- identicas, se usan 5 rutinas "polimorficas" que reciben el nombre del
-- catalogo (p_catalogo) y resuelven la tabla destino con IF/ELSIF estatico
-- (nunca con SQL dinamico). p_catalogo llega siempre desde codigo Node de
-- confianza (src/lib/catalogos.js), nunca directamente de un formulario.
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_catalogo_listar(p_catalogo VARCHAR)
RETURNS TABLE (id INTEGER, nombre VARCHAR) AS $$
BEGIN
    IF p_catalogo = 'formatos' THEN
        RETURN QUERY SELECT formato_id::INTEGER, formatos.nombre FROM formatos ORDER BY formatos.nombre ASC;
    ELSIF p_catalogo = 'categorias' THEN
        RETURN QUERY SELECT categoria_id::INTEGER, categorias.nombre FROM categorias ORDER BY categorias.nombre ASC;
    ELSIF p_catalogo = 'generos' THEN
        RETURN QUERY SELECT genero_id::INTEGER, generos.nombre FROM generos ORDER BY generos.nombre ASC;
    ELSIF p_catalogo = 'conceptos' THEN
        RETURN QUERY SELECT concepto_id::INTEGER, conceptos.nombre FROM conceptos ORDER BY conceptos.nombre ASC;
    ELSE
        RAISE EXCEPTION 'Catalogo no soportado: %', p_catalogo;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION fn_catalogo_obtener(p_catalogo VARCHAR, p_id INTEGER)
RETURNS TABLE (id INTEGER, nombre VARCHAR) AS $$
BEGIN
    IF p_catalogo = 'formatos' THEN
        RETURN QUERY SELECT formato_id::INTEGER, formatos.nombre FROM formatos WHERE formato_id = p_id;
    ELSIF p_catalogo = 'categorias' THEN
        RETURN QUERY SELECT categoria_id::INTEGER, categorias.nombre FROM categorias WHERE categoria_id = p_id;
    ELSIF p_catalogo = 'generos' THEN
        RETURN QUERY SELECT genero_id::INTEGER, generos.nombre FROM generos WHERE genero_id = p_id;
    ELSIF p_catalogo = 'conceptos' THEN
        RETURN QUERY SELECT concepto_id::INTEGER, conceptos.nombre FROM conceptos WHERE concepto_id = p_id;
    ELSE
        RAISE EXCEPTION 'Catalogo no soportado: %', p_catalogo;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION fn_catalogo_crear(p_catalogo VARCHAR, p_nombre VARCHAR)
RETURNS TABLE (id INTEGER, nombre VARCHAR) AS $$
BEGIN
    IF p_catalogo = 'formatos' THEN
        RETURN QUERY INSERT INTO formatos (nombre) VALUES (p_nombre) RETURNING formato_id::INTEGER, formatos.nombre;
    ELSIF p_catalogo = 'categorias' THEN
        RETURN QUERY INSERT INTO categorias (nombre) VALUES (p_nombre) RETURNING categoria_id::INTEGER, categorias.nombre;
    ELSIF p_catalogo = 'generos' THEN
        RETURN QUERY INSERT INTO generos (nombre) VALUES (p_nombre) RETURNING genero_id::INTEGER, generos.nombre;
    ELSIF p_catalogo = 'conceptos' THEN
        RETURN QUERY INSERT INTO conceptos (nombre) VALUES (p_nombre) RETURNING concepto_id::INTEGER, conceptos.nombre;
    ELSE
        RAISE EXCEPTION 'Catalogo no soportado: %', p_catalogo;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_catalogo_actualizar(p_catalogo VARCHAR, p_id INTEGER, p_nombre VARCHAR)
RETURNS TABLE (id INTEGER, nombre VARCHAR) AS $$
BEGIN
    IF p_catalogo = 'formatos' THEN
        RETURN QUERY UPDATE formatos SET nombre = p_nombre WHERE formato_id = p_id RETURNING formato_id::INTEGER, formatos.nombre;
    ELSIF p_catalogo = 'categorias' THEN
        RETURN QUERY UPDATE categorias SET nombre = p_nombre WHERE categoria_id = p_id RETURNING categoria_id::INTEGER, categorias.nombre;
    ELSIF p_catalogo = 'generos' THEN
        RETURN QUERY UPDATE generos SET nombre = p_nombre WHERE genero_id = p_id RETURNING genero_id::INTEGER, generos.nombre;
    ELSIF p_catalogo = 'conceptos' THEN
        RETURN QUERY UPDATE conceptos SET nombre = p_nombre WHERE concepto_id = p_id RETURNING concepto_id::INTEGER, conceptos.nombre;
    ELSE
        RAISE EXCEPTION 'Catalogo no soportado: %', p_catalogo;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE PROCEDURE sp_catalogo_eliminar(p_catalogo VARCHAR, p_id INTEGER)
LANGUAGE plpgsql AS $$
BEGIN
    IF p_catalogo = 'formatos' THEN
        DELETE FROM formatos WHERE formato_id = p_id;
    ELSIF p_catalogo = 'categorias' THEN
        DELETE FROM categorias WHERE categoria_id = p_id;
    ELSIF p_catalogo = 'generos' THEN
        DELETE FROM generos WHERE genero_id = p_id;
    ELSIF p_catalogo = 'conceptos' THEN
        DELETE FROM conceptos WHERE concepto_id = p_id;
    ELSE
        RAISE EXCEPTION 'Catalogo no soportado: %', p_catalogo;
    END IF;
END;
$$;


-- ============================================================================
-- AUTORES (rutinas propias: tiene mas columnas que los catalogos simples)
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_autores_listar()
RETURNS TABLE (autor_id BIGINT, nombre VARCHAR, apellido VARCHAR, pais VARCHAR) AS $$
BEGIN
    RETURN QUERY SELECT a.autor_id, a.nombre, a.apellido, a.pais FROM autores a ORDER BY a.nombre ASC;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION fn_autor_obtener(p_id BIGINT)
RETURNS TABLE (autor_id BIGINT, nombre VARCHAR, apellido VARCHAR, pais VARCHAR) AS $$
BEGIN
    RETURN QUERY SELECT a.autor_id, a.nombre, a.apellido, a.pais FROM autores a WHERE a.autor_id = p_id;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION fn_autor_crear(p_nombre VARCHAR, p_apellido VARCHAR, p_pais VARCHAR)
RETURNS TABLE (autor_id BIGINT, nombre VARCHAR, apellido VARCHAR, pais VARCHAR) AS $$
BEGIN
    RETURN QUERY
    INSERT INTO autores (nombre, apellido, pais)
    VALUES (p_nombre, p_apellido, p_pais)
    RETURNING autores.autor_id, autores.nombre, autores.apellido, autores.pais;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_autor_actualizar(p_id BIGINT, p_nombre VARCHAR, p_apellido VARCHAR, p_pais VARCHAR)
RETURNS TABLE (autor_id BIGINT, nombre VARCHAR, apellido VARCHAR, pais VARCHAR) AS $$
BEGIN
    RETURN QUERY
    UPDATE autores
    SET nombre = p_nombre, apellido = p_apellido, pais = p_pais
    WHERE autores.autor_id = p_id
    RETURNING autores.autor_id, autores.nombre, autores.apellido, autores.pais;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE PROCEDURE sp_autor_eliminar(p_id BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM autores WHERE autor_id = p_id;
END;
$$;
