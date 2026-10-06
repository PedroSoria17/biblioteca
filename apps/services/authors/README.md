# Microservicio Authors (puerto 5003)

Administra los autores (`autores`) y sus relaciones con libros
(`libro_autor`) en la base compartida `library_db`.

| Servicio      | Puerto |
| ------------- | ------ |
| Books / SOAP  | 5000   |
| Login         | 5001   |
| Users         | 5002   |
| **Authors**   | **5003** |
| Orders        | 5004 (futuro) |
| Payments      | 5005 (futuro) |

## Responsabilidad

Sí: listar/consultar/crear/editar/eliminar autores, consultar los libros de
un autor, asociar un autor existente a un libro existente y quitar esa
asociación.

No: crear, editar o eliminar libros (eso es Books), autenticar, emitir JWT,
manejar sesiones, ni tocar pedidos o pagos. Authors valida los access tokens
que emite Login usando `library_shared` (mismo `JWT_SECRET_KEY`, mismo Redis).

Authors consulta `libros` **directamente en PostgreSQL** (solo lectura) para
comprobar que un ISBN existe: no hace llamadas HTTP a Books.

Respuestas en JSON.

## Esquema real (data/01_schema.sql)

```sql
autores (autor_id BIGSERIAL PRIMARY KEY,
         nombre   VARCHAR(120) NOT NULL,
         apellido VARCHAR(120) NOT NULL,
         pais     VARCHAR(80))                       -- nullable

libro_autor (isbn     VARCHAR(20) NOT NULL REFERENCES libros(isbn)       ON DELETE CASCADE,
             autor_id BIGINT      NOT NULL REFERENCES autores(autor_id)  ON DELETE RESTRICT,
             orden    SMALLINT    NOT NULL DEFAULT 1,  -- posición del autor en el libro
             PRIMARY KEY (isbn, autor_id))
```

| Constraint | Efecto |
| ---------- | ------ |
| `autores_pkey` | Única restricción de `autores`: **no hay UNIQUE** de nombre, así que los homónimos son válidos (no se inventa una regla de duplicados). |
| `libro_autor_pkey (isbn, autor_id)` | Una relación autor-libro no puede repetirse. |
| `libro_autor_autor_id_fkey` **ON DELETE RESTRICT** | No se puede borrar un autor que tenga libros asociados. |
| `libro_autor_isbn_fkey` **ON DELETE CASCADE** | Si Books borra un libro, sus filas de `libro_autor` desaparecen (el autor queda). |

- `autores` no tiene timestamps ni triggers; ningún otro objeto referencia
  `autores` además de `libro_autor`.
- Índices: solo las PK. No existe índice por `libro_autor.autor_id` (la PK
  empieza por `isbn`); con el volumen actual no es necesario. Si crece,
  se recomienda una migración nueva con
  `CREATE INDEX ix_libro_autor_autor_id ON libro_autor (autor_id)`.

## Endpoints y permisos

| Método | Ruta | Permiso | OK |
| ------ | ---- | ------- | -- |
| GET | `/health` | público | 200 / 503 |
| GET | `/authors?limit=50&offset=0&q=texto` | público | 200 |
| GET | `/authors/<autor_id>` | público | 200 |
| GET | `/authors/<autor_id>/books` | público | 200 |
| POST | `/authors` | ADMIN | 201 |
| PUT | `/authors/<autor_id>` | ADMIN | 200 |
| PATCH | `/authors/<autor_id>` | ADMIN | 200 |
| DELETE | `/authors/<autor_id>` | ADMIN | 200 |
| POST | `/authors/<autor_id>/books/<isbn>` | ADMIN | 201 |
| DELETE | `/authors/<autor_id>/books/<isbn>` | ADMIN | 200 |

- Escrituras: `Authorization: Bearer <access_token>` validado por
  `library_shared` (`require_roles(ROLE_ADMIN)`): firma, HS256 fijo,
  expiración, `type=access`, claims `user_id`/`role_id`/`jti`/`iat`/`exp` y
  revocación `jwt:revoked:<jti>` en Redis. Primero 401, después 403; la
  validación del body ocurre solo después de autenticar.
- Lecturas: públicas; no leen el header `Authorization` ni consultan Redis.
- `limit` 1–200 (50 por defecto), `offset` ≥ 0, `q` ≤ 120 caracteres:
  búsqueda parcial sin distinguir mayúsculas en `nombre`, `apellido`,
  `nombre + ' ' + apellido` y `pais` (los `%` y `_` se tratan como texto).
  Orden: `apellido, nombre, autor_id`.

Ejemplo de autor (todas las respuestas usan `{"success": true, "data": ...}`):

```json
{"autor_id": 1, "nombre": "Laura", "apellido": "Gomez", "pais": "Mexico", "books_count": 3}
```

`GET /authors` agrega `"pagination": {"limit", "offset", "total", "q"}`.
`GET /authors/<id>/books` devuelve `{"author": {...}, "books": [{"isbn",
"titulo", "anio_publicacion", "orden"}]}` ordenado por título.

## Campos y validaciones

| Campo | Regla | POST | PUT | PATCH |
| ----- | ----- | ---- | --- | ----- |
| `nombre` | string no vacío, se recorta, ≤ 120 | obligatorio | obligatorio | opcional |
| `apellido` | string no vacío, se recorta, ≤ 120 | obligatorio | obligatorio | opcional |
| `pais` | string no vacío ≤ 80, o `null` | opcional (`null`) | **obligatorio** (puede ser `null`) | opcional (`null` lo borra) |

- `autor_id` en el body → **400 `FIELDS_NOT_ALLOWED`** (lo genera PostgreSQL
  y viene en la URL; nunca cambia).
- Campos desconocidos → **400 `UNKNOWN_FIELDS`** (lista en `details.fields`).
- `pais: ""` se rechaza (para borrar se usa `null`).
- PUT exige `pais` explícito para que un PUT nunca lo borre por omisión.
- PATCH solo modifica los campos enviados; cuerpo vacío → 400.
- Body que no es un objeto JSON → 400.

## DELETE de autor

- **Nunca borra libros**: desde `autores` no hay ninguna cascada.
- Autor **sin** relaciones → 200, se borra la fila de `autores`.
- Autor **con** relaciones → **409 `AUTHOR_HAS_BOOKS`** (con
  `details.books_count`); no se borra nada. Hay que quitar antes cada
  relación con `DELETE /authors/<id>/books/<isbn>`. Si una relación se crea
  justo entre la comprobación y el DELETE, `ON DELETE RESTRICT` lo impide y
  se devuelve el mismo 409.
- Autor inexistente → 404 `AUTHOR_NOT_FOUND`.

## Relaciones autor-libro

Las relaciones son un sub-recurso del autor: los libros de
`GET /authors/<id>/books` son exactamente esas filas de `libro_autor`.

`POST /authors/<autor_id>/books/<isbn>` — body opcional `{"orden": n}`
(1–32767). Sin `orden`, el autor se agrega **al final** de los autores
actuales del libro (`max(orden) + 1`, o 1 si el libro no tiene autores).

| Caso | Respuesta |
| ---- | --------- |
| Relación creada | 201 `{"autor_id", "isbn", "titulo", "anio_publicacion", "orden"}` |
| Autor inexistente | 404 `AUTHOR_NOT_FOUND` |
| Libro inexistente | 404 `BOOK_NOT_FOUND` |
| Relación ya existente | 409 `RELATION_ALREADY_EXISTS` (también si dos peticiones compiten: la PK lo impide) |

`DELETE /authors/<autor_id>/books/<isbn>` borra **solo** esa fila de
`libro_autor`; el autor y el libro permanecen (un libro puede quedarse sin
autores, el esquema lo permite). Si no existe: 404 `RELATION_NOT_FOUND`
(o `AUTHOR_NOT_FOUND` / `BOOK_NOT_FOUND` si lo que falta es el autor o el libro).

El ISBN de la URL se normaliza igual que en Books (`strip()` + mayúsculas
para la `X` final; los guiones se conservan).

### Coherencia con la caché de Books

Books solo cachea `GET /books` y `GET /books/<isbn>`, y esas respuestas **no
incluyen autores** (`/books-with-images` sí, pero no está cacheado). Por eso
Authors no necesita invalidar claves Redis de Books.

## Redis

Solo para seguridad (revocación de JWT, vía `library_shared`). Authors no
crea claves en Redis.

| Redis | GET públicos | POST/PUT/PATCH/DELETE |
| ----- | ------------ | --------------------- |
| disponible | 200 | normal |
| caído | **siguen funcionando** | **503 `AUTH_BACKEND_UNAVAILABLE`** (no se puede comprobar la revocación; nunca se deja pasar) |

## Health

`GET /health` (público):

| PostgreSQL | Redis | `status` | HTTP |
| ---------- | ----- | -------- | ---- |
| conectado | conectado | `healthy` | 200 |
| conectado | caído | `degraded` | 200 (las lecturas funcionan; un proxy sigue enviando tráfico) |
| caído | — | `unavailable` | 503 |

```json
{"success": true, "service": "authors", "status": "healthy", "database": "connected",
 "redis": "connected", "public_reads": "available", "writes": "available"}
```

No incluye hosts, usuarios ni contraseñas.

## Códigos de respuesta

| HTTP | `code` | Cuándo |
| ---- | ------ | ------ |
| 400 | `INVALID_INPUT`, `UNKNOWN_FIELDS`, `FIELDS_NOT_ALLOWED` | validación |
| 401 | `MISSING_TOKEN`, `INVALID_AUTHORIZATION_HEADER`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `TOKEN_REVOKED` | escritura sin token válido (incluye refresh usado como access) |
| 403 | `FORBIDDEN` | USER intentando modificar |
| 404 | `AUTHOR_NOT_FOUND`, `BOOK_NOT_FOUND`, `RELATION_NOT_FOUND`, `NOT_FOUND` | recurso o ruta inexistente |
| 405 | `METHOD_NOT_ALLOWED` | método no soportado |
| 409 | `AUTHOR_HAS_BOOKS`, `RELATION_ALREADY_EXISTS` | conflictos |
| 503 | `AUTH_BACKEND_UNAVAILABLE` | Redis caído en una escritura |
| 503 | `DATABASE_UNAVAILABLE` | PostgreSQL inaccesible |
| 500 | `INTERNAL_ERROR` | error inesperado (sin detalles internos) |

Formato de error: `{"success": false, "code": "...", "message": "..."}`
(más `details` cuando aplica).

## PostgreSQL y permisos

Base `library_db`, usuario `library_user`. **No hace falta script de
grants**: `library_user` ya tiene `SELECT, INSERT, UPDATE, DELETE` sobre
`autores`, `libro_autor` y `libros`, y `USAGE, SELECT` sobre
`autores_autor_id_seq` (`00_create_database.sql`, partes B/C). Authors solo
lee `libros`. No se modifica el esquema.

## Variables de entorno

Ver `.env.example`. Obligatorias: `DB_HOST`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `JWT_SECRET_KEY` (≥ 32, **igual** que Login, Books y Users) y
`REDIS_URL` (el **mismo** Redis). Opcionales: `FLASK_HOST` (`127.0.0.1`),
`FLASK_PORT` (`5003`), `FLASK_DEBUG` (`false`), `APP_ENV` (`development`;
en `production` se prohíbe `*` en CORS), `DB_PORT` (`5432`),
`REDIS_CONNECT_TIMEOUT_SECONDS` / `REDIS_SOCKET_TIMEOUT_SECONDS` (`2`),
`REDIS_HEALTH_CHECK_INTERVAL_SECONDS` (`30`), `CORS_ALLOWED_ORIGINS`.

## Instalación y ejecución

Windows (PowerShell), desde `apps\services\authors`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env      # completar valores reales
python -m pytest
python app.py                    # http://127.0.0.1:5003
```

CentOS 10 (más adelante), desde `apps/services/authors`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
python app.py    # 127.0.0.1:5003 detrás del reverse proxy HTTPS
```

## Pruebas

- Unitarias (`python -m pytest`): sin PostgreSQL ni Redis; un fake reproduce
  la PK de `libro_autor`, el RESTRICT de `autor_id`, la FK de `isbn` y el
  rollback.
- Integración (`tests/test_integration_postgres.py`): solo si existe
  `AUTHORS_IT_DB_NAME`, que **debe terminar en `_test`**. Necesita una base
  desechable con el esquema completo (01, 02, 06, 04, 05,
  `login_microservice.sql`, 07). Solo crea y borra sus propias filas
  (autores `IT-*`, ISBN `979111111111x`).

```powershell
$env:AUTHORS_IT_DB_PORT="5432"; $env:AUTHORS_IT_DB_NAME="library_authors_test"
$env:AUTHORS_IT_DB_USER="library_user"; $env:AUTHORS_IT_DB_PASSWORD="<password local>"
python -m pytest
```

## Ejemplos (curl)

En PowerShell usar `curl.exe`. `$ADMIN` / `$USER` son access tokens de Login
(`POST http://127.0.0.1:5001/login?format=json`).

```bash
# Listar / buscar (público)
curl -s "http://127.0.0.1:5003/authors?limit=10&offset=0&q=gomez"

# Un autor y sus libros (público)
curl -s http://127.0.0.1:5003/authors/1
curl -s http://127.0.0.1:5003/authors/1/books

# Crear (ADMIN) -> 201
curl -s -X POST http://127.0.0.1:5003/authors \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"nombre":"Gabriel","apellido":"García Márquez","pais":"Colombia"}'

# Editar parcialmente (ADMIN)
curl -s -X PATCH http://127.0.0.1:5003/authors/33 \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"pais":null}'

# Asociar libro (ADMIN) -> 201; orden opcional
curl -s -X POST http://127.0.0.1:5003/authors/33/books/9781000000000 \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"orden":2}'

# Quitar la relación (ADMIN) -> 200; no borra ni autor ni libro
curl -s -X DELETE -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5003/authors/33/books/9781000000000

# Borrar autor (ADMIN): 200 sin libros / 409 AUTHOR_HAS_BOOKS con libros
curl -s -X DELETE -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5003/authors/33

# USER intentando modificar -> 403 FORBIDDEN
curl -s -X POST http://127.0.0.1:5003/authors \
  -H "Authorization: Bearer $USER" -H "Content-Type: application/json" \
  -d '{"nombre":"X","apellido":"Y"}'

# Redis caído: GET sigue en 200; escrituras -> 503 AUTH_BACKEND_UNAVAILABLE;
# /health -> 200 "degraded"
curl -s http://127.0.0.1:5003/health
```
