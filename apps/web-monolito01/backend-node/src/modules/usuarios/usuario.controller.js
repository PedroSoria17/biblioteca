const bcrypt = require('bcryptjs');
const usuarioModel = require('./usuario.model');
const { esEmailValido } = require('../../lib/validadores');

async function listar(req, res, next) {
  try {
    const usuarios = await usuarioModel.listar();
    res.render('usuarios/lista', { usuarios });
  } catch (err) {
    next(err);
  }
}

async function verPerfil(req, res, next) {
  try {
    const usuario = await usuarioModel.obtenerPorId(req.session.usuario.usuario_id);
    res.render('usuarios/perfil', { usuario, errores: null });
  } catch (err) {
    next(err);
  }
}

async function actualizarPerfil(req, res, next) {
  try {
    const { nombreCompleto, email } = req.body;
    const errores = [];
    if (!nombreCompleto || !nombreCompleto.trim()) errores.push('El nombre es obligatorio.');
    if (!email || !email.trim()) errores.push('El correo es obligatorio.');
    else if (!esEmailValido(email)) errores.push('El correo no tiene un formato válido.');
    if (errores.length) {
      return res.status(400).render('usuarios/perfil', {
        usuario: { ...req.session.usuario, nombre_completo: nombreCompleto, email },
        errores,
      });
    }
    const actualizado = await usuarioModel.actualizarPerfil(req.session.usuario.usuario_id, { nombreCompleto, email });
    req.session.usuario.nombre_completo = actualizado.nombre_completo;
    req.session.usuario.email = actualizado.email;
    req.session.flash = { tipo: 'exito', mensaje: 'Perfil actualizado.' };
    res.redirect('/usuarios/perfil');
  } catch (err) {
    if (err.code === '23505') {
      req.session.flash = { tipo: 'error', mensaje: 'Ese correo ya está en uso.' };
      return res.redirect('/usuarios/perfil');
    }
    next(err);
  }
}

async function cambiarPassword(req, res, next) {
  try {
    const { passwordActual, passwordNueva, passwordConfirmar } = req.body;
    const usuario = await usuarioModel.obtenerPorId(req.session.usuario.usuario_id);
    const coincide = await bcrypt.compare(passwordActual || '', usuario.password_hash);
    if (!coincide) {
      req.session.flash = { tipo: 'error', mensaje: 'La contraseña actual no es correcta.' };
      return res.redirect('/usuarios/perfil');
    }
    if (!passwordNueva || passwordNueva.length < 8) {
      req.session.flash = { tipo: 'error', mensaje: 'La nueva contraseña debe tener al menos 8 caracteres.' };
      return res.redirect('/usuarios/perfil');
    }
    if (passwordNueva !== passwordConfirmar) {
      req.session.flash = { tipo: 'error', mensaje: 'Las contraseñas no coinciden.' };
      return res.redirect('/usuarios/perfil');
    }
    const hash = await bcrypt.hash(passwordNueva, 10);
    await usuarioModel.actualizarPassword(usuario.usuario_id, hash);
    req.session.flash = { tipo: 'exito', mensaje: 'Contraseña actualizada.' };
    res.redirect('/usuarios/perfil');
  } catch (err) {
    next(err);
  }
}

async function editarAdmin(req, res, next) {
  try {
    const usuario = await usuarioModel.obtenerPorId(req.params.id);
    if (!usuario) {
      return res.status(404).render('errores/mensaje', { status: 404, mensaje: 'Usuario no encontrado.' });
    }
    res.render('usuarios/editar', { usuario, errores: null });
  } catch (err) {
    next(err);
  }
}

async function guardarEdicionAdmin(req, res, next) {
  try {
    const { nombreCompleto, email, activo } = req.body;
    const errores = [];
    if (!nombreCompleto || !nombreCompleto.trim()) errores.push('El nombre es obligatorio.');
    if (!email || !email.trim()) errores.push('El correo es obligatorio.');
    else if (!esEmailValido(email)) errores.push('El correo no tiene un formato válido.');
    if (errores.length) {
      const usuario = await usuarioModel.obtenerPorId(req.params.id);
      return res
        .status(400)
        .render('usuarios/editar', { usuario: { ...usuario, nombre_completo: nombreCompleto, email }, errores });
    }
    await usuarioModel.actualizarPerfil(req.params.id, { nombreCompleto, email });
    await usuarioModel.actualizarActivo(req.params.id, activo === 'on');
    if (req.session.usuario.usuario_id === Number(req.params.id)) {
      req.session.usuario.nombre_completo = nombreCompleto;
      req.session.usuario.email = email;
    }
    req.session.flash = { tipo: 'exito', mensaje: 'Usuario actualizado.' };
    res.redirect('/usuarios');
  } catch (err) {
    if (err.code === '23505') {
      req.session.flash = { tipo: 'error', mensaje: 'Ese correo ya está en uso.' };
      return res.redirect(`/usuarios/${req.params.id}/editar`);
    }
    next(err);
  }
}

async function eliminar(req, res, next) {
  try {
    const idObjetivo = Number(req.params.id);
    if (idObjetivo === req.session.usuario.usuario_id) {
      req.session.flash = { tipo: 'error', mensaje: 'No puedes eliminar tu propia cuenta mientras tienes sesión activa.' };
      return res.redirect('/usuarios');
    }
    await usuarioModel.eliminar(idObjetivo);
    req.session.flash = { tipo: 'exito', mensaje: 'Usuario eliminado.' };
    res.redirect('/usuarios');
  } catch (err) {
    next(err);
  }
}

async function promover(req, res, next) {
  try {
    const idNuevoAdmin = Number(req.params.id);
    await usuarioModel.transferirAdministracion(idNuevoAdmin);
    req.session.usuario.es_administrador = idNuevoAdmin === req.session.usuario.usuario_id;
    req.session.flash = { tipo: 'exito', mensaje: 'Se transfirió la administración correctamente.' };
    res.redirect('/usuarios');
  } catch (err) {
    // sp_usuario_transferir_administracion rechaza con RAISE EXCEPTION (SQLSTATE
    // P0001) un destino inexistente o inactivo, sin haber modificado nada; ese
    // mensaje ya esta redactado para mostrarse tal cual, sin exponer SQL/stack.
    if (err.code === 'P0001') {
      req.session.flash = { tipo: 'error', mensaje: err.message };
      return res.redirect('/usuarios');
    }
    next(err);
  }
}

module.exports = {
  listar,
  verPerfil,
  actualizarPerfil,
  cambiarPassword,
  editarAdmin,
  guardarEdicionAdmin,
  eliminar,
  promover,
};
