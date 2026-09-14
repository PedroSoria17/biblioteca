const pool = require('../../config/db');

// Migrado a las functions/procedures de db/04_stored_procedures.sql. Las
// transacciones que antes se manejaban manualmente en Node (BEGIN/COMMIT
// alrededor de agregarImagen y marcarPortada) ahora viven dentro de
// fn_libro_imagen_agregar y sp_libro_imagen_marcar_portada: al ejecutarse
// como una sola funcion/procedure de PostgreSQL, son atomicas por
// construccion y ya no necesitan `pool.connect()` + BEGIN/COMMIT desde aqui.

// ---- libro_autor (N:M) ----
async function autoresDeLibro(isbn) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_autores_listar($1)', [isbn]);
  return rows;
}

async function agregarAutor(isbn, autorId, orden) {
  await pool.query('CALL sp_libro_autor_agregar($1, $2, $3)', [isbn, autorId, orden || 1]);
}

async function quitarAutor(isbn, autorId) {
  await pool.query('CALL sp_libro_autor_quitar($1, $2)', [isbn, autorId]);
}

// ---- libro_genero (N:M) ----
async function generosDeLibro(isbn) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_generos_listar($1)', [isbn]);
  return rows;
}

async function agregarGenero(isbn, generoId) {
  await pool.query('CALL sp_libro_genero_agregar($1, $2)', [isbn, generoId]);
}

async function quitarGenero(isbn, generoId) {
  await pool.query('CALL sp_libro_genero_quitar($1, $2)', [isbn, generoId]);
}

// ---- libro_concepto (N:M con atributo "definicion" propio del par) ----
async function conceptosDeLibro(isbn) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_conceptos_listar($1)', [isbn]);
  return rows;
}

async function agregarConcepto(isbn, conceptoId, definicion) {
  await pool.query('CALL sp_libro_concepto_agregar($1, $2, $3)', [isbn, conceptoId, definicion]);
}

async function quitarConcepto(isbn, conceptoId) {
  await pool.query('CALL sp_libro_concepto_quitar($1, $2)', [isbn, conceptoId]);
}

// ---- imagenes_libro (1:N) ----
async function imagenesDeLibro(isbn) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_imagenes_listar($1)', [isbn]);
  return rows;
}

async function agregarImagen(isbn, { url, textoAlternativo, orden, esPortada }) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_imagen_agregar($1, $2, $3, $4, $5)', [
    isbn,
    url,
    textoAlternativo || null,
    orden || 1,
    Boolean(esPortada),
  ]);
  return rows[0];
}

async function marcarPortada(isbn, imagenId) {
  await pool.query('CALL sp_libro_imagen_marcar_portada($1, $2)', [isbn, imagenId]);
}

async function obtenerImagen(imagenId) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_imagen_obtener($1)', [imagenId]);
  return rows[0];
}

async function actualizarImagen(imagenId, { textoAlternativo, orden }) {
  const { rows } = await pool.query('SELECT * FROM fn_libro_imagen_actualizar($1, $2, $3)', [
    imagenId,
    textoAlternativo || null,
    orden,
  ]);
  return rows[0];
}

async function eliminarImagen(imagenId) {
  await pool.query('CALL sp_libro_imagen_eliminar($1)', [imagenId]);
}

module.exports = {
  autoresDeLibro,
  agregarAutor,
  quitarAutor,
  generosDeLibro,
  agregarGenero,
  quitarGenero,
  conceptosDeLibro,
  agregarConcepto,
  quitarConcepto,
  imagenesDeLibro,
  agregarImagen,
  marcarPortada,
  obtenerImagen,
  actualizarImagen,
  eliminarImagen,
};
