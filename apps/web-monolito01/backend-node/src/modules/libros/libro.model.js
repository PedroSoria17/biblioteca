const pool = require('../../config/db');

// A partir de esta migracion, las lecturas/escrituras de libros pasan por las
// functions de db/04_stored_procedures.sql (que a su vez usan la vista
// vw_catalogo_libros de db/06_views.sql para el listado). Las interfaces de
// este modulo (listar/obtenerPorIsbn/crear/actualizar/eliminar) no cambian,
// para no romper libro.controller.js.

async function listar({ busqueda } = {}) {
  const { rows } = await pool.query('SELECT * FROM fn_libros_listar($1)', [busqueda || null]);
  return rows;
}

async function obtenerPorIsbn(isbn) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_obtener($1)', [isbn]);
  return rows[0];
}

async function crear(datos) {
  const { isbn, titulo, anioPublicacion, precio, stock, formatoId, categoriaId } = datos;
  const { rows } = await pool.query('SELECT * FROM fn_libro_crear($1, $2, $3, $4, $5, $6, $7)', [
    isbn,
    titulo,
    anioPublicacion,
    precio,
    stock,
    formatoId,
    categoriaId,
  ]);
  return rows[0];
}

async function actualizar(isbn, datos) {
  const { titulo, anioPublicacion, precio, stock, formatoId, categoriaId } = datos;
  const { rows } = await pool.query('SELECT * FROM fn_libro_actualizar($1, $2, $3, $4, $5, $6, $7)', [
    isbn,
    titulo,
    anioPublicacion,
    precio,
    stock,
    formatoId,
    categoriaId,
  ]);
  return rows[0];
}

async function eliminar(isbn) {
  await pool.query('CALL sp_libro_eliminar($1)', [isbn]);
}

module.exports = { listar, obtenerPorIsbn, crear, actualizar, eliminar };
