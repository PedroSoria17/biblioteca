const bcrypt = require('bcryptjs');
const usuarioModel = require('../usuarios/usuario.model');
const { esEmailValido } = require('../../lib/validadores');

function mostrarLogin(req, res) {
  res.render('auth/login', { errores: null, valores: {} });
}

async function procesarLogin(req, res, next) {
  try {
    const { email, password } = req.body;
    const usuario = await usuarioModel.obtenerPorEmail((email || '').trim().toLowerCase());
    if (!usuario || !usuario.activo) {
      return res.status(400).render('auth/login', { errores: ['Credenciales inválidas.'], valores: { email } });
    }
    const coincide = await bcrypt.compare(password || '', usuario.password_hash);
    if (!coincide) {
      return res.status(400).render('auth/login', { errores: ['Credenciales inválidas.'], valores: { email } });
    }
    req.session.usuario = {
      usuario_id: usuario.usuario_id,
      nombre_completo: usuario.nombre_completo,
      email: usuario.email,
      es_administrador: usuario.es_administrador,
    };
    req.session.flash = { tipo: 'exito', mensaje: `Bienvenido de nuevo, ${usuario.nombre_completo}.` };
    res.redirect('/libros');
  } catch (err) {
    next(err);
  }
}

function mostrarRegistro(req, res) {
  res.render('auth/registro', { errores: null, valores: {} });
}

async function procesarRegistro(req, res, next) {
  try {
    const { nombreCompleto, email, password, passwordConfirmar } = req.body;
    const errores = [];
    if (!nombreCompleto || !nombreCompleto.trim()) errores.push('El nombre es obligatorio.');
    if (!email || !email.trim()) errores.push('El correo es obligatorio.');
    else if (!esEmailValido(email)) errores.push('El correo no tiene un formato válido.');
    if (!password || password.length < 8) errores.push('La contraseña debe tener al menos 8 caracteres.');
    if (password !== passwordConfirmar) errores.push('Las contraseñas no coinciden.');
    if (errores.length) {
      return res.status(400).render('auth/registro', { errores, valores: { nombreCompleto, email } });
    }

    const existente = await usuarioModel.obtenerPorEmail(email.trim().toLowerCase());
    if (existente) {
      return res
        .status(400)
        .render('auth/registro', { errores: ['Ya existe una cuenta con ese correo.'], valores: { nombreCompleto, email } });
    }

    const hash = await bcrypt.hash(password, 10);
    const usuario = await usuarioModel.crear({
      nombreCompleto: nombreCompleto.trim(),
      email: email.trim().toLowerCase(),
      passwordHash: hash,
      esAdministrador: false,
    });
    req.session.usuario = {
      usuario_id: usuario.usuario_id,
      nombre_completo: usuario.nombre_completo,
      email: usuario.email,
      es_administrador: usuario.es_administrador,
    };
    req.session.flash = { tipo: 'exito', mensaje: `Bienvenido, ${usuario.nombre_completo}. Tu cuenta fue creada.` };
    res.redirect('/libros');
  } catch (err) {
    if (err.code === '23505') {
      return res
        .status(400)
        .render('auth/registro', { errores: ['Ya existe una cuenta con ese correo.'], valores: req.body });
    }
    next(err);
  }
}

function cerrarSesion(req, res) {
  req.session.destroy(() => res.redirect('/login'));
}

module.exports = { mostrarLogin, procesarLogin, mostrarRegistro, procesarRegistro, cerrarSesion };
