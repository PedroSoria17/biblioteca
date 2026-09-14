function requireLogin(req, res, next) {
  if (!req.session.usuario) {
    req.session.flash = { tipo: 'error', mensaje: 'Debes iniciar sesión para continuar.' };
    return res.redirect('/login');
  }
  next();
}

function requireAdmin(req, res, next) {
  if (!req.session.usuario) {
    req.session.flash = { tipo: 'error', mensaje: 'Debes iniciar sesión para continuar.' };
    return res.redirect('/login');
  }
  if (!req.session.usuario.es_administrador) {
    return res.status(403).render('errores/mensaje', {
      status: 403,
      mensaje: 'No tienes permisos para acceder a esta sección.',
    });
  }
  next();
}

module.exports = { requireLogin, requireAdmin };
