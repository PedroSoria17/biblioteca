-- ============================================================================
-- 03_all_quieries_before_stored_procedures.sql
-- ============================================================================
-- Snapshot documental de las consultas SQL que la aplicacion Node.js ejecutaba
-- de forma directa (mediante `pg`) ANTES de migrar a stored procedures,
-- functions y views (ver db/04_stored_procedures.sql y db/06_views.sql).
--
-- Este archivo es evidencia, no un script ejecutable de un tirón:
--   - Varias sentencias usan placeholders posicionales ($1, $2, ...) tal como
--     los recibe `pg` desde el código Node; sin los valores reales no se
--     pueden ejecutar como un lote.
--   - Algunas sentencias forman parte de una transaccion explicita
--     (BEGIN/COMMIT/ROLLBACK) en el codigo original; se marcan como tal.
--   - NO se conservan aqui contraseñas ni secretos (los hashes de password
--     nunca se seleccionan hacia la vista, y las credenciales de conexion
--     viven en variables de entorno, nunca en SQL).
--
-- Fuente: codigo real revisado en
--   apps/web-monolito01/backend-node/src/modules/libros/libro.model.js
--   apps/web-monolito01/backend-node/src/modules/libros/asociaciones.model.js
--   apps/web-monolito01/backend-node/src/modules/usuarios/usuario.model.js
--   apps/web-monolito01/backend-node/src/lib/catalogoFactory.js
-- antes de la migracion a stored procedures de esta misma ronda de trabajo.
-- ============================================================================


-- =========================================================
-- LIBROS  (src/modules/libros/libro.model.js)
-- =========================================================

-- Q-LIB-01: Listar catalogo, con busqueda opcional por titulo
-- (antes de P0-02 solo buscaba por titulo; ver Q-LIB-01b para la version
-- vigente despues de P0-02, que agrega busqueda por ISBN).
-- SELECT
SELECT l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock,
       f.nombre AS formato, c.nombre AS categoria
FROM libros l
JOIN formatos f ON f.formato_id = l.formato_id
JOIN categorias c ON c.categoria_id = l.categoria_id
WHERE l.titulo ILIKE $1
ORDER BY l.titulo ASC;

-- Q-LIB-01b: Listar catalogo, busqueda por titulo O isbn (version vigente
-- tras P0-02). El mismo parametro $1 (con comodines %..%) se usa dos veces.
-- SELECT
SELECT l.isbn, l.titulo, l.anio_publicacion, l.precio, l.stock,
       f.nombre AS formato, c.nombre AS categoria
FROM libros l
JOIN formatos f ON f.formato_id = l.formato_id
JOIN categorias c ON c.categoria_id = l.categoria_id
WHERE l.titulo ILIKE $1 OR l.isbn ILIKE $1
ORDER BY l.titulo ASC;

-- Q-LIB-02: Obtener un libro por ISBN, con nombre de formato y categoria
-- SELECT
SELECT l.*, f.nombre AS formato_nombre, c.nombre AS categoria_nombre
FROM libros l
JOIN formatos f ON f.formato_id = l.formato_id
JOIN categorias c ON c.categoria_id = l.categoria_id
WHERE l.isbn = $1;

-- Q-LIB-03: Crear libro
-- INSERT
INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, formato_id, categoria_id)
VALUES ($1, $2, $3, $4, $5, $6, $7)
RETURNING *;

-- Q-LIB-04: Actualizar libro
-- UPDATE
UPDATE libros
SET titulo = $1, anio_publicacion = $2, precio = $3, stock = $4, formato_id = $5, categoria_id = $6
WHERE isbn = $7
RETURNING *;

-- Q-LIB-05: Eliminar libro
-- DELETE
DELETE FROM libros WHERE isbn = $1;


-- =========================================================
-- ASOCIACIONES DE LIBRO (src/modules/libros/asociaciones.model.js)
-- =========================================================

-- ---- libro_autor (N:M) ----

-- Q-ASOC-01: Autores de un libro, en orden
-- SELECT
SELECT a.autor_id, a.nombre, a.apellido, la.orden
FROM libro_autor la
JOIN autores a ON a.autor_id = la.autor_id
WHERE la.isbn = $1
ORDER BY la.orden ASC;

-- Q-ASOC-02: Asociar autor a libro (o actualizar su orden si ya existia)
-- INSERT ... ON CONFLICT DO UPDATE (upsert)
INSERT INTO libro_autor (isbn, autor_id, orden)
VALUES ($1, $2, $3)
ON CONFLICT (isbn, autor_id) DO UPDATE SET orden = EXCLUDED.orden;

-- Q-ASOC-03: Quitar autor de un libro
-- DELETE
DELETE FROM libro_autor WHERE isbn = $1 AND autor_id = $2;

-- ---- libro_genero (N:M) ----

-- Q-ASOC-04: Generos de un libro
-- SELECT
SELECT g.genero_id, g.nombre
FROM libro_genero lg
JOIN generos g ON g.genero_id = lg.genero_id
WHERE lg.isbn = $1
ORDER BY g.nombre ASC;

-- Q-ASOC-05: Asociar genero a libro (ignora si ya existia)
-- INSERT ... ON CONFLICT DO NOTHING
INSERT INTO libro_genero (isbn, genero_id)
VALUES ($1, $2)
ON CONFLICT (isbn, genero_id) DO NOTHING;

-- Q-ASOC-06: Quitar genero de un libro
-- DELETE
DELETE FROM libro_genero WHERE isbn = $1 AND genero_id = $2;

-- ---- libro_concepto (N:M con atributo propio "definicion") ----

-- Q-ASOC-07: Conceptos y definicion de un libro
-- SELECT
SELECT c.concepto_id, c.nombre, lc.definicion
FROM libro_concepto lc
JOIN conceptos c ON c.concepto_id = lc.concepto_id
WHERE lc.isbn = $1
ORDER BY c.nombre ASC;

-- Q-ASOC-08: Asociar concepto a libro con definicion (o actualizar definicion)
-- INSERT ... ON CONFLICT DO UPDATE (upsert)
INSERT INTO libro_concepto (isbn, concepto_id, definicion)
VALUES ($1, $2, $3)
ON CONFLICT (isbn, concepto_id) DO UPDATE SET definicion = EXCLUDED.definicion;

-- Q-ASOC-09: Quitar concepto de un libro
-- DELETE
DELETE FROM libro_concepto WHERE isbn = $1 AND concepto_id = $2;

-- ---- imagenes_libro (1:N) ----

-- Q-ASOC-10: Imagenes de un libro, en orden
-- SELECT
SELECT imagen_id, url, texto_alternativo, orden, es_portada
FROM imagenes_libro
WHERE isbn = $1
ORDER BY orden ASC;

-- Q-ASOC-11: Agregar imagen a un libro
-- TRANSACCION explicita (BEGIN/COMMIT/ROLLBACK) ejecutada por el modelo Node:
--   1) cuenta cuantas imagenes tiene ya el libro;
--   2) decide si la nueva imagen debe marcarse como portada
--      (si el llamador lo pidio, o si es la primera imagen del libro);
--   3) si va a ser portada, desmarca cualquier portada previa del mismo libro;
--   4) inserta la imagen.
-- BEGIN;
SELECT COUNT(*)::int AS total FROM imagenes_libro WHERE isbn = $1;
-- (decision en JS: marcarComoPortada = esPortada OR total = 0)
UPDATE imagenes_libro SET es_portada = false WHERE isbn = $1; -- solo si marcarComoPortada
INSERT INTO imagenes_libro (isbn, url, texto_alternativo, orden, es_portada)
VALUES ($1, $2, $3, $4, $5)
RETURNING *;
-- COMMIT; (o ROLLBACK si algo falla)

-- Q-ASOC-12: Marcar una imagen como portada (y desmarcar las demas del libro)
-- TRANSACCION explicita (BEGIN/COMMIT/ROLLBACK)
-- BEGIN;
UPDATE imagenes_libro SET es_portada = false WHERE isbn = $1;
UPDATE imagenes_libro SET es_portada = true WHERE imagen_id = $1 AND isbn = $2;
-- COMMIT;

-- Q-ASOC-13: Obtener una imagen por id (usada antes de eliminar el archivo fisico)
-- SELECT
SELECT * FROM imagenes_libro WHERE imagen_id = $1;

-- Q-ASOC-14: Actualizar texto alternativo y orden de una imagen (P0-03)
-- UPDATE
UPDATE imagenes_libro
SET texto_alternativo = $1, orden = $2
WHERE imagen_id = $3
RETURNING *;

-- Q-ASOC-15: Eliminar imagen (metadatos; el archivo fisico se borra aparte en Node)
-- DELETE
DELETE FROM imagenes_libro WHERE imagen_id = $1;


-- =========================================================
-- USUARIOS (src/modules/usuarios/usuario.model.js)
-- =========================================================

-- Q-USR-01: Listar usuarios (sin password_hash mas alla de esta consulta puntual;
-- el modelo si selecciona la columna, pero el controlador de listado publico
-- (usuario.controller.js -> listar) solo la usa server-side, nunca la renderiza)
-- SELECT
SELECT usuario_id, nombre_completo, email, es_administrador, activo, fecha_registro
FROM usuarios
ORDER BY fecha_registro DESC;

-- Q-USR-02: Obtener usuario por id (incluye password_hash; uso interno para
-- verificar contraseña actual, nunca se envia al cliente)
-- SELECT
SELECT * FROM usuarios WHERE usuario_id = $1;

-- Q-USR-03: Obtener usuario por email (login)
-- SELECT
SELECT * FROM usuarios WHERE email = $1;

-- Q-USR-04: Crear usuario (registro)
-- INSERT
INSERT INTO usuarios (nombre_completo, email, password_hash, es_administrador)
VALUES ($1, $2, $3, $4)
RETURNING *;

-- Q-USR-05: Actualizar nombre/email de perfil
-- UPDATE
UPDATE usuarios
SET nombre_completo = $1, email = $2
WHERE usuario_id = $3
RETURNING *;

-- Q-USR-06: Actualizar password_hash
-- UPDATE
UPDATE usuarios SET password_hash = $1 WHERE usuario_id = $2;

-- Q-USR-07: Activar/desactivar usuario
-- UPDATE
UPDATE usuarios SET activo = $1 WHERE usuario_id = $2;

-- Q-USR-08: Eliminar usuario
-- DELETE
DELETE FROM usuarios WHERE usuario_id = $1;

-- Q-USR-09: Transferir administracion a otro usuario
-- TRANSACCION explicita (BEGIN/COMMIT/ROLLBACK): degrada al administrador
-- actual y promueve al nuevo dentro de la MISMA transaccion, para nunca
-- dejar 0 ni 2 administradores a medio camino (la base solo permite 0 o 1
-- gracias al indice unico parcial de 01_schema.sql).
-- BEGIN;
UPDATE usuarios SET es_administrador = false WHERE es_administrador = true;
UPDATE usuarios SET es_administrador = true WHERE usuario_id = $1;
-- COMMIT;


-- =========================================================
-- CATALOGOS GENERICOS: formatos, categorias, generos, conceptos, autores
-- (src/lib/catalogoFactory.js -- generadas dinamicamente por tabla/columnas,
-- se documentan aqui instanciadas para cada tabla real que las usa)
-- =========================================================

-- Q-CAT-01: Listar catalogo (ejemplo instanciado para "formatos";
-- generos/categorias/conceptos/autores siguen el mismo patron sobre su tabla)
-- SELECT
SELECT * FROM formatos ORDER BY nombre ASC;

-- Q-CAT-02: Obtener un registro de catalogo por id
-- SELECT
SELECT * FROM formatos WHERE formato_id = $1;

-- Q-CAT-03: Crear registro de catalogo (autores usa 3 columnas: nombre,
-- apellido, pais; los demas catalogos usan solo "nombre")
-- INSERT
INSERT INTO formatos (nombre) VALUES ($1) RETURNING *;
INSERT INTO autores (nombre, apellido, pais) VALUES ($1, $2, $3) RETURNING *;

-- Q-CAT-04: Actualizar registro de catalogo
-- UPDATE
UPDATE formatos SET nombre = $1 WHERE formato_id = $2 RETURNING *;
UPDATE autores SET nombre = $1, apellido = $2, pais = $3 WHERE autor_id = $4 RETURNING *;

-- Q-CAT-05: Eliminar registro de catalogo
-- DELETE
DELETE FROM formatos WHERE formato_id = $1;

-- ============================================================================
-- Fin del snapshot. A partir de aqui, la aplicacion migra a llamadas a
-- stored procedures/functions (db/04_stored_procedures.sql) y, para lecturas
-- que repiten los mismos JOIN, a views (db/06_views.sql).
-- ============================================================================
