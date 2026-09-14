# Library SOAP Service — Ejercicio 03

> **Nota sobre la ruta de este módulo:** el enunciado de la actividad de
> Electron describe la ubicación conceptual `app/services/soap/app.py`. La
> implementación equivalente del microservicio Flask se encuentra en
> `apps/library_soap_service/app.py` debido a la estructura real de este
> monorepo (ver `apps/`). No se movió ni se duplicó: sigue siendo el único
> `app.py` de este servicio.

Módulo Flask independiente que expone, en el mismo proceso:

- el contrato SOAP original (`POST /soap` + WSDL/XSD), que integra las
  aplicaciones de escritorio con el catálogo real de la librería del
  Ejercicio 02;
- un pequeño catálogo REST **bilingüe XML/JSON** (`/health`, `/books`,
  `/books/<isbn>`, `/cloud-concepts`, `/books-with-images`), agregado por
  `01_prompt_bilingue.md` sobre la misma aplicación Flask, **sin crear un
  segundo microservicio**.

## Arquitectura

```text
                         Flask app (app.py)
                            |
              +-------------+-------------+
              |                           |
              v                           v
          POST /soap                 catalog/*
          SOAP/XML                  REST XML / JSON
        (soap/*, sin cambios)     (?format=json|xml)
              |                           |
              +-------------+-------------+
                            |
                            v psycopg2 (db/connection.py)
                       PostgreSQL library_db
                            ^
                            |
                            | pg
                      Node.js Monolith
```

El monolito Node.js no se modifica. El módulo `catalog/` es nuevo y
deliberadamente independiente de `soap/`: comparte solo la capa de
conexión a PostgreSQL (`db/connection.py`), no las tablas/funciones de
`soap_module` ni la lógica de parsing SOAP.

## Estructura

```text
library_soap_service/
├── app.py
├── config/
│   └── settings.py
├── db/
│   ├── connection.py
│   └── repository.py        # consultas propias de soap_module (SOAP)
├── catalog/                  # nuevo: catálogo REST bilingüe XML/JSON
│   ├── format.py             # get_response_format(): ?format=xml|json
│   ├── errors.py             # CatalogError + INVALID_FORMAT/BOOK_NOT_FOUND/INTERNAL_ERROR
│   ├── repository.py         # SELECTs parametrizados sobre libros/conceptos/imagenes_libro
│   ├── serializers.py        # dict (JSON) / xml.etree bytes (XML), mismo modelo interno
│   └── http.py               # catalog_route(): helper común de negociación + errores
├── soap/
│   ├── service.py
│   ├── envelope.py
│   ├── faults.py
│   └── security.py
├── wsdl/
│   ├── library-classifier.wsdl
│   └── library-classifier.xsd
├── sql/
│   ├── soap_module.sql
│   └── 02_soap_routines.sql
├── docs/
├── tests/
│   ├── test_envelope.py               # SOAP (sin cambios)
│   ├── test_catalog_format.py         # ?format= (sin PostgreSQL)
│   ├── test_catalog_api.py            # /health + rutas de error (sin PostgreSQL)
│   ├── test_catalog_cloud_concepts.py # allowlist de conceptos Cloud + rutas de error (sin PostgreSQL)
│   ├── test_catalog_serializers_books_with_images.py # XML/JSON de /books-with-images (sin PostgreSQL)
│   └── test_uploads_libros.py         # GET /uploads/libros/<archivo> + path traversal (sin PostgreSQL)
├── uploads/
│   └── libros/                       # imágenes servidas por GET /uploads/libros/<archivo> (no versionadas)
├── .env.example
├── requirements.txt
└── README.md
```

## 1. Crear ambiente virtual

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configurar variables de entorno

Copia `.env.example` a `.env`.

Nunca subas `.env` al repositorio.

Para una base local:

```env
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=library_db_test
PGUSER=library_soap_user
PGPASSWORD=<solo-local>
```

Si PostgreSQL continúa en la VM de GCP y se usa un túnel local, ajusta `PGPORT`
al puerto local del túnel, por ejemplo `5433`.

## 3. Preparar PostgreSQL

No ejecutar primero contra la base real.

Utilizar una base temporal compatible con el esquema del Ejercicio 02.

Orden:

```text
1. Esquema y datos del Ejercicio 02 en library_db_test
2. sql/soap_module.sql
3. sql/02_soap_routines.sql
4. Grants para library_soap_user
```

El usuario SOAP debe:

- leer `public.libros`;
- leer `public.conceptos`;
- leer `public.libro_concepto`;
- leer `public.categorias`;
- leer `public.formatos` (usado por `GET /books` y `GET /books/{isbn}`);
- leer `public.imagenes_libro` (usado por `GET /books-with-images`);
- leer `public.autores` y `public.libro_autor` (usado por
  `GET /books-with-images` para los autores reales de cada libro);
- operar las tablas de `soap_module`;
- ejecutar las routines de `soap_module`;
- no tener acceso a `public.usuarios`;
- no tener privilegios DDL.

`formatos` e `imagenes_libro` son lecturas ya existentes, requeridas por el
catálogo REST bilingüe (`catalog/repository.py`). `autores` y
`libro_autor` son lecturas **nuevas** (Electron ejercicio 04): si
`library_soap_user` todavía no tiene `SELECT` sobre ellas, ejecutar en la
VM (conectado como un rol con privilegios, nunca como `postgres` desde la
aplicación):

```sql
GRANT SELECT ON TABLE public.autores TO library_soap_user;
GRANT SELECT ON TABLE public.libro_autor TO library_soap_user;
```

Ningún otro privilegio cambia y estos `GRANT` no son destructivos (no
alteran datos ni estructura).

## 4. Ejecutar pruebas unitarias sin PostgreSQL

Desde la raíz del proyecto:

```bash
python -m unittest discover -s tests -v
```

Estas pruebas validan el procesamiento manual del SOAP Envelope y los Faults.

## 5. Ejecutar Flask

```bash
python app.py
```

Endpoints:

```text
GET  /health
GET  /wsdl/library-classifier.wsdl
GET  /wsdl/library-classifier.xsd
POST /soap
```

Servicio local:

```text
http://127.0.0.1:5000/soap
```

## Actualizar la VM de GCP (git pull)

Esta actividad **no** creó un microservicio nuevo ni movió `app.py`: solo
modificó archivos existentes dentro de `apps/library_soap_service/`. En la
VM, dentro del checkout de este repo:

```bash
cd apps/library_soap_service
git pull
```

Archivos que cambian con este `git pull` (ver sección "Entrega final" del
reporte para el detalle completo): `app.py`, `config/settings.py`,
`catalog/repository.py`, `catalog/serializers.py`, `.env.example`,
`.gitignore`, `uploads/libros/.gitkeep`, y los tests nuevos en `tests/`.

Después del `pull`:

1. Si `library_soap_user` todavía no tiene `SELECT` sobre `autores` y
   `libro_autor`, ejecutar los `GRANT` de la sección "Preparar PostgreSQL"
   (conectado como un rol con privilegios sobre esas tablas, **no** como la
   propia aplicación).
2. Confirmar que las imágenes reales referenciadas por `imagenes_libro.url`
   están disponibles en el directorio que sirve `GET /uploads/libros/...`
   (por defecto `apps/library_soap_service/uploads/libros/`, o el que
   indique `UPLOADS_LIBROS_DIR` en `.env` si se configuró apuntando a otra
   carpeta, por ejemplo la del monolito Node.js si comparten filesystem).
3. Reiniciar el proceso Flask (`python app.py`, o el mecanismo que ya se
   use en la VM para mantenerlo corriendo — no hay un servicio
   systemd/gunicorn definido en este repo).

No se requiere cambiar nada en PostgreSQL aparte de los `GRANT` anteriores:
no hay migraciones de esquema en esta actividad.

## Operaciones v1

- `ObtenerConceptosPendientes`
- `RegistrarClasificacion`
- `ObtenerProgresoUsuario`

## SOAP Fault

Errores contractuales iniciales:

- `INVALID_XML`
- `INVALID_REQUEST`
- `INVALID_EMAIL`
- `INVALID_CLOUD_MODEL`
- `CONCEPT_NOT_FOUND`
- `BOOK_CONCEPT_NOT_FOUND`
- `DUPLICATE_CLASSIFICATION`
- `INTERNAL_ERROR`

Los detalles técnicos se registran en logs del servidor y no se exponen al
cliente.

## WS-Security

`soap/security.py` queda preparado como punto de extensión.

WS-Security se implementará posteriormente en la Tarea 1 al agregar
`ObtenerEstadisticasPorModelo`.

## Catálogo REST bilingüe (XML / JSON)

### Objetivo

Exponer datos de solo lectura del catálogo (`libros`, `conceptos`,
`imagenes_libro`) en el mismo microservicio Flask que ya sirve SOAP, con
**un único endpoint por recurso** que responde XML o JSON según el
parámetro `format` — sin rutas duplicadas (`/books-json`, `/books-xml`) ni
lógica de negocio repetida por formato.

### Parámetro `format`

Se implementa en `catalog/format.py::get_response_format()`, el único
lugar del código donde se valida:

| `format` recibido        | Resultado |
|---------------------------|-----------|
| ausente                   | `xml` (default) |
| `?format=xml`              | `xml` |
| `?format=json`             | `json` (insensible a mayúsculas) |
| cualquier otro valor (`?format=csv`) | `400 INVALID_FORMAT`, antes de tocar la base de datos |

Esta actividad usa `?format=` como mecanismo principal de negociación, no
el header `Accept`.

### Endpoints

| Method | Endpoint              | XML default | JSON          | Descripción |
|--------|------------------------|-------------|-----------------|-------------|
| GET    | `/health`              | Sí          | `?format=json`  | Estado del servicio. |
| GET    | `/books`               | Sí          | `?format=json`  | Lista de libros (isbn, título, año, precio, stock, categoría, formato). |
| GET    | `/books/{isbn}`        | Sí          | `?format=json`  | Un libro; `404 BOOK_NOT_FOUND` si no existe. |
| GET    | `/cloud-concepts`      | Sí          | `?format=json`  | Conceptos (`conceptos`) asociados a libros (`libro_concepto`), con su definición. |
| GET    | `/books-with-images`   | Sí          | `?format=json`  | Datos mínimos de cada libro (isbn, título, autores reales, año de publicación, precio) + sus imágenes reales (`imagenes_libro`). Es el endpoint que consume la app Electron. |
| GET    | `/uploads/libros/<archivo>` | Archivo (imagen) | No aplica | Sirve el archivo físico de una imagen de portada (ver "Imágenes estáticas" abajo). |
| POST   | `/soap`                | SOAP/XML    | No aplica        | Contrato SOAP original, sin cambios. |
| GET    | `/wsdl/library-classifier.wsdl` / `.xsd` | XML (archivo) | No aplica | Archivos WSDL/XSD originales; no se transforman a JSON. |

### Consultas y tablas utilizadas

- `/books`, `/books/{isbn}`: `libros` JOIN `categorias` JOIN `formatos`
  (nombres reales de columna verificados en `db/01_schema.sql`).
- `/cloud-concepts`: `libro_concepto` JOIN `conceptos` JOIN `libros`,
  filtrado por `WHERE lower(c.nombre) = ANY(%s)` contra la lista real de
  nombres de Cloud Computing (`catalog/repository.py::CLOUD_COMPUTING_CONCEPT_NAMES`:
  IaaS, PaaS, SaaS, FaaS, Bucket, Public Cloud, Private Cloud, Hybrid
  Cloud, Multicloud, Serverless). El esquema (`conceptos(concepto_id,
  nombre)`) no tiene una columna de categoría/tema, así que no hay forma
  de derivar "es de Cloud Computing" solo con una FK; la comparación es
  insensible a mayúsculas, pero la ortografía exacta de cada nombre no se
  verificó contra datos reales (ver "Pruebas" más abajo). Ningún dato del concepto
  (id, definición, isbn, título) se hardcodea: todo sigue viniendo de la
  consulta parametrizada.
- `/books-with-images`: **tres** `SELECT` independientes dentro de la misma
  transacción, combinados en Python por `isbn`
  (`catalog/repository.py::list_books_with_images()`):
  1. `libros` (isbn, titulo, anio_publicacion, precio);
  2. `libro_autor` JOIN `autores`, ordenado por `libro_autor.orden` (autores
     reales, en el orden de aparición correcto; un libro puede tener
     varios);
  3. `imagenes_libro`, ordenado por `orden` (imágenes reales; un libro sin
     imágenes responde con `images: []`).

  Se usan tres consultas en vez de un único JOIN de tres tablas a propósito:
  un libro puede tener varios autores **y** varias imágenes al mismo tiempo,
  así que un JOIN directo `libros × libro_autor × imagenes_libro` produciría
  el producto cartesiano autores × imágenes por libro (filas duplicadas que
  luego habría que des-duplicar). Construir `autores` e `images` desde su
  propia consulta y unirlas por `isbn` evita esa duplicación por diseño.

Todas las consultas están en `catalog/repository.py`, parametrizadas, y
reutilizan `db/connection.py::transaction()` (la misma capa de conexión
que ya usa SOAP), sin duplicar la configuración de PostgreSQL.

### Imágenes estáticas (`GET /uploads/libros/<archivo>`)

`imagenes_libro.url` guarda una ruta relativa, por ejemplo
`/uploads/libros/archivo.jpg` (mismo formato que usa el monolito Node.js en
`apps/web-monolito01/backend-node/src/public/uploads/libros/`, servida ahí
vía `express.static`). Para que un cliente XML (Electron u otro) pueda
mostrar realmente esa imagen, este microservicio Flask expone la misma ruta:

```text
GET /uploads/libros/<archivo>
```

Implementación (`app.py`):

- El nombre de archivo se normaliza con `os.path.basename()` antes de
  tocar el sistema de archivos: cualquier intento de incluir `../` u otra
  ruta se recorta al último segmento, igual que hace
  `apps/web-monolito01/backend-node/src/lib/uploadsFs.js::rutaFisicaDesdeUrl()`
  para el mismo problema en Node.js.
- `send_from_directory()` (Flask/Werkzeug) aplica además su propia
  protección contra path traversal: si el resultado no queda dentro del
  directorio configurado, responde `404` en vez de servir el archivo.
- No hay concatenación manual de rutas con `+` ni f-strings: la unión la
  hace `send_from_directory()`.

El directorio físico se configura con la variable de entorno opcional
`UPLOADS_LIBROS_DIR` (`.env.example`). Si no se define, se usa por defecto
`apps/library_soap_service/uploads/libros/` (creada en el repo con un
`.gitkeep`; el contenido real no se versiona, igual que en
`web-monolito01/.../uploads/libros/.gitignore`).

**Importante para la VM de GCP:** este directorio debe contener realmente
los archivos que `imagenes_libro.url` referencia. Si el proceso Flask corre
en la misma VM/filesystem que el monolito Node.js, la forma más simple es
apuntar `UPLOADS_LIBROS_DIR` directamente a
`apps/web-monolito01/backend-node/src/public/uploads/libros`; si no, hay
que copiar/sincronizar ahí los archivos reales. **No se inventó ningún
archivo de imagen para esta actividad.**

Verificado en este repo (sin acceso a la base de datos real de la VM):
`db/02_seed_30_per_table.sql` inserta URLs como
`/uploads/libros/seed-cover-001.jpg`, pero esos archivos **no existen
físicamente** en ninguna carpeta de uploads de este monorepo — son datos de
siembra de ejemplo, no archivos reales. Los archivos que sí existen
físicamente en este repo están en
`apps/web-monolito01/backend-node/src/public/uploads/libros/` con nombres
tipo `1788755786016-f0297c8a6adc.jpg` (subidos por el monolito Node.js), y
no coinciden con los nombres de `02_seed_30_per_table.sql`. Cuál de los dos
conjuntos (o si es un tercero) corresponde a la base real de la VM de GCP
no pudo verificarse aquí por falta de conectividad con esa base — ver
sección de pruebas más abajo. Cuando un `imagenes_libro.url` no tenga
archivo físico real detrás, `GET /uploads/libros/<archivo>` responde `404`
de forma controlada (no se inventa el archivo); Electron ya maneja ese caso
mostrando un placeholder (ver `apps/Electron-app/README.md`).

### Ejemplo XML (`GET /cloud-concepts`)

```xml
<cloudConcepts>
    <cloudConcept>
        <conceptId>12</conceptId>
        <concept>IaaS</concept>
        <definition>...</definition>
        <isbn>9781000000032</isbn>
        <bookTitle>Fundamentos de Cloud Computing</bookTitle>
    </cloudConcept>
</cloudConcepts>
```

### Ejemplo XML (`GET /books-with-images`)

```xml
<?xml version="1.0" encoding="utf-8"?>
<books>
    <book>
        <isbn>9781000000032</isbn>
        <titulo>Fundamentos de Cloud Computing</titulo>
        <autores>
            <autor>Nombre Apellido</autor>
        </autores>
        <anio_publicacion>2026</anio_publicacion>
        <precio>350.00</precio>
        <images>
            <image>
                <url>/uploads/libros/archivo.jpg</url>
                <alt>Portada de Fundamentos de Cloud Computing</alt>
                <order>1</order>
                <isCover>true</isCover>
            </image>
        </images>
    </book>
</books>
```

### Ejemplo JSON (`GET /books-with-images?format=json`)

```json
{
  "books": [
    {
      "isbn": "9781000000032",
      "titulo": "Fundamentos de Cloud Computing",
      "autores": ["Nombre Apellido"],
      "anio_publicacion": 2026,
      "precio": "350.00",
      "images": [
        {"url": "/uploads/libros/archivo.jpg", "alt": "Portada de Fundamentos de Cloud Computing", "order": 1, "isCover": true}
      ]
    }
  ]
}
```

### Errores

Formato consistente en XML y JSON (`catalog/serializers.py`), nunca con
stack traces, SQL ni credenciales:

```json
{"error": {"code": "BOOK_NOT_FOUND", "message": "Book not found"}}
```

```xml
<error><code>INVALID_FORMAT</code><message>Supported formats are xml and json</message></error>
```

| Código | HTTP | Cuándo |
|--------|------|--------|
| `INVALID_FORMAT` | 400 | `?format=` distinto de `xml`/`json`. |
| `BOOK_NOT_FOUND` | 404 | `/books/{isbn}` con un ISBN inexistente. |
| `INTERNAL_ERROR` | 500 | Fallo interno no controlado (incluida una base de datos no alcanzable); el detalle real solo se registra en el log del servidor. |

### Pruebas

```bash
cd apps/library_soap_service
python -m unittest discover -s tests -v
```

Incluye, sin requerir PostgreSQL:

- `test_catalog_format.py`, `test_catalog_api.py`,
  `test_catalog_cloud_concepts.py`: `?format=`, `/health`, que un fallo de
  base de datos produce un `500 INTERNAL_ERROR` controlado en vez de un
  stack trace, y la lista `CLOUD_COMPUTING_CONCEPT_NAMES`.
- `test_catalog_serializers_books_with_images.py`: alimenta directamente
  `catalog/serializers.py` con un libro de ejemplo (misma forma que
  devuelve `catalog_repository.list_books_with_images()`) y confirma que el
  XML y el JSON resultantes contienen `isbn`, `titulo`, `autores`/`autor`
  **en el orden correcto**, `anio_publicacion`, `precio` e
  `images`/`image` con `url`/`alt`/`order`/`isCover`; también que un libro
  sin autores o sin imágenes serializa `<autores></autores>` /
  `<images></images>` vacíos en vez de fallar.
- `test_uploads_libros.py`: sirve un archivo real desde un directorio
  temporal (`UPLOADS_LIBROS_DIR` apuntado ahí solo para la prueba),
  confirma `404` para un archivo inexistente, y confirma que un intento de
  path traversal (`..%2Fapp.py`, `../app.py`) nunca sirve un archivo fuera
  de ese directorio.

**No validan contra datos reales** el camino feliz de `/books`,
`/books/{isbn}`, `/cloud-concepts` ni `/books-with-images` (que
`/cloud-concepts` efectivamente excluye conceptos no-Cloud, que los
autores/imágenes reales de `/books-with-images` son los correctos, etc.),
porque no hubo una instancia PostgreSQL ni el servicio Flask real de GCP
(`http://34.51.73.237:5001`) alcanzables desde el entorno donde se
construyó esta funcionalidad (varios intentos de conexión directa
resultaron en "Connection refused"; ver reporte de entrega, sección
"Pruebas ejecutadas"). El código de `catalog/repository.py` fue verificado
manualmente contra `db/01_schema.sql` (nombres de tabla/columna reales)
pero no ejecutado contra una base con datos. **Antes de dar por cerrada
esta actividad, ejecuta tú mismo la verificación real de la sección
"Pruebas reales obligatorias" del prompt** (curl contra
`http://34.51.73.237:5001/books-with-images` + `npm start` en
`apps/Electron-app`), ya que es la única forma de confirmar autores/año/
precio/imágenes reales end-to-end.

## Restricciones de implementación

- No Spyne en el servidor inicial.
- No Zeep para construir el servidor.
- SOAP Envelope procesado manualmente con `xml.etree.ElementTree`.
- SQL parametrizado.
- Sin credenciales reales dentro del repositorio.
- El código Node.js del monolito no se modifica.
