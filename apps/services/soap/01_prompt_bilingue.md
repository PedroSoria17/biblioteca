PROMPT 01 — Convertir el microservicio Flask SOAP/XML en bilingüe XML + JSON

Objetivo general

Modificar el microservicio Flask existente para que todos sus endpoints puedan responder indistintamente en XML o JSON.

El comportamiento debe seguir exactamente estas reglas académicas:

XML es el formato por defecto.

Si se envía ?format=json, la respuesta debe ser JSON.

Si se envía ?format=xml, la respuesta debe ser XML.

Todos los endpoints deben soportar ambas representaciones.

Deben agregarse dos nuevos endpoints:

conceptos de Cloud Computing junto con datos de libros;

datos mínimos de libros junto con sus imágenes.

IMPORTANTE:

No crear otro microservicio separado.

No implementar todavía la aplicación Java.

No romper el SOAP existente.

No mover el proyecto únicamente para imitar la ruta sugerida por el profesor.

No incluir credenciales reales ni secretos en el repositorio.

No afirmar que una prueba pasó si no fue ejecutada realmente.

1. Inspección previa obligatoria

Antes de modificar cualquier archivo:

Inspecciona completamente la estructura real del repositorio.

Localiza el microservicio Flask SOAP/XML existente.

Revisa especialmente:

apps/library_soap_service/

y su archivo principal:

apps/library_soap_service/app.py

Las instrucciones del profesor mencionan una ruta conceptual:

app/services/soap/app.py

pero este repositorio utiliza otra estructura.

NO reorganices el proyecto únicamente para hacer coincidir esa ruta.

Identifica:

rutas Flask existentes;

/soap;

/health;

WSDL;

XSD;

conexión a PostgreSQL;

repositories;

services;

serializers XML existentes;

tests existentes.

Revisa el esquema real de PostgreSQL antes de escribir SQL.

Tablas relevantes actuales:

libros
conceptos
libro_concepto
categorias
imagenes_libro
formatos

Verifica nombres y columnas reales antes de utilizarlas.

No modifiques código hasta haber terminado esta inspección.

2. Regla de selección de formato

La representación de respuesta debe seleccionarse mediante el parámetro:

format

Ejemplos:

GET /books

Debe responder XML.

GET /books?format=xml

Debe responder XML.

GET /books?format=json

Debe responder JSON.

La lógica debe ser equivalente conceptualmente a:

response_format = request.args.get("format", "xml").lower()

No es obligatorio usar exactamente ese código.

Regla obligatoria:

SIN format → XML
format=xml → XML
format=json → JSON

Si llega un valor distinto:

?format=csv

devuelve un error controlado, por ejemplo HTTP 400.

3. No utilizar Accept como mecanismo principal

No implementes esta actividad basándote principalmente en:

Accept: application/json
Accept: application/xml

La evaluación debe poder demostrarse mediante:

?format=json

Puedes conservar soporte adicional por headers si ya existe y no interfiere, pero la lógica principal debe utilizar el query parameter format.

4. Arquitectura deseada

No dupliques consultas ni lógica de negocio por formato.

Debe existir conceptualmente:

HTTP endpoint
      ↓
repository/service
      ↓
datos Python
      ↓
serializer
   ┌───────┴───────┐
   ↓               ↓
 XML              JSON

NO crear:

/books-json
/books-xml

NO duplicar:

get_books_json()
get_books_xml()

si ambas hacen la misma consulta.

Debe existir una sola fuente de datos y cambiar únicamente la serialización.

5. Mantener SOAP existente

El módulo SOAP actual debe continuar funcionando.

No elimines ni rompas:

POST /soap

ni las operaciones actuales:

ObtenerConceptosPendientes
RegistrarClasificacion
ObtenerProgresoUsuario

No modifiques innecesariamente:

library-classifier.wsdl
library-classifier.xsd

No conviertas SOAP a REST.

La arquitectura debe coexistir así:

                         Flask app
                            |
              +-------------+-------------+
              |                           |
              v                           v
          POST /soap                 REST endpoints
          SOAP/XML                  XML / JSON
              |                           |
              +-------------+-------------+
                            |
                       PostgreSQL

6. Endpoint GET /books

Si ya existe una ruta equivalente, reutilízala y modifícala.

Si no existe, créala.

Debe permitir:

GET /books

Respuesta XML.

GET /books?format=xml

Respuesta XML.

GET /books?format=json

Respuesta JSON.

Debe obtener datos reales de PostgreSQL.

Devuelve información útil de los libros, sin exponer datos innecesarios.

Como mínimo:

isbn
titulo
anio_publicacion
precio
stock
categoria
formato

si esos campos están disponibles mediante la estructura actual.

No inventes joins ni columnas.

7. Endpoint GET /books/<isbn>

Debe existir:

GET /books/<isbn>

Ejemplo:

GET /books/9781000000032

→ XML

GET /books/9781000000032?format=json

→ JSON

Debe consultar exactamente el mismo libro y devolver los mismos datos conceptuales.

Si no existe:

HTTP 404

El error debe respetar el formato solicitado.

Ejemplo JSON:

{
  "error": {
    "code": "BOOK_NOT_FOUND",
    "message": "Book not found"
  }
}

Ejemplo XML:

<error>
    <code>BOOK_NOT_FOUND</code>
    <message>Book not found</message>
</error>

Sin format, el error debe ser XML.

8. Endpoint nuevo — conceptos Cloud con datos de libros

Agrega un endpoint para obtener conceptos de Cloud Computing junto con información de los libros donde aparecen.

Ruta recomendada:

GET /cloud-concepts

Si la arquitectura real sugiere otra ruta equivalente, úsala y documenta la decisión.

Debe poder responder:

GET /cloud-concepts

→ XML

GET /cloud-concepts?format=json

→ JSON

Debe obtener de PostgreSQL conceptos como:

IaaS
PaaS
SaaS
FaaS

No hardcodees esos conceptos si ya existen en la base.

Consulta las tablas reales, probablemente:

conceptos
libro_concepto
libros
categorias

Verifica primero.

Cada elemento debería incluir, como mínimo:

concepto_id
concepto
definicion
isbn
titulo_libro

Puede incluir categoría si ya está disponible y resulta útil.

Ejemplo conceptual JSON:

{
  "cloudConcepts": [
    {
      "conceptId": 12,
      "concept": "IaaS",
      "definition": "...",
      "isbn": "9781000000032",
      "bookTitle": "Fundamentos de Cloud Computing"
    }
  ]
}

Ejemplo conceptual XML:

<cloudConcepts>
    <cloudConcept>
        <conceptId>12</conceptId>
        <concept>IaaS</concept>
        <definition>...</definition>
        <isbn>9781000000032</isbn>
        <bookTitle>Fundamentos de Cloud Computing</bookTitle>
    </cloudConcept>
</cloudConcepts>

XML y JSON deben representar los mismos datos.

9. Endpoint nuevo — libros con imágenes

Agrega un endpoint que permita obtener datos mínimos de libros junto con sus imágenes.

Ruta recomendada:

GET /books-with-images

Debe soportar:

GET /books-with-images

→ XML

GET /books-with-images?format=json

→ JSON

Utiliza las tablas reales:

libros
imagenes_libro

Verifica nombres y relaciones.

Cada libro debe incluir únicamente datos mínimos útiles, por ejemplo:

isbn
titulo
imagenes

Dentro de cada imagen, si existen:

url
texto_alternativo
orden
es_portada

Ejemplo conceptual JSON:

{
  "books": [
    {
      "isbn": "9781000000032",
      "title": "Fundamentos de Cloud Computing",
      "images": [
        {
          "url": "/uploads/libros/cloud.jpg",
          "alt": "Portada",
          "order": 1,
          "isCover": true
        }
      ]
    }
  ]
}

Ejemplo conceptual XML:

<books>
    <book>
        <isbn>9781000000032</isbn>
        <title>Fundamentos de Cloud Computing</title>
        <images>
            <image>
                <url>/uploads/libros/cloud.jpg</url>
                <alt>Portada</alt>
                <order>1</order>
                <isCover>true</isCover>
            </image>
        </images>
    </book>
</books>

10. Serialización JSON

Utiliza las capacidades estándar de Flask.

No construyas JSON concatenando strings.

Mantén estructura consistente.

Debe usarse:

Content-Type: application/json

para respuestas JSON.

11. Serialización XML

Utiliza una construcción segura de XML.

Preferentemente reutiliza:

xml.etree.ElementTree

si ya está presente.

No concatenes datos provenientes de PostgreSQL directamente como XML sin escaping.

Debe utilizarse:

Content-Type: application/xml

o equivalente adecuado.

12. Helper común de formato

Implementa una forma centralizada de resolver el formato.

Conceptualmente algo como:

get_response_format()

Debe devolver:

xml
json

y validar valores inválidos.

No copies esta validación en cada endpoint.

13. Helper común de respuestas

Si resulta conveniente, crea helpers reutilizables para:

serialize_response(data, root_name, format)
serialize_error(code, message, status, format)

Los nombres son conceptuales.

El objetivo es evitar duplicación.

14. PostgreSQL

Reutiliza la capa actual de conexión cuando sea apropiado.

No:

hardcodees passwords;

uses postgres desde Flask;

concatenes SQL con parámetros del usuario;

expongas usuarios;

expongas password hashes;

cambies tablas del monolito sin necesidad.

Trabaja contra la configuración actual.

La base utilizada actualmente en desarrollo es:

library_db_test

No cambies automáticamente a otra base.

Las consultas deben ser parametrizadas cuando reciban valores del usuario.

15. Reutilización de repository/service

Si la estructura actual ya tiene:

db/repository.py
soap/service.py

no mezcles innecesariamente las nuevas consultas REST con la lógica SOAP si eso genera acoplamiento confuso.

Puedes:

extender el repository existente con consultas claramente separadas; o

crear un módulo REST/catalog repository específico.

Elige el cambio mínimo y más limpio.

No dupliques conexión a PostgreSQL si ya existe una implementación correcta.

16. Endpoint /health bilingüe

El endpoint existente:

GET /health

también debe respetar la regla de la actividad.

Por defecto:

GET /health

→ XML

Con:

GET /health?format=json

→ JSON

Ejemplo XML:

<health>
    <status>ok</status>
    <service>library_soap_service</service>
</health>

Ejemplo JSON:

{
  "status": "ok",
  "service": "library_soap_service"
}

No rompas su finalidad actual.

17. Todos los endpoints REST deben ser bilingües

Revisa TODOS los endpoints HTTP no-SOAP que existan en app.py.

Cada endpoint de datos deberá cumplir:

sin format → XML
?format=xml → XML
?format=json → JSON

La excepción es:

POST /soap

que debe continuar siendo SOAP/XML porque forma parte del contrato SOAP.

También los endpoints que publican archivos:

/wsdl/library-classifier.wsdl
/wsdl/library-classifier.xsd

pueden continuar devolviendo sus archivos XML originales; no deben transformarse artificialmente a JSON.

Documenta claramente esta excepción.

18. Manejo de errores bilingüe

Los endpoints REST nuevos deben devolver errores en el mismo formato solicitado.

Casos mínimos:

BOOK_NOT_FOUND
INVALID_FORMAT
INTERNAL_ERROR

Ejemplo:

GET /books/NO-EXISTE

→ XML 404

GET /books/NO-EXISTE?format=json

→ JSON 404

Para:

GET /books?format=csv

devuelve un error controlado, por ejemplo:

{
  "error": {
    "code": "INVALID_FORMAT",
    "message": "Supported formats are xml and json"
  }
}

o su equivalente XML.

No devuelvas:

stack traces;

SQL;

passwords;

variables de entorno;

rutas internas.

Los detalles técnicos pueden registrarse en logs del servidor.

19. Pruebas obligatorias

Ejecuta pruebas reales para demostrar como mínimo lo siguiente.

Health

GET /health

PASS si responde XML.

GET /health?format=json

PASS si responde JSON.

Books

GET /books

PASS si responde XML.

GET /books?format=json

PASS si responde JSON.

Book individual

Utiliza un ISBN que exista realmente en la base.

GET /books/<isbn>

PASS si responde XML.

GET /books/<isbn>?format=json

PASS si responde JSON.

Cloud concepts

GET /cloud-concepts

o la ruta final elegida.

PASS si responde XML e incluye datos reales de los conceptos Cloud y sus libros.

GET /cloud-concepts?format=json

PASS si responde JSON equivalente.

Confirma específicamente que aparecen, si existen en la base:

IaaS
PaaS
SaaS
FaaS

Books with images

GET /books-with-images

o la ruta final elegida.

PASS si responde XML.

GET /books-with-images?format=json

PASS si responde JSON.

Debe incluir imágenes reales registradas en imagenes_libro.

XML por defecto

Confirma específicamente:

GET /books

SIN format

→ XML.

ISBN inexistente

GET /books/ISBN_INEXISTENTE

→ XML 404.

GET /books/ISBN_INEXISTENTE?format=json

→ JSON 404.

Format inválido

GET /books?format=csv

→ error controlado.

Regression SOAP

Ejecuta los tests existentes del módulo SOAP.

Comprueba al menos que:

POST /soap

sigue disponible y que las pruebas anteriores no fueron afectadas.

No afirmes PASS si no ejecutaste realmente la prueba.

20. Verificación contra PostgreSQL

Verifica que:

/books obtiene registros reales de libros;

/cloud-concepts obtiene conceptos reales de conceptos y libro_concepto;

/books-with-images obtiene datos reales de imagenes_libro.

No insertes datos nuevos únicamente para hacer parecer que el endpoint funciona, salvo que sea estrictamente necesario y esté claramente documentado.

Si no existe algún dato esperado, repórtalo en lugar de inventarlo.

21. Seguridad

Nunca:

agregues .env al repositorio;

hardcodees una contraseña;

muestres credenciales reales;

uses postgres como usuario de la aplicación;

expongas password_hash;

retornes stack traces;

incluyas SQL en errores HTTP;

hagas DROP DATABASE;

borres datos existentes;

modifiques permisos innecesariamente.

Revisa .gitignore.

22. README

Actualiza la documentación del módulo explicando:

objetivo del microservicio bilingüe;

arquitectura;

ubicación real del servicio;

cómo ejecutar Flask;

conexión/configuración mediante .env;

endpoints;

parámetro format;

XML como formato por defecto;

ejemplos XML;

ejemplos JSON;

endpoint de conceptos Cloud;

endpoint de libros con imágenes;

manejo de errores;

pruebas.

Incluye una tabla similar a:

Método

Endpoint

XML default

JSON

GET

/health

Sí

?format=json

GET

/books

Sí

?format=json

GET

/books/{isbn}

Sí

?format=json

GET

/cloud-concepts

Sí

?format=json

GET

/books-with-images

Sí

?format=json

POST

/soap

SOAP/XML

No aplica

Adapta las rutas si la implementación final usa nombres distintos.

23. Evidencia académica

Cuando termines, indica exactamente qué screenshots debo tomar.

Necesito como mínimo evidencia de:

Flask ejecutándose.

/health en XML.

/health?format=json.

/books en XML.

/books?format=json.

/books/<isbn> en XML.

/books/<isbn>?format=json.

endpoint Cloud en XML.

endpoint Cloud en JSON.

endpoint libros + imágenes en XML.

endpoint libros + imágenes en JSON.

ISBN inexistente en XML.

ISBN inexistente en JSON.

format inválido.

pruebas automatizadas pasando.

consulta PostgreSQL que demuestre que los datos Cloud existen.

consulta PostgreSQL que demuestre que las imágenes existen.

evidencia de que /soap continúa funcionando.

24. Revisión final obligatoria

Antes de finalizar:

Revisa todos los cambios.

Ejecuta los tests.

Verifica XML por defecto.

Verifica ?format=json.

Verifica ?format=xml.

Verifica los endpoints nuevos.

Confirma que SOAP continúa funcionando.

Revisa WSDL/XSD y confirma que no fueron alterados innecesariamente.

Ejecuta git diff.

Confirma que ningún secreto fue agregado.

Confirma que no se creó un segundo microservicio innecesario.

25. Reporte final obligatorio

Cuando termines dame un reporte con esta estructura.

A. Inspección inicial

Describe qué encontraste realmente en el repositorio:

ubicación de Flask;

endpoints existentes;

estructura de acceso a PostgreSQL;

tests;

estructura SOAP.

B. Archivos modificados

Lista exacta.

C. Archivos creados

Lista exacta.

D. Endpoints finales

Tabla:

METHOD | ENDPOINT | XML | JSON | DESCRIPCIÓN

E. Implementación de format

Explica exactamente cómo:

?format=json

selecciona JSON y cómo la ausencia de format produce XML.

F. Conceptos Cloud

Explica:

endpoint;

consulta;

tablas utilizadas;

campos devueltos;

evidencia de IaaS/PaaS/SaaS/FaaS.

G. Libros + imágenes

Explica:

endpoint;

consulta;

tablas utilizadas;

datos mínimos devueltos.

H. Pruebas ejecutadas

Para cada prueba:

comando
resultado real
PASS / FAIL

No inventes resultados.

I. Evidencias recomendadas

Lista exactamente qué debo capturar para mi entrega.

J. Problemas encontrados

Documenta cualquier discrepancia entre la ruta indicada por el profesor:

app/services/soap/app.py

y la estructura real:

apps/library_soap_service/app.py

No reorganices el repositorio únicamente por esa diferencia.

K. Pendientes

Si algo no pudo probarse realmente, indícalo expresamente.

REGLA FINAL

El requisito académico principal es:

MISMO MICROSERVICIO FLASK
+
SOAP EXISTENTE SIN ROMPER
+
XML POR DEFAULT
+
?format=json PARA JSON
+
TODOS LOS ENDPOINTS REST EN AMBOS FORMATOS
+
ENDPOINT CLOUD CONCEPTS + BOOK DATA
+
ENDPOINT BOOK MINIMAL DATA + IMAGES

No crees un segundo microservicio.

No implementes Java en esta actividad.

No cambies la arquitectura más de lo necesario.

============================================================
REPORTE DE ENTREGA
============================================================

Nota sobre el proceso: este archivo cambió por completo (de una
especificación "microservicio nuevo + Accept header" a esta especificación
"mismo Flask + `?format=`") mientras ya se había implementado y probado la
primera versión, como `apps/cloud_microservice/`. Se confirmó contigo el
cambio de rumbo antes de continuar; esa carpeta separada fue eliminada y
todo el trabajo descrito abajo se hizo sobre `apps/library_soap_service/`,
sin crear un segundo microservicio.

## A. Inspección inicial

- **Ubicación de Flask:** `apps/library_soap_service/app.py` (único
  proceso Flask del módulo SOAP). No existía ningún endpoint REST previo;
  solo `GET /health`, `GET /wsdl/library-classifier.wsdl`, `GET
  /wsdl/library-classifier.xsd` y `POST /soap`.
- **Endpoints existentes:** los cuatro anteriores, sin cambios en `/soap`
  ni en los archivos WSDL/XSD.
- **Estructura de acceso a PostgreSQL:** `db/connection.py` expone
  `open_connection()` y el context manager `transaction()` (commit/rollback
  automático), leyendo credenciales desde `config/settings.py`
  (`PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`, con `load_dotenv()`).
  `db/repository.py` ya existente contiene únicamente consultas del
  esquema `soap_module` (clasificadores, clientes_servidos,
  clasificaciones_cloud) — no tenía nada reutilizable para `libros`,
  `conceptos` o `imagenes_libro`.
- **Tests existentes:** `tests/test_envelope.py` (unittest, sin pytest
  instalado en el entorno; `Flask 3.1.3`, `psycopg2-binary 2.9.13`,
  `python-dotenv 1.2.3` confirmados en `.venv`).
- **Estructura SOAP:** `soap/envelope.py` (parseo manual con
  `xml.etree.ElementTree`), `soap/faults.py` (`SoapServiceError` +
  `build_fault`), `soap/service.py` (dispatch de las 3 operaciones),
  `soap/security.py` (punto de extensión WS-Security, sin cambios).
- **Esquema real verificado en `db/01_schema.sql`** antes de escribir SQL
  nuevo: `libros(isbn, titulo, anio_publicacion, precio, stock,
  formato_id, categoria_id, ...)`, `categorias(categoria_id, nombre)`,
  `formatos(formato_id, nombre)`, `conceptos(concepto_id, nombre)`,
  `libro_concepto(isbn, concepto_id, definicion)`,
  `imagenes_libro(imagen_id, isbn, url, texto_alternativo, orden,
  es_portada)`. Ningún nombre de columna fue inventado.
- **PostgreSQL no alcanzable en este entorno:** `apps/library_soap_service/.env`
  apunta a `127.0.0.1:5433`; una prueba de socket confirmó "Connection
  refused" (sin servidor local ni túnel activo aquí). Esto condicionó qué
  pruebas pudieron ejecutarse de verdad (ver sección H).

## B. Archivos modificados

| Archivo | Cambio |
|---|---|
| `apps/library_soap_service/app.py` | Se agregaron los imports de `catalog.*`; `GET /health` ahora usa `catalog_route()` (XML por defecto, `?format=json`); se agregaron las rutas `GET /books`, `GET /books/<isbn>`, `GET /cloud-concepts`, `GET /books-with-images`. `POST /soap` y las rutas `/wsdl/*` quedaron intactas (mismo código, mismo orden). |
| `apps/library_soap_service/README.md` | Se agregó documentación del catálogo REST bilingüe (arquitectura, endpoints, `?format=`, ejemplos, errores, pruebas) y se actualizó la lista de privilegios sugeridos para `library_soap_user` (agrega lectura de `formatos` e `imagenes_libro`). |
| `apps/library_soap_service/sql/soap_module.sql` | Se agregaron, como comentario (no ejecutable automáticamente, igual que el resto del bloque de GRANTs), dos `GRANT SELECT` sugeridos: `public.formatos` y `public.imagenes_libro` para `library_soap_user`. Ninguna tabla, función ni Fault SOAP existente fue tocada. |

No se modificó ningún archivo de `apps/web-monolito01/` ni del monolito
Node.js. No se modificó `library-classifier.wsdl`, `library-classifier.xsd`,
`soap/envelope.py`, `soap/faults.py`, `soap/service.py`, `soap/security.py`,
`db/repository.py` ni `db/connection.py`.

## C. Archivos creados

```
apps/library_soap_service/catalog/__init__.py
apps/library_soap_service/catalog/format.py        # get_response_format(): ?format= -> "xml"/"json"
apps/library_soap_service/catalog/errors.py         # CatalogError, INVALID_FORMAT/BOOK_NOT_FOUND/INTERNAL_ERROR
apps/library_soap_service/catalog/repository.py     # SELECTs parametrizados (libros/conceptos/imagenes_libro)
apps/library_soap_service/catalog/serializers.py     # dict (JSON) / xml.etree bytes (XML)
apps/library_soap_service/catalog/http.py            # catalog_route(): helper común format+respuesta+error
apps/library_soap_service/tests/test_catalog_format.py
apps/library_soap_service/tests/test_catalog_api.py
```

(La carpeta `apps/cloud_microservice/` que se había creado bajo la
especificación anterior del archivo fue eliminada por completo, como se
acordó contigo.)

## D. Endpoints finales

| METHOD | ENDPOINT | XML | JSON | DESCRIPCIÓN |
|---|---|---|---|---|
| GET | `/health` | Sí (default) | `?format=json` | Estado del servicio. |
| GET | `/books` | Sí (default) | `?format=json` | Lista de libros con categoría y formato. |
| GET | `/books/<isbn>` | Sí (default) | `?format=json` | Un libro; `404 BOOK_NOT_FOUND` si no existe. |
| GET | `/cloud-concepts` | Sí (default) | `?format=json` | Conceptos (`conceptos`+`libro_concepto`) con el libro donde aparecen. |
| GET | `/books-with-images` | Sí (default) | `?format=json` | Libro (isbn, título) + sus imágenes. |
| POST | `/soap` | SOAP/XML (siempre) | No aplica | Contrato SOAP original, sin cambios. |
| GET | `/wsdl/library-classifier.wsdl`, `/wsdl/library-classifier.xsd` | XML (archivo original) | No aplica | Documentado como excepción explícita: no se transforman a JSON. |

## E. Implementación de `format`

`catalog/format.py::get_response_format(request)` es el único lugar que
resuelve el formato; todas las rutas nuevas y `/health` lo invocan a
través de `catalog/http.py::catalog_route()`:

- `request.args.get("format")` ausente o vacío → `"xml"` (default).
- `"xml"` (cualquier capitalización) → `"xml"`.
- `"json"` (cualquier capitalización) → `"json"`.
- cualquier otro valor (`csv`, `yaml`, etc.) → se lanza
  `CatalogError("INVALID_FORMAT", ..., 400)` **antes** de llamar a
  `catalog/repository.py`, o sea antes de tocar PostgreSQL.
- `catalog_route()` intenta resolver el formato primero; si eso falla,
  renderiza el propio error `INVALID_FORMAT` en XML (el default
  documentado), porque en ese momento no hay un formato válido en el que
  responder. Si el formato sí se resolvió y el fallo ocurre después
  (recurso no encontrado, error interno), el error se serializa en el
  formato ya resuelto.
- La serialización XML/JSON (`catalog/serializers.py`) parte siempre del
  mismo `dict` Python devuelto por `catalog/repository.py`: no hay
  `get_books_json()` / `get_books_xml()` duplicados, solo
  `books_to_dict()` y `books_to_xml()` operando sobre los mismos datos.

## F. Conceptos Cloud

- **Endpoint:** `GET /cloud-concepts` (`?format=json` para JSON).
- **Consulta** (`catalog/repository.py::list_cloud_concepts`):
  ```sql
  SELECT c.concepto_id, c.nombre, lc.definicion, lc.isbn, l.titulo
  FROM libro_concepto lc
  JOIN conceptos c ON c.concepto_id = lc.concepto_id
  JOIN libros l ON l.isbn = lc.isbn
  ORDER BY c.concepto_id, lc.isbn;
  ```
- **Tablas utilizadas:** `conceptos`, `libro_concepto`, `libros`. Sin
  `WHERE nombre IN (...)`: no se hardcodea IaaS/PaaS/SaaS/FaaS en Python;
  lo que exista en `conceptos` aparece tal cual vía el JOIN.
- **Campos devueltos:** `conceptId`, `concept`, `definition`, `isbn`,
  `bookTitle` (mismos nombres en JSON y XML).
- **Evidencia de IaaS/PaaS/SaaS/FaaS:** **no verificada en este entorno**
  porque PostgreSQL no está alcanzable (ver sección K). La consulta está
  escrita y verificada contra el esquema real, pero no se ejecutó contra
  datos reales.

## G. Libros + imágenes

- **Endpoint:** `GET /books-with-images` (`?format=json` para JSON).
- **Consulta** (`catalog/repository.py::list_books_with_images`):
  ```sql
  SELECT l.isbn, l.titulo, i.url, i.texto_alternativo, i.orden, i.es_portada
  FROM libros l
  LEFT JOIN imagenes_libro i ON i.isbn = l.isbn
  ORDER BY l.isbn, i.orden;
  ```
  (`LEFT JOIN` para que un libro sin imágenes siga apareciendo, con
  `images: []`.)
- **Tablas utilizadas:** `libros`, `imagenes_libro`.
- **Datos mínimos devueltos:** por libro, `isbn` y `title`; por imagen,
  `url`, `alt`, `order`, `isCover`.

## H. Pruebas ejecutadas

Comando ejecutado:

```
cd apps/library_soap_service
./.venv/Scripts/python.exe -m unittest tests.test_envelope tests.test_catalog_format tests.test_catalog_api -v
```

Resultado real (16/16 tests, todos ejecutados de verdad):

| # | Prueba | Resultado real | PASS/FAIL |
|---|---|---|---|
| 1 | `test_parse_registrar_clasificacion` (SOAP, preexistente) | Parseo correcto del envelope | PASS |
| 2 | `test_invalid_xml_returns_service_error` (SOAP, preexistente) | `INVALID_XML` lanzado | PASS |
| 3 | `test_fault_is_well_formed_xml` (SOAP, preexistente) | Fault XML bien formado | PASS |
| 4 | `?format=` ausente → `xml` | `get_response_format() == "xml"` | PASS |
| 5 | `?format=xml` → `xml` | `== "xml"` | PASS |
| 6 | `?format=json` → `json` | `== "json"` | PASS |
| 7 | `?format=JSON` (mayúsculas) → `json` | `== "json"` | PASS |
| 8 | `?format=` vacío → `xml` | `== "xml"` | PASS |
| 9 | `?format=csv` → error | `CatalogError` código `INVALID_FORMAT`, status 400 | PASS |
| 10 | `GET /health` sin format | 200, `Content-Type application/xml`, `<health><status>ok</status>...` | PASS |
| 11 | `GET /health?format=json` | 200, JSON `{"status":"ok","service":"library_soap_service"}` | PASS |
| 12 | `GET /health?format=xml` | 200, XML explícito | PASS |
| 13 | `GET /books?format=csv` | 400, XML, `INVALID_FORMAT`, sin llamar a PostgreSQL | PASS |
| 14 | `GET /books/9781000000032?format=csv` | 400, XML, `INVALID_FORMAT` | PASS |
| 15 | `GET /books` con PostgreSQL no alcanzable | 500, XML, `INTERNAL_ERROR`, sin traceback/`psycopg2` en el body | PASS |
| 16 | `POST /soap` con `Content-Type: text/plain` (regresión) | 415, SOAP Fault `INVALID_CONTENT_TYPE`, ruta sigue registrada | PASS |

Adicionalmente se levantó el servicio real (`python app.py`, puerto 5178)
y se validó con `curl` en vivo (no solo `test_client()`):

| Prueba en vivo | Comando | Resultado real |
|---|---|---|
| `/health` default | `curl $B/health` | `200`, XML |
| `/health?format=json` | `curl $B/health?format=json` | `200`, JSON |
| `/books` | `curl $B/books` | `500 INTERNAL_ERROR` (XML) — DB no alcanzable, error controlado |
| `/books?format=json` | `curl $B/books?format=json` | `500 INTERNAL_ERROR` (JSON) — ídem |
| `/books/9781000000032?format=json` | `curl ...` | `500 INTERNAL_ERROR` (JSON) — ídem |
| `/cloud-concepts` | `curl $B/cloud-concepts` | `500 INTERNAL_ERROR` (XML) — ídem |
| `/books-with-images?format=json` | `curl ...` | `500 INTERNAL_ERROR` (JSON) — ídem |
| `/books?format=csv` | `curl $B/books?format=csv` | `400 INVALID_FORMAT` (XML) |
| `POST /soap` texto plano | `curl -X POST $B/soap -H "Content-Type: text/plain" -d x` | `415`, SOAP Fault válido |
| `/wsdl/library-classifier.wsdl` | `curl $B/wsdl/...` | `200` |

Servidor detenido después de la validación (`Stop-Process`), confirmado
sin respuesta posterior.

**Nunca se afirma PASS para el camino feliz de datos reales** (`/books`,
`/books/<isbn>`, `/cloud-concepts`, `/books-with-images` devolviendo datos
verdaderos) porque esa prueba requiere PostgreSQL y no se pudo ejecutar.

## I. Evidencias recomendadas

1. Terminal mostrando `python app.py` arrancando sin errores.
2. `GET /health` en XML (navegador o `curl`).
3. `GET /health?format=json`.
4. `GET /books` en XML — **con PostgreSQL real corriendo**, no aquí.
5. `GET /books?format=json` — ídem.
6. `GET /books/<isbn>` en XML, con un ISBN real de tu base (por ejemplo
   `9781000000000`, del script `db/02_seed_30_per_table.sql`, **si**
   decides cargarlo — no confirmado contra tu base real).
7. `GET /books/<isbn>?format=json` — ídem.
8. `GET /cloud-concepts` en XML mostrando IaaS/PaaS/SaaS/FaaS reales.
9. `GET /cloud-concepts?format=json` — ídem.
10. `GET /books-with-images` en XML con al menos una imagen real.
11. `GET /books-with-images?format=json` — ídem.
12. `GET /books/ISBN-QUE-NO-EXISTE` → 404 XML.
13. `GET /books/ISBN-QUE-NO-EXISTE?format=json` → 404 JSON.
14. `GET /books?format=csv` → 400 (formato inválido).
15. Corrida de `python -m unittest tests.test_envelope tests.test_catalog_format tests.test_catalog_api -v` mostrando `OK`.
16. Consulta SQL directa (`psql`) mostrando filas reales en `conceptos`/`libro_concepto` (para complementar el punto 8).
17. Consulta SQL directa mostrando filas reales en `imagenes_libro` (para complementar el punto 10).
18. `POST /soap` con un request válido (o el cliente de escritorio) demostrando que SOAP sigue funcionando.

## J. Problemas encontrados

- **Discrepancia de ruta del profesor vs. estructura real:** la ruta
  conceptual `app/services/soap/app.py` mencionada en el enunciado no
  existe; el archivo real es `apps/library_soap_service/app.py`. Tal como
  pide el propio archivo de instrucciones, **no se reorganizó el
  repositorio** para imitar esa ruta.
- **Cambio de especificación a mitad de tarea:** este mismo archivo
  (`01_prompt_bilingue.md`) fue reemplazado por completo mientras ya se
  había construido una primera versión (microservicio separado,
  negociación por `Accept`). Se detuvo el trabajo, se confirmó contigo el
  cambio, se eliminó `apps/cloud_microservice/` y se reconstruyó todo
  según esta versión. Ver la nota al inicio de este reporte.
- **PostgreSQL no alcanzable en este entorno:** no hay servidor en
  `127.0.0.1:5433` (el valor configurado en `.env`) ni ningún otro
  PostgreSQL accesible aquí. Esto es una limitación del entorno de
  desarrollo usado para construir la tarea, no del código.

## K. Pendientes

Lo siguiente **no fue validado realmente** y debe confirmarse contra una
instancia PostgreSQL real con los datos del Ejercicio 02:

1. Que `GET /books` y `GET /books/<isbn>` devuelven filas reales de
   `libros`/`categorias`/`formatos` (la consulta fue verificada contra el
   esquema, no ejecutada contra datos).
2. Que `GET /cloud-concepts` efectivamente muestra IaaS/PaaS/SaaS/FaaS si
   esos conceptos existen en tu base — la consulta no filtra por nombre,
   pero no se ejecutó para confirmarlo.
3. Que `GET /books-with-images` devuelve imágenes reales de
   `imagenes_libro`, incluyendo el caso de un libro sin imágenes
   (`images: []`).
4. Que el usuario `library_soap_user` (o el que uses) realmente tiene
   `SELECT` sobre `formatos` e `imagenes_libro` — se documentó el GRANT
   sugerido en `sql/soap_module.sql`, pero no se aplicó ni se verificó
   contra una base real.
5. El cliente de escritorio SOAP (`desktop_client/`) no fue re-ejecutado;
   solo se confirmó que `POST /soap` sigue respondiendo y que las 3
   pruebas unitarias de `tests/test_envelope.py` siguen en PASS.
6. No existe repositorio git en este proyecto (`git status` devuelve "not
   a git repository"), así que no se pudo ejecutar `git diff` como pide la
   sección 24. En su lugar, la sección B de este reporte lista de forma
   exhaustiva y exacta los 3 archivos modificados, y ningún otro archivo
   fue tocado durante esta tarea (confirmado revisando cada llamada de
   escritura hecha en esta sesión).
7. Se confirma que no se agregó ningún `.env` real ni secreto: solo se
   creó/modificó código y documentación; `apps/library_soap_service/.env`
   ya existía de antes y no fue leído más allá de sus nombres de variable
   (su contenido con la contraseña real nunca se mostró ni se citó en este
   reporte).

------------------------------------------------------------
ADENDA — Filtro de conceptos Cloud Computing en /cloud-concepts
------------------------------------------------------------

Se pidió, como ajuste puntual, que `GET /cloud-concepts` devuelva
solamente conceptos de Cloud Computing (IaaS, PaaS, SaaS, FaaS, Bucket,
Public Cloud, Private Cloud, Hybrid Cloud, Multicloud, Serverless) y no
toda asociación `conceptos`/`libro_concepto` sin distinción de tema.

**Archivo modificado:** `catalog/repository.py::list_cloud_concepts()`.
Ningún otro endpoint, archivo SOAP, WSDL/XSD ni test preexistente fue
tocado.

**Cambio:** se agregó la constante `CLOUD_COMPUTING_CONCEPT_NAMES` (los 10
nombres exactos indicados) y se filtró la consulta con
`WHERE lower(c.nombre) = ANY(%s)`, usando esa lista como parámetro
(consulta parametrizada, sin concatenar strings). El esquema
(`conceptos(concepto_id, nombre)`) no tiene columna de categoría/tema, así
que no existe una forma puramente relacional de distinguir "es de Cloud
Computing"; filtrar por el conjunto real de nombres dado en la instrucción
fue la alternativa más directa sin alterar el esquema. Todo dato devuelto
(id, definición, isbn, título) sigue viniendo de la base, no se inventa
nada — solo el criterio de inclusión (qué nombres cuentan como "Cloud
Computing") es fijo en código.

**Archivos nuevos:** `tests/test_catalog_cloud_concepts.py` — valida (a)
que `CLOUD_COMPUTING_CONCEPT_NAMES` contiene exactamente los 10 nombres
pedidos (protege contra typos/omisiones) y (b) que `GET /cloud-concepts` y
`GET /cloud-concepts?format=json` siguen enrutando y fallan de forma
controlada (`500 INTERNAL_ERROR` bilingüe, sin traceback ni `psycopg2` en
el cuerpo) mientras PostgreSQL no esté disponible aquí.

**Pruebas ejecutadas realmente** (comando):

```
./.venv/Scripts/python.exe -m unittest tests.test_envelope tests.test_catalog_format tests.test_catalog_api tests.test_catalog_cloud_concepts -v
```

Resultado real: **19/19 PASS** (los 16 anteriores + 3 nuevos: allowlist
exacta, `/cloud-concepts` XML falla seguro, `/cloud-concepts?format=json`
falla seguro).

Adicionalmente, validación en vivo (`python app.py`, puerto 5179,
detenido al terminar):

| Prueba en vivo | Resultado real |
|---|---|
| `GET /cloud-concepts` | `500 INTERNAL_ERROR` (XML) — DB no alcanzable |
| `GET /cloud-concepts?format=json` | `500 INTERNAL_ERROR` (JSON) — ídem |
| `GET /cloud-concepts?format=csv` | `400 INVALID_FORMAT` (XML), sin tocar la base |
| `GET /health` | `200`, sin cambios |
| `GET /books` | `500 INTERNAL_ERROR`, sin cambios respecto al comportamiento previo |
| `POST /soap` (content-type inválido) | `415`, SOAP Fault válido, sin cambios |

**Pendiente (sin cambios respecto al reporte anterior):** no se pudo
confirmar contra datos reales que el filtro efectivamente deja pasar
IaaS/PaaS/SaaS/FaaS/Bucket/Public Cloud/Private Cloud/Hybrid
Cloud/Multicloud/Serverless y excluye el resto, ni que la ortografía usada
en `CLOUD_COMPUTING_CONCEPT_NAMES` coincide exactamente (mayusculas,
espacios) con `conceptos.nombre` en tu base — la comparación se hizo
insensible a mayúsculas para mitigar ese riesgo, pero no hay forma de
verificarlo sin una instancia PostgreSQL alcanzable. Recomendación: al
correr esto contra tu base real, ejecuta primero
`SELECT DISTINCT nombre FROM conceptos ORDER BY nombre;` y compara contra
`CLOUD_COMPUTING_CONCEPT_NAMES` en `catalog/repository.py` antes de dar
por bueno el resultado de `/cloud-concepts`.

Empieza inspeccionando el repositorio antes de modificar cualquier archivo.