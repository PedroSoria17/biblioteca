const express = require('express');
const pool = require('../config/db');
const { requireAdmin } = require('../middleware/auth');
const { requiereIdsNumericos } = require('./validadores');

// Los catalogos simples (formatos, categorias, generos, conceptos) tienen la
// misma forma (id + nombre UNIQUE) y se resuelven con las funciones/procedure
// polimorficos fn_catalogo_*/sp_catalogo_eliminar de db/04_stored_procedures.sql
// (reciben el nombre de la tabla como parametro fijo, nunca como SQL dinamico:
// cada rama de esas rutinas es SQL estatico). "autores" tiene columnas propias
// (apellido, pais) y usa sus propias rutinas dedicadas fn_autor_*/sp_autor_eliminar.
//
// Esta fabrica evita repetir el CRUD cinco veces en el codigo Node, igual que
// antes de la migracion a stored procedures; solo cambia como habla con la base.
function crearModeloCatalogo({ tabla, idColumna }) {
  const esAutores = tabla === 'autores';

  // fn_catalogo_* devuelve columnas genericas (id, nombre); este adaptador las
  // vuelve a mapear al nombre de columna real (formato_id, categoria_id, ...)
  // para que las vistas EJS (que usan item[config.idColumna]) sigan funcionando
  // exactamente igual que antes.
  function adaptarFila(fila) {
    if (!fila) return undefined;
    return { [idColumna]: fila.id, nombre: fila.nombre };
  }

  async function listar() {
    if (esAutores) {
      const { rows } = await pool.query('SELECT * FROM fn_autores_listar()');
      return rows;
    }
    const { rows } = await pool.query('SELECT * FROM fn_catalogo_listar($1)', [tabla]);
    return rows.map(adaptarFila);
  }

  async function obtenerPorId(id) {
    if (esAutores) {
      const { rows } = await pool.query('SELECT * FROM fn_autor_obtener($1)', [id]);
      return rows[0];
    }
    const { rows } = await pool.query('SELECT * FROM fn_catalogo_obtener($1, $2)', [tabla, id]);
    return adaptarFila(rows[0]);
  }

  async function crear(datos) {
    if (esAutores) {
      const { rows } = await pool.query('SELECT * FROM fn_autor_crear($1, $2, $3)', [
        datos.nombre || null,
        datos.apellido || null,
        datos.pais || null,
      ]);
      return rows[0];
    }
    const { rows } = await pool.query('SELECT * FROM fn_catalogo_crear($1, $2)', [tabla, datos.nombre || null]);
    return adaptarFila(rows[0]);
  }

  async function actualizar(id, datos) {
    if (esAutores) {
      const { rows } = await pool.query('SELECT * FROM fn_autor_actualizar($1, $2, $3, $4)', [
        id,
        datos.nombre || null,
        datos.apellido || null,
        datos.pais || null,
      ]);
      return rows[0];
    }
    const { rows } = await pool.query('SELECT * FROM fn_catalogo_actualizar($1, $2, $3)', [
      tabla,
      id,
      datos.nombre || null,
    ]);
    return adaptarFila(rows[0]);
  }

  async function eliminar(id) {
    if (esAutores) {
      await pool.query('CALL sp_autor_eliminar($1)', [id]);
      return;
    }
    await pool.query('CALL sp_catalogo_eliminar($1, $2)', [tabla, id]);
  }

  return { listar, obtenerPorId, crear, actualizar, eliminar };
}

function validar(config, body) {
  const errores = [];
  for (const campo of config.campos) {
    if (campo.requerido && !String(body[campo.nombre] || '').trim()) {
      errores.push(`El campo "${campo.etiqueta}" es obligatorio.`);
    }
  }
  return errores;
}

function crearRouterCatalogo(config) {
  const router = express.Router();
  const modelo = crearModeloCatalogo(config);
  const { rutaBase, tituloSingular, idColumna } = config;

  router.get('/', requireAdmin, async (req, res, next) => {
    try {
      const items = await modelo.listar();
      res.render('catalogo/lista', { items, config });
    } catch (err) {
      next(err);
    }
  });

  router.get('/nuevo', requireAdmin, (req, res) => {
    res.render('catalogo/formulario', { config, item: null, errores: null });
  });

  router.post('/', requireAdmin, async (req, res, next) => {
    try {
      const errores = validar(config, req.body);
      if (errores.length) {
        return res.status(400).render('catalogo/formulario', { config, item: req.body, errores });
      }
      await modelo.crear(req.body);
      req.session.flash = { tipo: 'exito', mensaje: `${tituloSingular} creado correctamente.` };
      res.redirect(`/${rutaBase}`);
    } catch (err) {
      next(err);
    }
  });

  router.get('/:id/editar', requireAdmin, requiereIdsNumericos('id'), async (req, res, next) => {
    try {
      const item = await modelo.obtenerPorId(req.params.id);
      if (!item) {
        return res.status(404).render('errores/mensaje', { status: 404, mensaje: 'Registro no encontrado.' });
      }
      res.render('catalogo/formulario', { config, item, errores: null });
    } catch (err) {
      next(err);
    }
  });

  router.post('/:id/editar', requireAdmin, requiereIdsNumericos('id'), async (req, res, next) => {
    try {
      const errores = validar(config, req.body);
      if (errores.length) {
        return res.status(400).render('catalogo/formulario', {
          config,
          item: { ...req.body, [idColumna]: req.params.id },
          errores,
        });
      }
      await modelo.actualizar(req.params.id, req.body);
      req.session.flash = { tipo: 'exito', mensaje: `${tituloSingular} actualizado correctamente.` };
      res.redirect(`/${rutaBase}`);
    } catch (err) {
      next(err);
    }
  });

  router.post('/:id/eliminar', requireAdmin, requiereIdsNumericos('id'), async (req, res, next) => {
    try {
      await modelo.eliminar(req.params.id);
      req.session.flash = { tipo: 'exito', mensaje: `${tituloSingular} eliminado.` };
      res.redirect(`/${rutaBase}`);
    } catch (err) {
      if (err.code === '23503') {
        req.session.flash = {
          tipo: 'error',
          mensaje: `No se puede eliminar: hay libros que usan este ${tituloSingular.toLowerCase()}.`,
        };
        return res.redirect(`/${rutaBase}`);
      }
      next(err);
    }
  });

  return router;
}

module.exports = { crearModeloCatalogo, crearRouterCatalogo };
