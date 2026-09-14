const fs = require('fs/promises');
const path = require('path');

const carpetaUploadsLibros = path.join(__dirname, '..', 'public', 'uploads', 'libros');

// Resuelve, de forma segura, la ruta fisica de una url de imagen almacenada
// en BD (ej. "/uploads/libros/archivo.jpg"). Usa unicamente el nombre de
// archivo (path.basename) y lo une al directorio fijo de uploads, para que
// un valor con "../" u otra ruta nunca pueda resolver fuera de ese
// directorio (evita path traversal). Nunca puede resolver hacia
// src/public/images/book-placeholder.svg ni ningun otro archivo del proyecto,
// porque siempre se une contra carpetaUploadsLibros.
function rutaFisicaDesdeUrl(url) {
  const nombreArchivo = path.basename(String(url || ''));
  return path.join(carpetaUploadsLibros, nombreArchivo);
}

// Elimina el archivo fisico de una imagen si existe. Nunca lanza: un archivo
// ya inexistente (ENOENT) se trata como resultado exitoso (idempotente);
// otros errores se registran en el servidor pero tampoco interrumpen al
// llamador, porque esta limpieza siempre corre DESPUES de que PostgreSQL ya
// confirmo el cambio correspondiente (ver libro.controller.js).
async function eliminarArchivoImagen(url) {
  if (!url) return;
  try {
    await fs.unlink(rutaFisicaDesdeUrl(url));
  } catch (err) {
    if (err.code !== 'ENOENT') {
      console.error('No se pudo eliminar el archivo de imagen:', rutaFisicaDesdeUrl(url), err);
    }
  }
}

module.exports = { carpetaUploadsLibros, rutaFisicaDesdeUrl, eliminarArchivoImagen };
