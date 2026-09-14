# Library SOAP Service — Ejercicio 03

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
│   └── test_catalog_cloud_concepts.py # allowlist de conceptos Cloud + rutas de error (sin PostgreSQL)
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
- operar las tablas de `soap_module`;
- ejecutar las routines de `soap_module`;
- no tener acceso a `public.usuarios`;
- no tener privilegios DDL.

`formatos` e `imagenes_libro` son lecturas nuevas, requeridas por el
catálogo REST bilingüe (`catalog/repository.py`); ningún otro privilegio
cambia.

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
| GET    | `/books-with-images`   | Sí          | `?format=json`  | Datos mínimos de libro + sus imágenes (`imagenes_libro`). |
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
- `/books-with-images`: `libros` LEFT JOIN `imagenes_libro` (un libro sin
  imágenes responde con `images: []`).

Todas las consultas están en `catalog/repository.py`, parametrizadas, y
reutilizan `db/connection.py::transaction()` (la misma capa de conexión
que ya usa SOAP), sin duplicar la configuración de PostgreSQL.

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

### Ejemplo JSON (`GET /books-with-images?format=json`)

```json
{
  "books": [
    {
      "isbn": "9781000000032",
      "title": "Fundamentos de Cloud Computing",
      "images": [
        {"url": "/uploads/libros/cloud.jpg", "alt": "Portada", "order": 1, "isCover": true}
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
python -m unittest tests.test_envelope tests.test_catalog_format tests.test_catalog_api tests.test_catalog_cloud_concepts -v
```

`test_catalog_format.py`, `test_catalog_api.py` y
`test_catalog_cloud_concepts.py` no requieren PostgreSQL: validan
`?format=`, `/health`, que un fallo de base de datos produce un `500
INTERNAL_ERROR` controlado en vez de un stack trace (incluido para
`/cloud-concepts`), y que la lista `CLOUD_COMPUTING_CONCEPT_NAMES`
contiene exactamente los 10 nombres esperados. **No validan el camino
feliz de `/books`, `/books/{isbn}`, `/cloud-concepts` ni
`/books-with-images` contra datos reales** (que `/cloud-concepts`
efectivamente excluye conceptos no-Cloud y solo devuelve
IaaS/PaaS/SaaS/FaaS/Bucket/Public Cloud/Private Cloud/Hybrid
Cloud/Multicloud/Serverless), porque no había una instancia PostgreSQL
alcanzable en el entorno donde se construyó esta funcionalidad (ver el
reporte de entrega, sección "Pendientes"). El código de
`catalog/repository.py` fue verificado manualmente contra
`db/01_schema.sql` (nombres de tabla/columna reales) pero no ejecutado
contra una base con datos.

## Restricciones de implementación

- No Spyne en el servidor inicial.
- No Zeep para construir el servidor.
- SOAP Envelope procesado manualmente con `xml.etree.ElementTree`.
- SQL parametrizado.
- Sin credenciales reales dentro del repositorio.
- El código Node.js del monolito no se modifica.
