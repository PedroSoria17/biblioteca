const pool = require('../../config/db');

// Migrado a las functions/procedures de db/04_stored_procedures.sql. La
// transaccion manual (BEGIN/COMMIT) que antes envolvia transferirAdministracion
// ahora vive dentro de sp_usuario_transferir_administracion, atomica por ser
// un unico procedure; el indice unico parcial de db/01_schema.sql sigue
// siendo la barrera final que impide 0 o 2 administradores.

async function listar() {
  const { rows } = await pool.query('SELECT * FROM fn_usuarios_listar()');
  return rows;
}

async function obtenerPorId(id) {
  const { rows } = await pool.query('SELECT * FROM fn_usuario_obtener($1)', [id]);
  return rows[0];
}

async function obtenerPorEmail(email) {
  const { rows } = await pool.query('SELECT * FROM fn_usuario_obtener_por_email($1)', [email]);
  return rows[0];
}

async function crear({ nombreCompleto, email, passwordHash, esAdministrador = false }) {
  const { rows } = await pool.query('SELECT * FROM fn_usuario_crear($1, $2, $3, $4)', [
    nombreCompleto,
    email,
    passwordHash,
    esAdministrador,
  ]);
  return rows[0];
}

async function actualizarPerfil(id, { nombreCompleto, email }) {
  const { rows } = await pool.query('SELECT * FROM fn_usuario_actualizar_perfil($1, $2, $3)', [
    id,
    nombreCompleto,
    email,
  ]);
  return rows[0];
}

async function actualizarPassword(id, passwordHash) {
  await pool.query('CALL sp_usuario_actualizar_password($1, $2)', [id, passwordHash]);
}

async function actualizarActivo(id, activo) {
  await pool.query('CALL sp_usuario_actualizar_activo($1, $2)', [id, activo]);
}

async function eliminar(id) {
  await pool.query('CALL sp_usuario_eliminar($1)', [id]);
}

async function transferirAdministracion(idNuevoAdmin) {
  await pool.query('CALL sp_usuario_transferir_administracion($1)', [idNuevoAdmin]);
}

module.exports = {
  listar,
  obtenerPorId,
  obtenerPorEmail,
  crear,
  actualizarPerfil,
  actualizarPassword,
  actualizarActivo,
  eliminar,
  transferirAdministracion,
};
