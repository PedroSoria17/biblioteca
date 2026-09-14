require('dotenv').config();
const bcrypt = require('bcryptjs');
const pool = require('../src/config/db');

async function main() {
  const email = process.env.ADMIN_EMAIL;
  const password = process.env.ADMIN_PASSWORD;
  const nombre = process.env.ADMIN_NOMBRE || 'Administrador';

  if (!email || !password) {
    console.error('Define ADMIN_EMAIL y ADMIN_PASSWORD en tu archivo .env antes de ejecutar este script.');
    process.exitCode = 1;
    return;
  }

  const { rows: administradores } = await pool.query('SELECT usuario_id FROM usuarios WHERE es_administrador = true');
  if (administradores.length > 0) {
    console.log('Ya existe un administrador registrado. No se creó ningún usuario nuevo.');
    return;
  }

  const hash = await bcrypt.hash(password, 10);
  await pool.query(
    `INSERT INTO usuarios (nombre_completo, email, password_hash, es_administrador)
     VALUES ($1, $2, $3, true)
     ON CONFLICT (email) DO UPDATE SET es_administrador = true, password_hash = EXCLUDED.password_hash`,
    [nombre, email.toLowerCase(), hash]
  );
  console.log(`Administrador creado/actualizado: ${email}`);
}

main()
  .catch((err) => {
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => pool.end());
