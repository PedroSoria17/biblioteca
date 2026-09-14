const express = require('express');
const router = express.Router();
const { requireLogin, requireAdmin } = require('../../middleware/auth');
const { upload, mensajeErrorSubida } = require('../../middleware/upload');
const { requiereIdsNumericos } = require('../../lib/validadores');
const controlador = require('./libro.controller');

function subirImagen(req, res, next) {
  upload.single('imagen')(req, res, (err) => {
    if (err) {
      req.session.flash = { tipo: 'error', mensaje: mensajeErrorSubida(err) };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    next();
  });
}

router.get('/', requireLogin, controlador.listar);
router.get('/nuevo', requireAdmin, controlador.nuevoFormulario);
router.post('/', requireAdmin, controlador.crear);

router.get('/:isbn/editar', requireAdmin, controlador.editarFormulario);
router.post('/:isbn/editar', requireAdmin, controlador.actualizar);
router.post('/:isbn/eliminar', requireAdmin, controlador.eliminar);

router.post('/:isbn/autores', requireAdmin, controlador.agregarAutor);
router.post(
  '/:isbn/autores/:autorId/eliminar',
  requireAdmin,
  requiereIdsNumericos('autorId'),
  controlador.quitarAutor
);

router.post('/:isbn/generos', requireAdmin, controlador.agregarGenero);
router.post(
  '/:isbn/generos/:generoId/eliminar',
  requireAdmin,
  requiereIdsNumericos('generoId'),
  controlador.quitarGenero
);

router.post('/:isbn/conceptos', requireAdmin, controlador.agregarConcepto);
router.post(
  '/:isbn/conceptos/:conceptoId/eliminar',
  requireAdmin,
  requiereIdsNumericos('conceptoId'),
  controlador.quitarConcepto
);

router.post('/:isbn/imagenes', requireAdmin, subirImagen, controlador.agregarImagen);
router.post(
  '/:isbn/imagenes/:imagenId/editar',
  requireAdmin,
  requiereIdsNumericos('imagenId'),
  controlador.actualizarImagen
);
router.post(
  '/:isbn/imagenes/:imagenId/portada',
  requireAdmin,
  requiereIdsNumericos('imagenId'),
  controlador.marcarPortada
);
router.post(
  '/:isbn/imagenes/:imagenId/eliminar',
  requireAdmin,
  requiereIdsNumericos('imagenId'),
  controlador.eliminarImagen
);

router.get('/:isbn', requireLogin, controlador.detalle);

module.exports = router;
