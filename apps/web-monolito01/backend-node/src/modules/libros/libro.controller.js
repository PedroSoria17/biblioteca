const libroModel = require('./libro.model');
const asociaciones = require('./asociaciones.model');
const { formatoModelo, categoriaModelo, generoModelo, conceptoModelo, autorModelo } = require('../../lib/catalogos');
const { esEnteroPositivo } = require('../../lib/validadores');
const { eliminarArchivoImagen } = require('../../lib/uploadsFs');

async function datosCatalogo() {
  const [formatos, categorias, todosAutores, todosGeneros, todosConceptos] = await Promise.all([
    formatoModelo.listar(),
    categoriaModelo.listar(),
    autorModelo.listar(),
    generoModelo.listar(),
    conceptoModelo.listar(),
  ]);
  return { formatos, categorias, todosAutores, todosGeneros, todosConceptos };
}

async function datosAsociaciones(isbn) {
  const [autoresLibro, generosLibro, conceptosLibro, imagenes] = await Promise.all([
    asociaciones.autoresDeLibro(isbn),
    asociaciones.generosDeLibro(isbn),
    asociaciones.conceptosDeLibro(isbn),
    asociaciones.imagenesDeLibro(isbn),
  ]);
  return { autoresLibro, generosLibro, conceptosLibro, imagenes };
}

function validarLibro(body) {
  const errores = [];
  if (!body.isbn || !body.isbn.trim()) errores.push('El ISBN es obligatorio.');
  if (!body.titulo || !body.titulo.trim()) errores.push('El título es obligatorio.');
  const anio = Number(body.anioPublicacion);
  if (!body.anioPublicacion || Number.isNaN(anio) || anio < 1450 || anio > 2100) {
    errores.push('El año de publicación debe ser un valor válido entre 1450 y 2100.');
  }
  if (body.precio === undefined || Number.isNaN(Number(body.precio)) || Number(body.precio) < 0) {
    errores.push('El precio debe ser un número válido.');
  }
  if (body.stock === undefined || Number.isNaN(Number(body.stock)) || Number(body.stock) < 0 || !Number.isInteger(Number(body.stock))) {
    errores.push('El stock debe ser un número entero válido.');
  }
  if (!esEnteroPositivo(body.formatoId)) errores.push('Selecciona un formato válido.');
  if (!esEnteroPositivo(body.categoriaId)) errores.push('Selecciona una categoría válida.');
  return errores;
}

async function listar(req, res, next) {
  try {
    const busqueda = (req.query.q || '').trim();
    const libros = await libroModel.listar({ busqueda });
    res.render('libros/lista', { libros, busqueda });
  } catch (err) {
    next(err);
  }
}

async function detalle(req, res, next) {
  try {
    const libro = await libroModel.obtenerPorIsbn(req.params.isbn);
    if (!libro) {
      return res.status(404).render('errores/mensaje', { status: 404, mensaje: 'Libro no encontrado.' });
    }
    const { autoresLibro, generosLibro, conceptosLibro, imagenes } = await datosAsociaciones(libro.isbn);
    res.render('libros/detalle', {
      libro,
      autores: autoresLibro,
      generos: generosLibro,
      conceptos: conceptosLibro,
      imagenes,
    });
  } catch (err) {
    next(err);
  }
}

async function nuevoFormulario(req, res, next) {
  try {
    const catalogo = await datosCatalogo();
    res.render('libros/formulario', {
      libro: null,
      ...catalogo,
      autoresLibro: [],
      generosLibro: [],
      conceptosLibro: [],
      imagenes: [],
      errores: null,
    });
  } catch (err) {
    next(err);
  }
}

async function crear(req, res, next) {
  try {
    const errores = validarLibro(req.body);
    if (errores.length) {
      const catalogo = await datosCatalogo();
      return res.status(400).render('libros/formulario', {
        libro: req.body,
        ...catalogo,
        autoresLibro: [],
        generosLibro: [],
        conceptosLibro: [],
        imagenes: [],
        errores,
      });
    }
    const libro = await libroModel.crear(req.body);
    req.session.flash = { tipo: 'exito', mensaje: 'Libro creado correctamente. Ahora puedes agregar autores, géneros, conceptos e imágenes.' };
    res.redirect(`/libros/${encodeURIComponent(libro.isbn)}/editar`);
  } catch (err) {
    if (err.code === '23505') {
      req.session.flash = { tipo: 'error', mensaje: 'Ya existe un libro con ese ISBN.' };
      return res.redirect('/libros/nuevo');
    }
    next(err);
  }
}

async function editarFormulario(req, res, next) {
  try {
    const libro = await libroModel.obtenerPorIsbn(req.params.isbn);
    if (!libro) {
      return res.status(404).render('errores/mensaje', { status: 404, mensaje: 'Libro no encontrado.' });
    }
    const [catalogo, asoc] = await Promise.all([datosCatalogo(), datosAsociaciones(libro.isbn)]);
    res.render('libros/formulario', { libro, ...catalogo, ...asoc, errores: null });
  } catch (err) {
    next(err);
  }
}

async function actualizar(req, res, next) {
  try {
    const errores = validarLibro({ ...req.body, isbn: req.params.isbn });
    if (errores.length) {
      const [catalogo, asoc] = await Promise.all([datosCatalogo(), datosAsociaciones(req.params.isbn)]);
      return res.status(400).render('libros/formulario', {
        libro: { ...req.body, isbn: req.params.isbn },
        ...catalogo,
        ...asoc,
        errores,
      });
    }
    await libroModel.actualizar(req.params.isbn, req.body);
    req.session.flash = { tipo: 'exito', mensaje: 'Libro actualizado.' };
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function eliminar(req, res, next) {
  try {
    // Base de datos primero: si PostgreSQL rechaza el DELETE (p. ej. una
    // restriccion de integridad), no debemos haber tocado el filesystem.
    // Por eso las imagenes se leen ANTES de borrar (imagenes_libro desaparece
    // por ON DELETE CASCADE en el mismo DELETE) y los archivos se eliminan
    // DESPUES, solo si el libro ya quedo eliminado en BD.
    const imagenes = await asociaciones.imagenesDeLibro(req.params.isbn);
    await libroModel.eliminar(req.params.isbn);
    await Promise.allSettled(imagenes.map((imagen) => eliminarArchivoImagen(imagen.url)));
    req.session.flash = { tipo: 'exito', mensaje: 'Libro eliminado.' };
    res.redirect('/libros');
  } catch (err) {
    next(err);
  }
}

async function agregarAutor(req, res, next) {
  try {
    const { autorId, orden } = req.body;
    if (!esEnteroPositivo(autorId) || (orden && !esEnteroPositivo(orden))) {
      req.session.flash = { tipo: 'error', mensaje: 'Selecciona un autor y un orden válidos.' };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    await asociaciones.agregarAutor(req.params.isbn, Number(autorId), orden ? Number(orden) : 1);
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function quitarAutor(req, res, next) {
  try {
    await asociaciones.quitarAutor(req.params.isbn, req.params.autorId);
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function agregarGenero(req, res, next) {
  try {
    if (!esEnteroPositivo(req.body.generoId)) {
      req.session.flash = { tipo: 'error', mensaje: 'Selecciona un género válido.' };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    await asociaciones.agregarGenero(req.params.isbn, Number(req.body.generoId));
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function quitarGenero(req, res, next) {
  try {
    await asociaciones.quitarGenero(req.params.isbn, req.params.generoId);
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function agregarConcepto(req, res, next) {
  try {
    const { conceptoId, definicion } = req.body;
    if (!esEnteroPositivo(conceptoId)) {
      req.session.flash = { tipo: 'error', mensaje: 'Selecciona un concepto válido.' };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    if (!definicion || !definicion.trim()) {
      req.session.flash = { tipo: 'error', mensaje: 'La definición es obligatoria.' };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    await asociaciones.agregarConcepto(req.params.isbn, Number(conceptoId), definicion.trim());
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function quitarConcepto(req, res, next) {
  try {
    await asociaciones.quitarConcepto(req.params.isbn, req.params.conceptoId);
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function agregarImagen(req, res, next) {
  try {
    if (!req.file) {
      req.session.flash = { tipo: 'error', mensaje: 'Selecciona una imagen.' };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    const { orden, textoAlternativo } = req.body;
    if (orden && !esEnteroPositivo(orden)) {
      req.session.flash = { tipo: 'error', mensaje: 'El orden de la imagen debe ser un número entero positivo.' };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    const url = `/uploads/libros/${req.file.filename}`;
    await asociaciones.agregarImagen(req.params.isbn, {
      url,
      textoAlternativo: textoAlternativo ? textoAlternativo.trim() : null,
      orden: orden ? Number(orden) : 1,
      esPortada: req.body.esPortada === 'on',
    });
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function actualizarImagen(req, res, next) {
  try {
    const { orden, textoAlternativo } = req.body;
    if (!esEnteroPositivo(orden)) {
      req.session.flash = { tipo: 'error', mensaje: 'El orden de la imagen debe ser un número entero positivo.' };
      return res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
    }
    await asociaciones.actualizarImagen(req.params.imagenId, {
      textoAlternativo: textoAlternativo ? textoAlternativo.trim() : null,
      orden: Number(orden),
    });
    req.session.flash = { tipo: 'exito', mensaje: 'Imagen actualizada.' };
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function marcarPortada(req, res, next) {
  try {
    await asociaciones.marcarPortada(req.params.isbn, req.params.imagenId);
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

async function eliminarImagen(req, res, next) {
  try {
    const imagen = await asociaciones.obtenerImagen(req.params.imagenId);
    if (imagen) {
      await asociaciones.eliminarImagen(imagen.imagen_id);
      await eliminarArchivoImagen(imagen.url);
    }
    res.redirect(`/libros/${encodeURIComponent(req.params.isbn)}/editar`);
  } catch (err) {
    next(err);
  }
}

module.exports = {
  listar,
  detalle,
  nuevoFormulario,
  crear,
  editarFormulario,
  actualizar,
  eliminar,
  agregarAutor,
  quitarAutor,
  agregarGenero,
  quitarGenero,
  agregarConcepto,
  quitarConcepto,
  agregarImagen,
  actualizarImagen,
  marcarPortada,
  eliminarImagen,
};
