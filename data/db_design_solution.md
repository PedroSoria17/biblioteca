# Diseño de base de datos: Librería en línea (PostgreSQL)

Solución a las instrucciones de [`db_design.md`](./db_design.md). El DDL completo está en
[`sql/schema.sql`](../sql/schema.sql).

## 1. Entidades

| Tabla            | Rol                                                              |
|------------------|-------------------------------------------------------------------|
| `usuarios`       | Usuarios registrados; a lo sumo uno con `es_administrador = true` |
| `libros`         | Atributos de valor único del libro (identificado por `isbn`)      |
| `autores`        | Catálogo de autores                                                |
| `generos`        | Catálogo de géneros                                                |
| `categorias`     | Catálogo de categorías (independiente de `formatos`)               |
| `formatos`       | Catálogo de formatos (independiente de `categorias`)                |
| `conceptos`      | Catálogo de conceptos reutilizables entre libros                   |
| `imagenes_libro` | Imágenes de un libro (1:N)                                         |
| `libro_autor`    | Relación N:M libro–autor                                           |
| `libro_genero`   | Relación N:M libro–género                                          |
| `libro_concepto` | Relación N:M libro–concepto, con `definicion` propia de cada par   |

## 2. Dependencias funcionales (FD)

Tomando `isbn` como clave candidata de un libro:

```
isbn → titulo, anio_publicacion, precio, stock, formato_id, categoria_id
usuario_id → nombre_completo, email, password_hash, es_administrador, fecha_registro
concepto_id → nombre
imagen_id → isbn, url, orden, es_portada
(isbn, autor_id) → orden           -- el orden del autor depende del PAR libro-autor
(isbn, concepto_id) → definicion   -- la definición depende del PAR libro-concepto, no de isbn ni de concepto_id por separado
```

El último caso es la clave del ejercicio: `definicion` no es funcionalmente dependiente de
`concepto_id` solo (el mismo concepto tiene definiciones distintas en libros distintos), ni de
`isbn` solo (un libro define varios conceptos). Su determinante mínimo es el par compuesto
`(isbn, concepto_id)`, de ahí que `libro_concepto` tenga esa clave primaria compuesta.

## 3. Dependencias multivaluadas (MVD) y por qué se separan en tablas puente

Si `autor`, `genero`, `imagen` y `concepto` vivieran como columnas repetidas dentro de `libros`,
la tabla violaría 1FN (grupos repetitivos) y, aun normalizando a una sola tabla ancha por libro,
violaría 4FN: son hechos independientes entre sí sobre el mismo libro.

```
isbn ->> autor_id      (independiente de género, imagen y concepto)
isbn ->> genero_id     (independiente de autor, imagen y concepto)
isbn ->> imagen_id     (independiente de autor, género y concepto)
isbn ->> concepto_id   (independiente de autor, género e imagen)
```

Ejemplo concreto: un libro con 2 autores y 3 géneros no implica 6 combinaciones reales
autor×género — son dos hechos independientes. Guardarlos en una sola fila (o en una tabla que
cruce ambos) produciría redundancia y anomalías de actualización. La solución en 4FN es una
tabla puente binaria por cada dependencia multivaluada:

- `libro_autor(isbn, autor_id)`
- `libro_genero(isbn, genero_id)`
- `imagenes_libro(imagen_id, isbn, ...)` (1:N real, no N:M, pero mismo principio de independencia)
- `libro_concepto(isbn, concepto_id, definicion)` — aquí además se cuelga el atributo
  `definicion`, porque depende funcionalmente del par, no de una sola de las dos columnas.

Con esto el esquema queda en 4FN: cada tabla puente representa exactamente una dependencia
multivaluada, sin mezclar dos MVD independientes en la misma relación.

## 4. Reglas de negocio → mecanismo de aplicación

| Regla                                                              | Implementación                                                                 |
|----------------------------------------------------------------------|---------------------------------------------------------------------------------|
| Un libro puede tener varios autores                                  | `libro_autor` N:M                                                               |
| Un libro puede pertenecer a varios géneros                           | `libro_genero` N:M                                                              |
| Mismo concepto con definición distinta por libro                     | `libro_concepto(isbn, concepto_id)` PK compuesta + `definicion` en la relación  |
| Un libro puede tener varias imágenes                                 | `imagenes_libro` 1:N, con `es_portada` limitada a una por libro (índice único parcial) |
| Formato y categoría son catálogos independientes                     | Tablas `formatos` y `categorias` separadas, cada una referenciada por FK propia desde `libros` (nada de tabla genérica "tipo") |
| Debe existir como máximo un administrador                            | Índice único parcial `ON usuarios (es_administrador) WHERE es_administrador` |

## 5. Notas de diseño

- `isbn` es texto (no numérico) porque puede incluir guiones y el dígito de control `X`
  (ISBN-10); se valida con `CHECK` mediante expresión regular.
- Los catálogos (`autores`, `generos`, `formatos`, `categorias`, `conceptos`) usan
  `ON DELETE RESTRICT` para no borrar en cascada un valor de catálogo en uso.
- Las tablas puente hacia `libros` usan `ON DELETE CASCADE`: al borrar un libro desaparecen
  sus asociaciones, pero nunca el autor/género/concepto del catálogo.
- La restricción de "máximo un administrador" se resuelve con un índice único parcial en vez
  de lógica de aplicación, para que la garantía viva en la base de datos y no dependa de que
  el backend la respete siempre.
