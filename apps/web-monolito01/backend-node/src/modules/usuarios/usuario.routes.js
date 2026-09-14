const express = require('express');
const router = express.Router();
const { requireLogin, requireAdmin } = require('../../middleware/auth');
const { requiereIdsNumericos } = require('../../lib/validadores');
const controlador = require('./usuario.controller');

router.get('/', requireAdmin, controlador.listar);
router.get('/perfil', requireLogin, controlador.verPerfil);
router.post('/perfil', requireLogin, controlador.actualizarPerfil);
router.post('/perfil/password', requireLogin, controlador.cambiarPassword);
router.get('/:id/editar', requireAdmin, requiereIdsNumericos('id'), controlador.editarAdmin);
router.post('/:id/editar', requireAdmin, requiereIdsNumericos('id'), controlador.guardarEdicionAdmin);
router.post('/:id/eliminar', requireAdmin, requiereIdsNumericos('id'), controlador.eliminar);
router.post('/:id/promover', requireAdmin, requiereIdsNumericos('id'), controlador.promover);

module.exports = router;
