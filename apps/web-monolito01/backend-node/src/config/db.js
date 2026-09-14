const { Pool } = require('pg');

// PGUSER, PGPASSWORD y PGDATABASE son indispensables y no deben tener un valor
// por defecto: un fallback aqui podria hacer que la aplicacion se conecte con
// el superusuario "postgres" u otra base distinta a "library_db" sin avisar.
const variablesRequeridas = ['PGUSER', 'PGPASSWORD', 'PGDATABASE'];
const variablesFaltantes = variablesRequeridas.filter((nombre) => !process.env[nombre]);

if (variablesFaltantes.length > 0) {
  throw new Error(
    `Faltan variables de entorno requeridas para conectar a PostgreSQL: ${variablesFaltantes.join(', ')}. ` +
      'Configura un archivo .env a partir de .env.example antes de iniciar la aplicación.'
  );
}

const pool = new Pool({
  host: process.env.PGHOST || 'localhost',
  port: Number(process.env.PGPORT) || 5432,
  user: process.env.PGUSER,
  password: process.env.PGPASSWORD,
  database: process.env.PGDATABASE,
});

pool.on('error', (err) => {
  console.error('Error inesperado en el pool de PostgreSQL:', err);
});

module.exports = pool;
