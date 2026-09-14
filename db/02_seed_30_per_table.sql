-- ============================================================================
-- 02_seed_30_per_table.sql
--
-- >>> ADVERTENCIA (leer antes de ejecutar) <<<
-- Este seed esta disenado para una base limpia de laboratorio (por ejemplo,
-- library_db_test recien creada con db/00_create_database.sql + db/01_schema.sql)
-- y NO debe ejecutarse sobre una base existente con datos de produccion/prueba
-- (como la library_db real, que ya tiene usuarios, un Administrador real y libros
-- creados durante pruebas funcionales). Motivos concretos:
--   - Asume nombres de catalogo (formatos/categorias/generos/conceptos) y el
--     email admin@libreria.local libres; si ya existen, cada INSERT choca con
--     una restriccion UNIQUE (23505) y ninguna fila de ese INSERT se guarda.
--   - Inserta un usuario con es_administrador = true: si la base ya tiene un
--     Administrador, el indice unico parcial (01_schema.sql) rechaza la fila
--     (23505) en vez de crear un segundo Administrador -- es un fallo seguro,
--     no una migracion, y no debe interpretarse como tal.
--   - Depende de que los ID *SERIAL de formatos/categorias/generos/autores/
--     conceptos empiecen exactamente en 1 y sin huecos (los INSERT de libros y
--     de las tablas puente referencian esos catalogos por posicion). Sobre una
--     base con filas previas los ID reales serian otros y las asociaciones
--     apuntarian a catalogos equivocados sin que PostgreSQL pueda detectarlo.
-- Este script NO es idempotente a proposito: es un seed de una sola vez para una
-- base vacia, no una migracion repetible.
--
-- Datos sinteticos: al menos 30 filas por tabla/relacion, siempre que sea
-- coherente con el modelo. Generado programaticamente para garantizar IDs, ISBN
-- y emails unicos, y para no repetir el mismo hash de forma manual en 30 filas.
--
-- Ejecutar DESPUES de db/01_schema.sql. No depende de db/04_stored_procedures.sql
-- ni de db/06_views.sql: son INSERT directos contra las tablas base.
--
-- Conteo planeado por tabla/relacion:
--   formatos        = 30
--   categorias      = 30
--   generos         = 30
--   autores         = 32
--   conceptos       = 30  (20 generales + 10 de Cloud Computing)
--   usuarios        = 30  (1 administrador + 29 regulares, 1 inactivo)
--   libros          = 33  (32 regulares + 1 de Cloud Computing)
--   libro_autor     >= 30 (cada libro con 1 autor; varios con coautoria)
--   libro_genero    >= 30 (cada libro con 1-2 generos)
--   imagenes_libro  = 33 (1 portada por libro; ver nota de archivos abajo)
--   libro_concepto  >= 30 (1 concepto por libro regular + 10 del libro de Cloud Computing)
--
-- imagenes_libro: cada fila usa una url UNICA y SINTETICA (seed-cover-NNN.jpg),
-- que nunca existe en disco. Deliberadamente NO se reutiliza ningun archivo real
-- subido durante pruebas manuales anteriores: aunque solo se asignara una vez por
-- archivo (sin compartirlo entre filas), ese archivo pertenece visualmente a OTRO
-- libro de prueba, y un libro sintetico del seed mostrando la portada real de un
-- libro distinto es incorrecto para la evidencia final. En su lugar, formulario.ejs
-- y detalle.ejs manejan el evento onerror del <img> y muestran
-- /images/book-placeholder.svg cuando el archivo no existe (sin loop de onerror).
-- eliminarImagen() en libro.controller.js ya tolera un archivo inexistente (no
-- falla), y ninguna fila comparte archivo con otra.
--
-- usuarios: la contraseña de prueba NO es una credencial real. Es un valor
-- sintetico de laboratorio ("Passw0rd!Lab2026") hasheado con bcrypt (costo 10)
-- mediante la misma libreria bcryptjs que usa la aplicacion, unicamente para
-- poder iniciar sesion durante pruebas. No debe usarse en ningun ambiente real.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- formatos (30)
-- ----------------------------------------------------------------------------
INSERT INTO formatos (nombre) VALUES
    ('Tapa dura'),
    ('Tapa blanda'),
    ('Digital (EPUB)'),
    ('Digital (PDF)'),
    ('Digital (MOBI)'),
    ('Audiolibro'),
    ('Audiolibro (MP3)'),
    ('Edicion de bolsillo'),
    ('Edicion de lujo'),
    ('Edicion coleccionista'),
    ('Espiral'),
    ('Pasta dura ilustrada'),
    ('Edicion escolar'),
    ('Edicion bilingue'),
    ('Letra grande'),
    ('Edicion facsimilar'),
    ('Edicion economica'),
    ('Libro-objeto'),
    ('Fasciculo'),
    ('Edicion universitaria'),
    ('Edicion de bolsillo ilustrada'),
    ('Digital interactivo'),
    ('Braille'),
    ('Edicion conmemorativa'),
    ('Edicion revisada'),
    ('Edicion ampliada'),
    ('Comic digital'),
    ('Novela grafica'),
    ('Cuadernillo'),
    ('Caja coleccionable');

-- ----------------------------------------------------------------------------
-- categorias (30)
-- ----------------------------------------------------------------------------
INSERT INTO categorias (nombre) VALUES
    ('Infantil'),
    ('Academico'),
    ('Comic'),
    ('Adulto'),
    ('Juvenil'),
    ('Ciencia'),
    ('Tecnologia'),
    ('Negocios'),
    ('Autoayuda'),
    ('Salud'),
    ('Cocina'),
    ('Arte'),
    ('Historia'),
    ('Biografias'),
    ('Referencia'),
    ('Texto escolar'),
    ('Poesia'),
    ('Teatro'),
    ('Ensayo'),
    ('Deportes'),
    ('Viajes'),
    ('Religion'),
    ('Filosofia'),
    ('Politica'),
    ('Economia'),
    ('Derecho'),
    ('Medicina'),
    ('Psicologia'),
    ('Educacion'),
    ('Idiomas');

-- ----------------------------------------------------------------------------
-- generos (30)
-- ----------------------------------------------------------------------------
INSERT INTO generos (nombre) VALUES
    ('Fantasia'),
    ('Terror'),
    ('Romance'),
    ('Historia'),
    ('Ciencia Ficcion'),
    ('Misterio'),
    ('Aventura'),
    ('Poesia'),
    ('Drama'),
    ('Comedia'),
    ('Biografia'),
    ('Autoayuda'),
    ('Filosofia'),
    ('Politica'),
    ('Economia'),
    ('Tecnologia'),
    ('Arte'),
    ('Musica'),
    ('Deporte'),
    ('Viajes'),
    ('Cocina'),
    ('Salud'),
    ('Psicologia'),
    ('Educacion'),
    ('Fabula'),
    ('Distopia'),
    ('Utopia'),
    ('Belico'),
    ('Policiaco'),
    ('Gotico');

-- ----------------------------------------------------------------------------
-- autores (32)
-- ----------------------------------------------------------------------------
INSERT INTO autores (nombre, apellido, pais) VALUES
    ('Laura', 'Gomez', 'Mexico'),
    ('Carlos', 'Perez', 'Argentina'),
    ('Marta', 'Diaz', 'Espana'),
    ('Andres', 'Ruiz', 'Colombia'),
    ('Sofia', 'Torres', 'Chile'),
    ('Diego', 'Morales', 'Peru'),
    ('Elena', 'Castro', 'Uruguay'),
    ('Javier', 'Vega', 'Ecuador'),
    ('Camila', 'Fernandez', 'Mexico'),
    ('Ricardo', 'Herrera', 'Argentina'),
    ('Valentina', 'Reyes', 'Espana'),
    ('Mateo', 'Ortiz', 'Colombia'),
    ('Isabel', 'Silva', 'Chile'),
    ('Fernando', 'Rojas', 'Peru'),
    ('Lucia', 'Vargas', 'Uruguay'),
    ('Pablo', 'Cabrera', 'Ecuador'),
    ('Daniela', 'Nunez', 'Mexico'),
    ('Sebastian', 'Molina', 'Argentina'),
    ('Renata', 'Suarez', 'Espana'),
    ('Alejandro', 'Aguilar', 'Colombia'),
    ('Paula', 'Campos', 'Chile'),
    ('Emilio', 'Delgado', 'Peru'),
    ('Natalia', 'Rios', 'Uruguay'),
    ('Gustavo', 'Paredes', 'Ecuador'),
    ('Ines', 'Cordero', 'Mexico'),
    ('Rodrigo', 'Salazar', 'Argentina'),
    ('Carolina', 'Mendez', 'Espana'),
    ('Hugo', 'Guerrero', 'Colombia'),
    ('Victoria', 'Navarro', 'Chile'),
    ('Martin', 'Bravo', 'Peru'),
    ('Gabriela', 'Espinoza', 'Uruguay'),
    ('Tomas', 'Cortes', 'Ecuador');

-- ----------------------------------------------------------------------------
-- conceptos (30 = 20 generales + 10 de Cloud Computing)
-- ----------------------------------------------------------------------------
INSERT INTO conceptos (nombre) VALUES
    ('Protagonista'),
    ('Ambientacion'),
    ('Conflicto central'),
    ('Simbolismo'),
    ('Final abierto'),
    ('Narrador omnisciente'),
    ('Antagonista'),
    ('Clímax narrativo'),
    ('Trama secundaria'),
    ('Metafora'),
    ('Ironia'),
    ('Prolepsis'),
    ('Analepsis'),
    ('Monologo interior'),
    ('Verosimilitud'),
    ('Arco de transformacion'),
    ('Punto de giro'),
    ('Foreshadowing'),
    ('Alegoria'),
    ('Tono narrativo'),
    ('IaaS'),
    ('PaaS'),
    ('SaaS'),
    ('FaaS'),
    ('Bucket'),
    ('Public Cloud'),
    ('Private Cloud'),
    ('Hybrid Cloud'),
    ('Multicloud'),
    ('Serverless');

-- ----------------------------------------------------------------------------
-- usuarios (30: 1 administrador + 29 regulares)
-- ----------------------------------------------------------------------------
INSERT INTO usuarios (nombre_completo, email, password_hash, es_administrador, activo) VALUES
    ('Administrador General', 'admin@libreria.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', true, true),
    ('Ana Fernandez', 'usuario01@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Luis Herrera', 'usuario02@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Paola Reyes', 'usuario03@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Marco Ortiz', 'usuario04@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Ivan Silva', 'usuario05@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Renata Rojas', 'usuario06@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Oscar Vargas', 'usuario07@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Denisse Cabrera', 'usuario08@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Hector Nunez', 'usuario09@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Karla Molina', 'usuario10@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Julian Suarez', 'usuario11@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Brenda Aguilar', 'usuario12@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Felipe Campos', 'usuario13@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Monica Delgado', 'usuario14@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Adrian Rios', 'usuario15@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Ximena Paredes', 'usuario16@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Nicolas Cordero', 'usuario17@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Fabiola Salazar', 'usuario18@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Rodrigo Mendez', 'usuario19@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Carla Guerrero', 'usuario20@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Emiliano Navarro', 'usuario21@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Yolanda Bravo', 'usuario22@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Bruno Espinoza', 'usuario23@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Teresa Cortes', 'usuario24@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Cesar Gomez', 'usuario25@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Alicia Perez', 'usuario26@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Simon Diaz', 'usuario27@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Miriam Ruiz', 'usuario28@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, true),
    ('Leonardo Torres', 'usuario29@lab.local', '$2a$10$7KuVntFKKE.r9DUDc.NQh.rX3wwOn2iycL3F6bPYPtRGPZ0SoxsRe', false, false);

-- ----------------------------------------------------------------------------
-- libros (33: 32 regulares + 1 de Cloud Computing)
-- ----------------------------------------------------------------------------
INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, formato_id, categoria_id) VALUES
    ('9781000000000', 'El Faro Silencioso (Vol. 1)', 1990, 99.50, 0, 1, 1),
    ('9781000000001', 'El Espejo Escondido (Vol. 2)', 1991, 116.50, 7, 2, 2),
    ('9781000000002', 'El Horizonte Ultimo (Vol. 3)', 1992, 133.50, 14, 3, 3),
    ('9781000000003', 'El Muelle Eterno (Vol. 4)', 1993, 150.50, 21, 4, 4),
    ('9781000000004', 'El Observatorio Perdido (Vol. 5)', 1994, 167.50, 28, 5, 5),
    ('9781000000005', 'El Bosque Distante (Vol. 6)', 1995, 184.50, 35, 6, 6),
    ('9781000000006', 'El Jardin Oscuro (Vol. 7)', 1996, 201.50, 2, 7, 7),
    ('9781000000007', 'El Puente Secreto (Vol. 8)', 1997, 218.50, 9, 8, 8),
    ('9781000000008', 'El Archivo Roto (Vol. 9)', 1998, 235.50, 16, 9, 9),
    ('9781000000009', 'El Vagon Dorado (Vol. 10)', 1999, 252.50, 23, 10, 10),
    ('9781000000010', 'El Mercado Invisible (Vol. 11)', 2000, 269.50, 30, 11, 11),
    ('9781000000011', 'El Rio Lejano (Vol. 12)', 2001, 286.50, 37, 12, 12),
    ('9781000000012', 'El Camino Profundo (Vol. 13)', 2002, 303.50, 4, 13, 13),
    ('9781000000013', 'El Refugio Antiguo (Vol. 14)', 2003, 320.50, 11, 14, 14),
    ('9781000000014', 'El Desierto Nuevo (Vol. 15)', 2004, 337.50, 18, 15, 15),
    ('9781000000015', 'El Sotano Frio (Vol. 16)', 2005, 354.50, 25, 16, 16),
    ('9781000000016', 'El Faro Silencioso (Vol. 17)', 2006, 371.50, 32, 17, 17),
    ('9781000000017', 'El Espejo Escondido (Vol. 18)', 2007, 388.50, 39, 18, 18),
    ('9781000000018', 'El Horizonte Ultimo (Vol. 19)', 2008, 405.50, 6, 19, 19),
    ('9781000000019', 'El Muelle Eterno (Vol. 20)', 2009, 422.50, 13, 20, 20),
    ('9781000000020', 'El Observatorio Perdido (Vol. 21)', 2010, 439.50, 20, 21, 21),
    ('9781000000021', 'El Bosque Distante (Vol. 22)', 2011, 456.50, 27, 22, 22),
    ('9781000000022', 'El Jardin Oscuro (Vol. 23)', 2012, 473.50, 34, 23, 23),
    ('9781000000023', 'El Puente Secreto (Vol. 24)', 2013, 490.50, 1, 24, 24),
    ('9781000000024', 'El Archivo Roto (Vol. 25)', 2014, 107.50, 8, 25, 25),
    ('9781000000025', 'El Vagon Dorado (Vol. 26)', 2015, 124.50, 15, 26, 26),
    ('9781000000026', 'El Mercado Invisible (Vol. 27)', 2016, 141.50, 22, 27, 27),
    ('9781000000027', 'El Rio Lejano (Vol. 28)', 2017, 158.50, 29, 28, 28),
    ('9781000000028', 'El Camino Profundo (Vol. 29)', 2018, 175.50, 36, 29, 29),
    ('9781000000029', 'El Refugio Antiguo (Vol. 30)', 2019, 192.50, 3, 30, 30),
    ('9781000000030', 'El Desierto Nuevo (Vol. 31)', 2020, 209.50, 10, 1, 1),
    ('9781000000031', 'El Sotano Frio (Vol. 32)', 2021, 226.50, 17, 2, 2),
    ('9781000000032', 'Fundamentos de Cloud Computing', 2024, 459.00, 25, 4, 7);

-- ----------------------------------------------------------------------------
-- libro_autor (44, >= 30: 1 autor por libro y coautoria en ~1 de cada 3)
-- ----------------------------------------------------------------------------
INSERT INTO libro_autor (isbn, autor_id, orden) VALUES
    ('9781000000000', 1, 1),
    ('9781000000000', 6, 2),
    ('9781000000001', 2, 1),
    ('9781000000002', 3, 1),
    ('9781000000003', 4, 1),
    ('9781000000003', 9, 2),
    ('9781000000004', 5, 1),
    ('9781000000005', 6, 1),
    ('9781000000006', 7, 1),
    ('9781000000006', 12, 2),
    ('9781000000007', 8, 1),
    ('9781000000008', 9, 1),
    ('9781000000009', 10, 1),
    ('9781000000009', 15, 2),
    ('9781000000010', 11, 1),
    ('9781000000011', 12, 1),
    ('9781000000012', 13, 1),
    ('9781000000012', 18, 2),
    ('9781000000013', 14, 1),
    ('9781000000014', 15, 1),
    ('9781000000015', 16, 1),
    ('9781000000015', 21, 2),
    ('9781000000016', 17, 1),
    ('9781000000017', 18, 1),
    ('9781000000018', 19, 1),
    ('9781000000018', 24, 2),
    ('9781000000019', 20, 1),
    ('9781000000020', 21, 1),
    ('9781000000021', 22, 1),
    ('9781000000021', 27, 2),
    ('9781000000022', 23, 1),
    ('9781000000023', 24, 1),
    ('9781000000024', 25, 1),
    ('9781000000024', 30, 2),
    ('9781000000025', 26, 1),
    ('9781000000026', 27, 1),
    ('9781000000027', 28, 1),
    ('9781000000027', 1, 2),
    ('9781000000028', 29, 1),
    ('9781000000029', 30, 1),
    ('9781000000030', 31, 1),
    ('9781000000030', 4, 2),
    ('9781000000031', 32, 1),
    ('9781000000032', 1, 1);

-- ----------------------------------------------------------------------------
-- libro_genero (50, >= 30: 1-2 generos por libro)
-- ----------------------------------------------------------------------------
INSERT INTO libro_genero (isbn, genero_id) VALUES
    ('9781000000000', 1),
    ('9781000000000', 8),
    ('9781000000001', 2),
    ('9781000000002', 3),
    ('9781000000002', 10),
    ('9781000000003', 4),
    ('9781000000004', 5),
    ('9781000000004', 12),
    ('9781000000005', 6),
    ('9781000000006', 7),
    ('9781000000006', 14),
    ('9781000000007', 8),
    ('9781000000008', 9),
    ('9781000000008', 16),
    ('9781000000009', 10),
    ('9781000000010', 11),
    ('9781000000010', 18),
    ('9781000000011', 12),
    ('9781000000012', 13),
    ('9781000000012', 20),
    ('9781000000013', 14),
    ('9781000000014', 15),
    ('9781000000014', 22),
    ('9781000000015', 16),
    ('9781000000016', 17),
    ('9781000000016', 24),
    ('9781000000017', 18),
    ('9781000000018', 19),
    ('9781000000018', 26),
    ('9781000000019', 20),
    ('9781000000020', 21),
    ('9781000000020', 28),
    ('9781000000021', 22),
    ('9781000000022', 23),
    ('9781000000022', 30),
    ('9781000000023', 24),
    ('9781000000024', 25),
    ('9781000000024', 2),
    ('9781000000025', 26),
    ('9781000000026', 27),
    ('9781000000026', 4),
    ('9781000000027', 28),
    ('9781000000028', 29),
    ('9781000000028', 6),
    ('9781000000029', 30),
    ('9781000000030', 1),
    ('9781000000030', 8),
    ('9781000000031', 2),
    ('9781000000032', 3),
    ('9781000000032', 10);

-- ----------------------------------------------------------------------------
-- imagenes_libro (33). Una portada sintetica por libro;
-- ninguna fila comparte url con otra ni con un archivo real de pruebas previas
-- (ver advertencia de archivos en el encabezado del archivo).
-- ----------------------------------------------------------------------------
INSERT INTO imagenes_libro (isbn, url, texto_alternativo, orden, es_portada) VALUES
    ('9781000000000', '/uploads/libros/seed-cover-001.jpg', 'Portada de El Faro Silencioso (Vol. 1)', 1, true),
    ('9781000000001', '/uploads/libros/seed-cover-002.jpg', 'Portada de El Espejo Escondido (Vol. 2)', 1, true),
    ('9781000000002', '/uploads/libros/seed-cover-003.jpg', 'Portada de El Horizonte Ultimo (Vol. 3)', 1, true),
    ('9781000000003', '/uploads/libros/seed-cover-004.jpg', 'Portada de El Muelle Eterno (Vol. 4)', 1, true),
    ('9781000000004', '/uploads/libros/seed-cover-005.jpg', 'Portada de El Observatorio Perdido (Vol. 5)', 1, true),
    ('9781000000005', '/uploads/libros/seed-cover-006.jpg', 'Portada de El Bosque Distante (Vol. 6)', 1, true),
    ('9781000000006', '/uploads/libros/seed-cover-007.jpg', 'Portada de El Jardin Oscuro (Vol. 7)', 1, true),
    ('9781000000007', '/uploads/libros/seed-cover-008.jpg', 'Portada de El Puente Secreto (Vol. 8)', 1, true),
    ('9781000000008', '/uploads/libros/seed-cover-009.jpg', 'Portada de El Archivo Roto (Vol. 9)', 1, true),
    ('9781000000009', '/uploads/libros/seed-cover-010.jpg', 'Portada de El Vagon Dorado (Vol. 10)', 1, true),
    ('9781000000010', '/uploads/libros/seed-cover-011.jpg', 'Portada de El Mercado Invisible (Vol. 11)', 1, true),
    ('9781000000011', '/uploads/libros/seed-cover-012.jpg', 'Portada de El Rio Lejano (Vol. 12)', 1, true),
    ('9781000000012', '/uploads/libros/seed-cover-013.jpg', 'Portada de El Camino Profundo (Vol. 13)', 1, true),
    ('9781000000013', '/uploads/libros/seed-cover-014.jpg', 'Portada de El Refugio Antiguo (Vol. 14)', 1, true),
    ('9781000000014', '/uploads/libros/seed-cover-015.jpg', 'Portada de El Desierto Nuevo (Vol. 15)', 1, true),
    ('9781000000015', '/uploads/libros/seed-cover-016.jpg', 'Portada de El Sotano Frio (Vol. 16)', 1, true),
    ('9781000000016', '/uploads/libros/seed-cover-017.jpg', 'Portada de El Faro Silencioso (Vol. 17)', 1, true),
    ('9781000000017', '/uploads/libros/seed-cover-018.jpg', 'Portada de El Espejo Escondido (Vol. 18)', 1, true),
    ('9781000000018', '/uploads/libros/seed-cover-019.jpg', 'Portada de El Horizonte Ultimo (Vol. 19)', 1, true),
    ('9781000000019', '/uploads/libros/seed-cover-020.jpg', 'Portada de El Muelle Eterno (Vol. 20)', 1, true),
    ('9781000000020', '/uploads/libros/seed-cover-021.jpg', 'Portada de El Observatorio Perdido (Vol. 21)', 1, true),
    ('9781000000021', '/uploads/libros/seed-cover-022.jpg', 'Portada de El Bosque Distante (Vol. 22)', 1, true),
    ('9781000000022', '/uploads/libros/seed-cover-023.jpg', 'Portada de El Jardin Oscuro (Vol. 23)', 1, true),
    ('9781000000023', '/uploads/libros/seed-cover-024.jpg', 'Portada de El Puente Secreto (Vol. 24)', 1, true),
    ('9781000000024', '/uploads/libros/seed-cover-025.jpg', 'Portada de El Archivo Roto (Vol. 25)', 1, true),
    ('9781000000025', '/uploads/libros/seed-cover-026.jpg', 'Portada de El Vagon Dorado (Vol. 26)', 1, true),
    ('9781000000026', '/uploads/libros/seed-cover-027.jpg', 'Portada de El Mercado Invisible (Vol. 27)', 1, true),
    ('9781000000027', '/uploads/libros/seed-cover-028.jpg', 'Portada de El Rio Lejano (Vol. 28)', 1, true),
    ('9781000000028', '/uploads/libros/seed-cover-029.jpg', 'Portada de El Camino Profundo (Vol. 29)', 1, true),
    ('9781000000029', '/uploads/libros/seed-cover-030.jpg', 'Portada de El Refugio Antiguo (Vol. 30)', 1, true),
    ('9781000000030', '/uploads/libros/seed-cover-031.jpg', 'Portada de El Desierto Nuevo (Vol. 31)', 1, true),
    ('9781000000031', '/uploads/libros/seed-cover-032.jpg', 'Portada de El Sotano Frio (Vol. 32)', 1, true),
    ('9781000000032', '/uploads/libros/seed-cover-033.jpg', 'Portada de Fundamentos de Cloud Computing', 1, true);

-- ----------------------------------------------------------------------------
-- libro_concepto (42, >= 30): 1 concepto general por libro
-- regular + los 10 conceptos de Cloud Computing en el libro dedicado. La
-- definicion vive SIEMPRE en esta tabla puente, nunca en "conceptos".
-- ----------------------------------------------------------------------------
INSERT INTO libro_concepto (isbn, concepto_id, definicion) VALUES
    ('9781000000000', 1, 'Personaje principal alrededor de quien gira la accion central de la obra. (segun se desarrolla en "El Faro Silencioso (Vol. 1)").'),
    ('9781000000001', 2, 'Conjunto de circunstancias de tiempo y lugar en que se desarrolla la historia. (segun se desarrolla en "El Espejo Escondido (Vol. 2)").'),
    ('9781000000002', 3, 'Tension principal que impulsa la trama y que el protagonista debe resolver. (segun se desarrolla en "El Horizonte Ultimo (Vol. 3)").'),
    ('9781000000003', 4, 'Uso de elementos concretos de la narracion para representar ideas abstractas. (segun se desarrolla en "El Muelle Eterno (Vol. 4)").'),
    ('9781000000004', 5, 'Desenlace que no resuelve por completo la trama, dejando espacio a la interpretacion del lector. (segun se desarrolla en "El Observatorio Perdido (Vol. 5)").'),
    ('9781000000005', 6, 'Voz narrativa que conoce pensamientos y hechos mas alla de lo que percibe un solo personaje. (segun se desarrolla en "El Bosque Distante (Vol. 6)").'),
    ('9781000000006', 7, 'Personaje u fuerza que se opone directamente a los objetivos del protagonista. (segun se desarrolla en "El Jardin Oscuro (Vol. 7)").'),
    ('9781000000007', 8, 'Punto de mayor tension de la historia, previo a la resolucion del conflicto. (segun se desarrolla en "El Puente Secreto (Vol. 8)").'),
    ('9781000000008', 9, 'Linea argumental paralela a la trama principal que enriquece el relato. (segun se desarrolla en "El Archivo Roto (Vol. 9)").'),
    ('9781000000009', 10, 'Figura literaria que atribuye a un elemento las cualidades de otro para crear una imagen. (segun se desarrolla en "El Vagon Dorado (Vol. 10)").'),
    ('9781000000010', 11, 'Recurso narrativo en el que el significado real contrasta con el literal. (segun se desarrolla en "El Mercado Invisible (Vol. 11)").'),
    ('9781000000011', 12, 'Salto narrativo hacia adelante en el tiempo respecto del momento actual del relato. (segun se desarrolla en "El Rio Lejano (Vol. 12)").'),
    ('9781000000012', 13, 'Salto narrativo hacia atras en el tiempo (flashback) respecto del momento actual del relato. (segun se desarrolla en "El Camino Profundo (Vol. 13)").'),
    ('9781000000013', 14, 'Tecnica narrativa que expone directamente el flujo de pensamiento de un personaje. (segun se desarrolla en "El Refugio Antiguo (Vol. 14)").'),
    ('9781000000014', 15, 'Cualidad de una historia de resultar creible dentro de las reglas internas que establece. (segun se desarrolla en "El Desierto Nuevo (Vol. 15)").'),
    ('9781000000015', 16, 'Evolucion interna que experimenta un personaje a lo largo de la historia. (segun se desarrolla en "El Sotano Frio (Vol. 16)").'),
    ('9781000000016', 17, 'Momento que cambia de forma significativa el rumbo de la trama. (segun se desarrolla en "El Faro Silencioso (Vol. 17)").'),
    ('9781000000017', 18, 'Indicio temprano que anticipa un evento posterior de la trama. (segun se desarrolla en "El Espejo Escondido (Vol. 18)").'),
    ('9781000000018', 19, 'Relato en el que los elementos representan de forma sostenida un significado distinto y coherente. (segun se desarrolla en "El Horizonte Ultimo (Vol. 19)").'),
    ('9781000000019', 20, 'Actitud del narrador frente a los hechos que relata (por ejemplo, ironico, solemne, ligero). (segun se desarrolla en "El Muelle Eterno (Vol. 20)").'),
    ('9781000000020', 1, 'Personaje principal alrededor de quien gira la accion central de la obra. (segun se desarrolla en "El Observatorio Perdido (Vol. 21)").'),
    ('9781000000021', 2, 'Conjunto de circunstancias de tiempo y lugar en que se desarrolla la historia. (segun se desarrolla en "El Bosque Distante (Vol. 22)").'),
    ('9781000000022', 3, 'Tension principal que impulsa la trama y que el protagonista debe resolver. (segun se desarrolla en "El Jardin Oscuro (Vol. 23)").'),
    ('9781000000023', 4, 'Uso de elementos concretos de la narracion para representar ideas abstractas. (segun se desarrolla en "El Puente Secreto (Vol. 24)").'),
    ('9781000000024', 5, 'Desenlace que no resuelve por completo la trama, dejando espacio a la interpretacion del lector. (segun se desarrolla en "El Archivo Roto (Vol. 25)").'),
    ('9781000000025', 6, 'Voz narrativa que conoce pensamientos y hechos mas alla de lo que percibe un solo personaje. (segun se desarrolla en "El Vagon Dorado (Vol. 26)").'),
    ('9781000000026', 7, 'Personaje u fuerza que se opone directamente a los objetivos del protagonista. (segun se desarrolla en "El Mercado Invisible (Vol. 27)").'),
    ('9781000000027', 8, 'Punto de mayor tension de la historia, previo a la resolucion del conflicto. (segun se desarrolla en "El Rio Lejano (Vol. 28)").'),
    ('9781000000028', 9, 'Linea argumental paralela a la trama principal que enriquece el relato. (segun se desarrolla en "El Camino Profundo (Vol. 29)").'),
    ('9781000000029', 10, 'Figura literaria que atribuye a un elemento las cualidades de otro para crear una imagen. (segun se desarrolla en "El Refugio Antiguo (Vol. 30)").'),
    ('9781000000030', 11, 'Recurso narrativo en el que el significado real contrasta con el literal. (segun se desarrolla en "El Desierto Nuevo (Vol. 31)").'),
    ('9781000000031', 12, 'Salto narrativo hacia adelante en el tiempo respecto del momento actual del relato. (segun se desarrolla en "El Sotano Frio (Vol. 32)").'),
    ('9781000000032', 21, 'Infrastructure as a Service: el proveedor entrega infraestructura de computo, almacenamiento y red virtualizada bajo demanda, y el cliente administra sistema operativo y aplicaciones.'),
    ('9781000000032', 22, 'Platform as a Service: el proveedor entrega una plataforma lista (runtime, herramientas, middleware) para que el cliente despliegue aplicaciones sin administrar la infraestructura subyacente.'),
    ('9781000000032', 23, 'Software as a Service: el proveedor entrega una aplicacion completa lista para usar a traves de internet, y el cliente no administra ni infraestructura ni plataforma.'),
    ('9781000000032', 24, 'Function as a Service: modelo serverless donde el cliente despliega funciones individuales que el proveedor ejecuta bajo demanda y escala automaticamente.'),
    ('9781000000032', 25, 'Unidad logica de almacenamiento de objetos en la nube (por ejemplo, para imagenes o archivos), identificada por un nombre unico dentro del proveedor.'),
    ('9781000000032', 26, 'Infraestructura de nube operada por un proveedor externo y compartida entre multiples clientes (multi-tenant), accesible a traves de internet.'),
    ('9781000000032', 27, 'Infraestructura de nube dedicada a una sola organizacion, ya sea alojada en su propio centro de datos o por un proveedor de forma exclusiva.'),
    ('9781000000032', 28, 'Combinacion de nube publica y nube privada (o infraestructura on-premise) integradas para mover cargas de trabajo y datos entre ambas.'),
    ('9781000000032', 29, 'Uso simultaneo de servicios de mas de un proveedor de nube publica, generalmente para evitar dependencia de un unico proveedor.'),
    ('9781000000032', 30, 'Modelo de ejecucion donde el proveedor administra por completo la infraestructura y el escalamiento, y el cliente solo se preocupa por el codigo de la aplicacion.');

COMMIT;
