const express = require('express');
const router = express.Router();
const controlador = require('./auth.controller');

router.get('/login', controlador.mostrarLogin);
router.post('/login', controlador.procesarLogin);
router.get('/registro', controlador.mostrarRegistro);
router.post('/registro', controlador.procesarRegistro);
router.post('/logout', controlador.cerrarSesion);

module.exports = router;
