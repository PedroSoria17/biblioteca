const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const multer = require('multer');

const carpetaDestino = path.join(__dirname, '..', 'public', 'uploads', 'libros');
fs.mkdirSync(carpetaDestino, { recursive: true });

const almacenamiento = multer.diskStorage({
  destination: (req, file, cb) => cb(null, carpetaDestino),
  filename: (req, file, cb) => {
    const extension = path.extname(file.originalname).toLowerCase();
    const nombreUnico = `${Date.now()}-${crypto.randomBytes(6).toString('hex')}${extension}`;
    cb(null, nombreUnico);
  },
});

// Solo JPG/JPEG, PNG y WebP para este ejercicio (GIF queda fuera de alcance).
const extensionesPermitidas = new Set(['.jpg', '.jpeg', '.png', '.webp']);
const mimesPermitidos = new Set(['image/jpeg', 'image/png', 'image/webp']);

function filtroArchivo(req, file, cb) {
  const extension = path.extname(file.originalname).toLowerCase();
  if (!extensionesPermitidas.has(extension)) {
    return cb(new Error('Formato de imagen no permitido. Usa JPG, PNG o WEBP.'));
  }
  if (!mimesPermitidos.has(file.mimetype)) {
    return cb(new Error('El tipo de archivo detectado no corresponde a una imagen permitida.'));
  }
  cb(null, true);
}

const upload = multer({
  storage: almacenamiento,
  fileFilter: filtroArchivo,
  limits: { fileSize: 5 * 1024 * 1024 },
});

// Traduce errores de Multer/fileFilter a un mensaje controlado para el usuario,
// sin exponer detalles técnicos ni interrumpir el flujo con un stack trace.
function mensajeErrorSubida(err) {
  if (err && err.code === 'LIMIT_FILE_SIZE') {
    return 'La imagen supera el tamaño máximo permitido (5 MB).';
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return 'No se pudo procesar la imagen.';
}

module.exports = { upload, mensajeErrorSubida };
