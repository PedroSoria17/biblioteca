module.exports = function errorHandler(err, req, res, next) {
  console.error(err);
  const status = err.status || 500;
  res.status(status).render('errores/mensaje', {
    status,
    mensaje: status === 500 ? 'Ocurrió un error inesperado. Intenta de nuevo más tarde.' : err.message,
  });
};
