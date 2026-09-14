-- ============================================================================
-- DATOS SINTETICOS - Libreria en linea (library_db)
-- Compatible con sql/schema.sql del repo integracion01-main
-- Ejecutar DESPUES de haber cargado sql/schema.sql
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- Catalogos base
-- ----------------------------------------------------------------------------
INSERT INTO formatos (nombre) VALUES
    ('Tapa dura'),
    ('Tapa blanda'),
    ('Digital'),
    ('Audiolibro');

INSERT INTO categorias (nombre) VALUES
    ('Infantil'),
    ('Academico'),
    ('Comic'),
    ('Adulto');

INSERT INTO generos (nombre) VALUES
    ('Fantasia'),
    ('Terror'),
    ('Romance'),
    ('Historia'),
    ('Ciencia Ficcion'),
    ('Misterio');

INSERT INTO autores (nombre, apellido, pais) VALUES
    ('Laura',   'Gomez',    'Mexico'),
    ('Carlos',  'Perez',    'Argentina'),
    ('Marta',   'Diaz',     'Espana'),
    ('Andres',  'Ruiz',     'Colombia'),
    ('Sofia',   'Torres',   'Chile'),
    ('Diego',   'Morales',  'Peru'),
    ('Elena',   'Castro',   'Mexico'),
    ('Javier',  'Vega',     'Argentina');

INSERT INTO conceptos (nombre) VALUES
    ('Protagonista'),
    ('Ambientacion'),
    ('Conflicto central'),
    ('Simbolismo'),
    ('Final abierto');

-- ----------------------------------------------------------------------------
-- Usuarios (1 administrador + 3 usuarios normales)
-- password_hash es un valor de ejemplo (bcrypt de "Password123!"); reemplaza
-- por hashes reales si necesitas iniciar sesion con ellos.
-- ----------------------------------------------------------------------------
INSERT INTO usuarios (nombre_completo, email, password_hash, es_administrador, activo) VALUES
    ('Admin General', 'admin@libreria.com', '$2b$10$abcdefghijklmnopqrstuuOQ5H0m3s1F0oEXAMPLEHASHVALUE000', true,  true),
    ('Ana Fernandez',  'ana.fernandez@example.com',  '$2b$10$EXAMPLEHASHVALUEEXAMPLEHASHVALUEEXAMPLEHASH01', false, true),
    ('Luis Herrera',   'luis.herrera@example.com',   '$2b$10$EXAMPLEHASHVALUEEXAMPLEHASHVALUEEXAMPLEHASH02', false, true),
    ('Paola Reyes',    'paola.reyes@example.com',    '$2b$10$EXAMPLEHASHVALUEEXAMPLEHASHVALUEEXAMPLEHASH03', false, true);

-- ----------------------------------------------------------------------------
-- 10 libros sinteticos
-- ----------------------------------------------------------------------------
INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, formato_id, categoria_id) VALUES
    ('9781234560017', 'El Bosque Silencioso',        2018, 259.00, 12, 2, 1),
    ('9781234560024', 'Cronicas de Marte Rojo',       2021, 349.90,  8, 3, 4),
    ('9781234560031', 'Sombras en la Niebla',         2015, 199.50, 20, 2, 4),
    ('9781234560048', 'El Ultimo Faro',               2019, 289.00, 15, 1, 1),
    ('9781234560055', 'Manual de Algebra Lineal',     2020, 459.00,  6, 2, 2),
    ('9781234560062', 'Risas de Papel',               2017, 149.00, 30, 3, 3),
    ('9781234560079', 'La Ciudad de los Espejos',     2022, 329.90, 10, 1, 4),
    ('9781234560086', 'Corazones de Tinta',           2016, 219.00, 18, 2, 1),
    ('9781234560093', 'El Enigma de Valparaiso',      2014, 259.90, 11, 3, 4),
    ('9781234560109', 'Introduccion a la Historia Antigua', 2023, 399.00,  9, 2, 2);

-- ----------------------------------------------------------------------------
-- Autores por libro (algunos con coautoria)
-- ----------------------------------------------------------------------------
INSERT INTO libro_autor (isbn, autor_id, orden) VALUES
    ('9781234560017', 1, 1),
    ('9781234560024', 2, 1),
    ('9781234560024', 5, 2),
    ('9781234560031', 3, 1),
    ('9781234560048', 4, 1),
    ('9781234560055', 6, 1),
    ('9781234560062', 7, 1),
    ('9781234560079', 8, 1),
    ('9781234560086', 1, 1),
    ('9781234560086', 3, 2),
    ('9781234560093', 2, 1),
    ('9781234560109', 6, 1);

-- ----------------------------------------------------------------------------
-- Generos por libro
-- ----------------------------------------------------------------------------
INSERT INTO libro_genero (isbn, genero_id) VALUES
    ('9781234560017', 2),
    ('9781234560024', 5),
    ('9781234560031', 2),
    ('9781234560031', 6),
    ('9781234560048', 1),
    ('9781234560055', 4),
    ('9781234560062', 3),
    ('9781234560079', 1),
    ('9781234560079', 5),
    ('9781234560086', 3),
    ('9781234560093', 6),
    ('9781234560109', 4);

-- ----------------------------------------------------------------------------
-- Imagenes (una portada por libro)
-- ----------------------------------------------------------------------------
INSERT INTO imagenes_libro (isbn, url, texto_alternativo, orden, es_portada) VALUES
    ('9781234560017', '/uploads/libros/bosque-silencioso.jpg',       'Portada El Bosque Silencioso', 1, true),
    ('9781234560024', '/uploads/libros/cronicas-marte-rojo.jpg',      'Portada Cronicas de Marte Rojo', 1, true),
    ('9781234560031', '/uploads/libros/sombras-niebla.jpg',           'Portada Sombras en la Niebla', 1, true),
    ('9781234560048', '/uploads/libros/ultimo-faro.jpg',              'Portada El Ultimo Faro', 1, true),
    ('9781234560055', '/uploads/libros/manual-algebra-lineal.jpg',    'Portada Manual de Algebra Lineal', 1, true),
    ('9781234560062', '/uploads/libros/risas-papel.jpg',              'Portada Risas de Papel', 1, true),
    ('9781234560079', '/uploads/libros/ciudad-espejos.jpg',           'Portada La Ciudad de los Espejos', 1, true),
    ('9781234560086', '/uploads/libros/corazones-tinta.jpg',          'Portada Corazones de Tinta', 1, true),
    ('9781234560093', '/uploads/libros/enigma-valparaiso.jpg',        'Portada El Enigma de Valparaiso', 1, true),
    ('9781234560109', '/uploads/libros/historia-antigua.jpg',         'Portada Introduccion a la Historia Antigua', 1, true);

-- ----------------------------------------------------------------------------
-- Conceptos definidos en algunos libros (definicion propia por libro)
-- ----------------------------------------------------------------------------
INSERT INTO libro_concepto (isbn, concepto_id, definicion) VALUES
    ('9781234560017', 1, 'El guardabosques que descubre un secreto ancestral.'),
    ('9781234560017', 2, 'Un bosque nordico envuelto en niebla permanente.'),
    ('9781234560024', 3, 'La lucha por los recursos hidricos en la colonia marciana.'),
    ('9781234560031', 4, 'La niebla representa el olvido colectivo del pueblo.'),
    ('9781234560079', 5, 'El desenlace deja abierta la identidad del narrador.');

COMMIT;