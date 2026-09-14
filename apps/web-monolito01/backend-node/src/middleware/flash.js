// Mensajes de una sola lectura entre redirecciones (patron Post/Redirect/Get),
// para no depender de JSON ni de una API para comunicar el resultado de una accion.
module.exports = function flash(req, res, next) {
  res.locals.flash = req.session.flash || null;
  delete req.session.flash;
  next();
};
