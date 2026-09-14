// Validaciones server-side reutilizadas por varios controladores/rutas.
// No sustituyen las restricciones de PostgreSQL: son la primera barrera de control.

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function esEmailValido(email) {
  return typeof email === 'string' && EMAIL_REGEX.test(email.trim());
}

function esEnteroPositivo(valor) {
  if (valor === undefined || valor === null || valor === '') return false;
  if (!/^\d+$/.test(String(valor).trim())) return false;
  return Number.isInteger(Number(valor)) && Number(valor) > 0;
}

// Middleware Express: rechaza la solicitud si alguno de los req.params indicados
// no es un entero positivo, en vez de dejar que llegue tal cual a una consulta SQL.
function requiereIdsNumericos(...nombresParametros) {
  return (req, res, next) => {
    for (const nombre of nombresParametros) {
      if (!esEnteroPositivo(req.params[nombre])) {
        return res.status(400).render('errores/mensaje', {
          status: 400,
          mensaje: 'Identificador inválido.',
        });
      }
    }
    next();
  };
}

module.exports = { esEmailValido, esEnteroPositivo, requiereIdsNumericos };
