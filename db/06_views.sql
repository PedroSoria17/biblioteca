-- ============================================================================
-- 06_views.sql
-- Vistas de consulta para library_db.
--
-- Ejecutar DESPUES de db/01_schema.sql y ANTES de db/04_stored_procedures.sql:
-- varias functions de ese archivo (fn_libros_listar, fn_libro_autores_listar,
-- fn_libro_generos_listar, fn_libro_conceptos_listar, fn_usuarios_listar) SI
-- dependen de estas vistas para no repetir los mismos JOIN en dos lugares (ver
-- orden final documentado en el encabezado de db/01_schema.sql).
--
-- Ninguna vista expone password_hash ni otros secretos.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- vw_catalogo_libros
-- Catalogo de libros con nombre de formato/categoria ya resuelto y, cuando
-- existe, la portada (evita repetir el JOIN formatos/categorias/imagenes_libro
-- en cada consulta de listado o detalle).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_catalogo_libros AS
SELECT
    l.isbn,
    l.titulo,
    l.anio_publicacion,
    l.precio,
    l.stock,
    l.formato_id,
    f.nombre AS formato,
    l.categoria_id,
    c.nombre AS categoria,
    p.url AS portada_url,
    p.texto_alternativo AS portada_alt,
    l.fecha_creacion,
    l.fecha_actualizacion
FROM libros l
JOIN formatos f ON f.formato_id = l.formato_id
JOIN categorias c ON c.categoria_id = l.categoria_id
LEFT JOIN imagenes_libro p ON p.isbn = l.isbn AND p.es_portada;

-- ----------------------------------------------------------------------------
-- vw_libro_autores
-- Autores de cada libro, en el orden registrado en libro_autor.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_libro_autores AS
SELECT
    l.isbn,
    l.titulo,
    a.autor_id,
    a.nombre,
    a.apellido,
    la.orden
FROM libro_autor la
JOIN libros l ON l.isbn = la.isbn
JOIN autores a ON a.autor_id = la.autor_id;

-- ----------------------------------------------------------------------------
-- vw_libro_generos
-- Generos de cada libro.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_libro_generos AS
SELECT
    l.isbn,
    l.titulo,
    g.genero_id,
    g.nombre AS genero
FROM libro_genero lg
JOIN libros l ON l.isbn = lg.isbn
JOIN generos g ON g.genero_id = lg.genero_id;

-- ----------------------------------------------------------------------------
-- vw_libro_conceptos
-- Conceptos y su definicion especifica por libro (isbn, concepto_id) ->
-- definicion; la definicion NUNCA vive en la tabla conceptos.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_libro_conceptos AS
SELECT
    l.isbn,
    l.titulo,
    co.concepto_id,
    co.nombre AS concepto,
    lc.definicion
FROM libro_concepto lc
JOIN libros l ON l.isbn = lc.isbn
JOIN conceptos co ON co.concepto_id = lc.concepto_id;

-- ----------------------------------------------------------------------------
-- vw_usuarios_resumen
-- Datos de usuario seguros para listados administrativos: nunca incluye
-- password_hash.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_usuarios_resumen AS
SELECT
    usuario_id,
    nombre_completo,
    email,
    es_administrador,
    activo,
    fecha_registro
FROM usuarios;
