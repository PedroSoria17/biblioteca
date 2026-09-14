PROMPT 03 — Base de Datos, Stored Procedures, Triggers y Views — Ejercicio 02

Contexto

Este repositorio corresponde actualmente al Ejercicio 02 de la materia Integración de Aplicaciones Computacionales.

La aplicación activa es la librería web monolítica desarrollada con:

Node.js

Express

EJS

PostgreSQL

pg

express-session

bcryptjs

multer

La aplicación ya fue corregida y validada funcionalmente en sus flujos principales contra la base de datos real.

La base real utilizada por el proyecto es:

Base de datos: library_db

Usuario de aplicación: library_user

Nunca escribas ni publiques la contraseña real.

La arquitectura debe continuar siendo un monolito server-side.
El uso de stored procedures, functions y views de PostgreSQL no cambia esta decisión arquitectónica porque la aplicación continúa accediendo directamente a PostgreSQL mediante pg.

1. Alcance de esta tarea

En esta ronda debes trabajar exclusivamente en la fase de base de datos del Ejercicio 02.

Debes crear y dejar coherentes los siguientes entregables:

db/
├── 00_create_database.sql
├── 01_schema.sql
├── 02_seed_30_per_table.sql
├── 03_all_quieries_before_stored_procedures.sql
├── 04_stored_procedures.sql
├── 05_triggers.sql
└── 06_views.sql

Mantén exactamente el nombre 03_all_quieries_before_stored_procedures.sql, aunque la palabra quieries contenga el error ortográfico del documento del ejercicio.

Además, cuando sea necesario para cumplir el ejercicio, actualiza el acceso a datos de la aplicación Node.js para utilizar los stored procedures/functions/views creados, conservando pg y la arquitectura monolítica.

2. Archivos que debes leer antes de modificar cualquier cosa

Revisa primero, en este orden:

CLAUDE.md

docs/REQUIREMENTS.md

docs/ENGINEERING_DECISIONS.md

docs/REQUIREMENTS_COMPLIANCE.md

docs/REQUIREMENTS_COMPLIANCE.xlsx

docs/NORMALIZATION_4FN.xlsx

docs/DB_DESIGN_ER_4FN.drawio

docs/ARCHITECTURE_MONOLITHIC.drawio

01-prompt-monolito.md

02-prompt-cumplimiento-ejercicio02.md

Después inspecciona:

sql/schema.sql

sql/data.sql

todos los archivos *.model.js del monolito;

src/config/db.js;

src/lib/catalogoFactory.js;

los controladores relacionados con operaciones de base de datos;

cualquier consulta SQL embebida actualmente en el código.

No asumas que la documentación coincide perfectamente con el código: verifica el estado real antes de modificarlo.

3. Regla de seguridad sobre la base real

La base library_db contiene datos que ya están siendo utilizados para probar la aplicación.

No debes:

ejecutar DROP DATABASE library_db;

ejecutar DROP ROLE library_user;

borrar la base actual;

recrear destructivamente la base real;

truncar todas las tablas de la base real;

ejecutar automáticamente scripts destructivos sobre la base real;

cambiar credenciales reales;

escribir contraseñas en scripts versionados.

Sí puedes:

inspeccionar el esquema actual;

generar los nuevos scripts;

ejecutar consultas SELECT de verificación;

realizar validaciones no destructivas;

proponer un procedimiento de prueba en una base temporal si se dispone de una.

Si necesitas probar un script que recrea el esquema desde cero, utiliza únicamente una base temporal explícitamente creada para pruebas.
Si no existe una base temporal disponible, deja el script preparado y explica cómo debe probarse manualmente.

4. Modelo de datos final

El modelo final debe continuar consistente con la documentación de 4FN.

Las tablas esperadas actualmente son:

usuarios

formatos

categorias

generos

autores

conceptos

libros

libro_autor

libro_genero

imagenes_libro

libro_concepto

No desnormalices el modelo.

Mantén las relaciones:

Libro N Autor mediante libro_autor.

Libro N Género mediante libro_genero.

Libro N Concepto mediante libro_concepto.

Libro 1 Imagen mediante imagenes_libro.

Formato 1 Libro.

Categoría 1 Libro.

La definición debe continuar perteneciendo a:

(ISBN, concepto_id) -> definicion

No la muevas a la tabla conceptos.

5. db/00_create_database.sql

Crea un script para preparar la base y el usuario de aplicación cuando se despliegue desde cero.

Debe considerar:

base: library_db;

usuario de aplicación: library_user;

principio de mínimo privilegio;

ninguna contraseña real dentro del archivo.

Requisitos

No uses postgres como usuario de la aplicación.

No escribas una contraseña real.

Si PostgreSQL/psql requiere proporcionar la contraseña al crear el rol, usa una variable/placeholder seguro y documentado.

Evita instrucciones destructivas como DROP DATABASE.

Documenta mediante comentarios qué partes requieren ejecutar con un usuario administrativo.

Otorga únicamente los privilegios que la aplicación necesita.

Considera privilegios sobre:

base;

schema;

tablas;

secuencias;

functions/procedures que correspondan.

El script debe ser comprensible y reproducible.

6. db/01_schema.sql

Parte del sql/schema.sql existente y crea la versión final del esquema.

Debe contener:

tablas;

tipos;

PK;

FK;

UNIQUE;

CHECK;

índices;

acciones ON UPDATE / ON DELETE justificadas;

reglas de integridad.

Debe conservar

Administrador único

La base debe impedir que existan dos usuarios con:

es_administrador = TRUE

Mantén o mejora la solución actual basada en PostgreSQL.

Portada única

Cada libro puede tener como máximo una imagen marcada como portada.

Mantén la protección a nivel de base de datos.

Precio y stock

La base debe rechazar:

precio negativo;

stock negativo.

ISBN

Debe mantenerse único como clave del libro.

Importante

Los triggers deben vivir principalmente en:

db/05_triggers.sql

Por tanto, si sql/schema.sql contiene actualmente funciones/triggers mezclados con las tablas, sepáralos de manera ordenada.

01_schema.sql debe dejar la estructura preparada para que 05_triggers.sql pueda ejecutarse después.

No dupliques la misma regla innecesariamente entre CHECK, UNIQUE y trigger.
Usa la herramienta declarativa más apropiada para cada regla.

7. db/02_seed_30_per_table.sql

Crea datos sintéticos suficientes para probar completamente la solución.

Objetivo

Genera 30 registros válidos por tabla o relación, siempre que sea técnicamente coherente con el modelo.

Como mínimo asegúrate de poder verificar aproximadamente:

usuarios          >= 30
formatos          >= 30
categorias        >= 30
generos           >= 30
autores           >= 30
conceptos         >= 30
libros            >= 30
libro_autor       >= 30
libro_genero      >= 30
imagenes_libro    >= 30
libro_concepto    >= 30

Si decides que alguna tabla debe tener exactamente 30 y otra más de 30 para satisfacer relaciones, documenta la razón mediante comentarios.

Usuarios

Debe existir:

exactamente un Administrador;

el resto usuarios regulares;

emails únicos;

hashes de contraseña válidos si los usuarios deben utilizarse para pruebas.

No escribas contraseñas reales.

Puedes utilizar una contraseña sintética común de laboratorio, claramente documentada como dato de prueba, únicamente si el hash se genera de forma válida y no corresponde a una credencial real.

Datos bibliográficos

Los datos deben ser sintéticos pero plausibles.

Evita:

ISBN duplicados;

nombres repetidos que violen UNIQUE;

FK inexistentes;

precios/stock inválidos;

dos portadas para un libro.

8. Libro obligatorio de Cloud Computing

El seed debe incluir al menos un libro claramente relacionado con Cloud Computing.

Ese libro debe relacionarse con los siguientes conceptos:

IaaS

PaaS

SaaS

FaaS

Bucket

Public Cloud

Private Cloud

Hybrid Cloud

Multicloud

Serverless

Cada concepto debe tener una definición específica dentro de la relación libro_concepto.

No guardes esas definiciones en conceptos.

Si el esquema permite capítulo o página y ya existe ese atributo, úsalo.
Si el esquema actual no tiene capítulo/página, no modifiques el modelo sólo para agregarlo, porque el ejercicio indica que puede incluirlo, no que sea obligatorio.

9. Imágenes en el seed

Ten cuidado con imagenes_libro.

Los metadatos insertados no deben provocar que la interfaz dependa obligatoriamente de archivos inexistentes.

Primero inspecciona cómo la vista actual maneja rutas de imágenes.

Luego elige la opción menos riesgosa:

reutilizar archivos de prueba ya incluidos en el proyecto;

utilizar una imagen placeholder existente;

o documentar claramente rutas sintéticas si la interfaz maneja correctamente archivos faltantes.

No agregues archivos binarios innecesarios.

Mantén máximo una portada por libro.

10. db/03_all_quieries_before_stored_procedures.sql

Este archivo debe preservar como evidencia las consultas SQL utilizadas por la aplicación antes de migrarlas a stored procedures/functions/views.

Debe hacerse a partir del código real

Busca las consultas actuales dentro de:

modelos;

catalogoFactory;

módulos de libros;

asociaciones;

usuarios;

autenticación cuando corresponda.

Organiza el archivo por módulo y operación.

Ejemplo de organización:

-- =========================================================
-- LIBROS
-- =========================================================

-- Q-LIB-01: Listar catálogo
...

-- Q-LIB-02: Buscar por ISBN/título
...

-- Q-LIB-03: Crear libro
...

Requisitos

conserva placeholders parametrizados $1, $2, etc. cuando corresponda;

identifica claramente:

SELECT;

INSERT;

UPDATE;

DELETE;

transacciones;

no incluyas contraseñas ni secretos;

no inventes consultas que la aplicación no utiliza sin marcar claramente que son adicionales.

Este archivo funciona como snapshot documental previo a stored procedures.

11. db/04_stored_procedures.sql

Diseña stored procedures/functions que encapsulen de forma razonable las operaciones de base de datos utilizadas por la aplicación.

Importante sobre PostgreSQL

Usa la herramienta correcta:

CREATE PROCEDURE cuando una operación no necesita retornar un conjunto de filas y el procedimiento sea apropiado.

CREATE FUNCTION ... RETURNS ... / RETURNS TABLE cuando la aplicación necesita obtener valores o conjuntos de resultados.

Aunque el archivo se llame stored_procedures.sql, puedes utilizar functions de PostgreSQL cuando técnicamente sean la mejor opción.
Documenta mediante comentarios la razón.

Deben cubrir de forma coherente

Al menos las operaciones principales de:

libros;

usuarios;

autores;

géneros;

formatos;

categorías;

conceptos;

libro_autor;

libro_genero;

libro_concepto;

imágenes.

No crees decenas de procedimientos duplicados sin necesidad.

Busca una organización mantenible.

Requisitos de seguridad

no construyas SQL dinámico a partir de entrada del usuario salvo que sea estrictamente necesario;

si se requiere SQL dinámico, usa quoting seguro;

respeta restricciones de PostgreSQL;

no eleves privilegios innecesariamente;

evita SECURITY DEFINER salvo que exista una justificación técnica clara.

12. Migración de la aplicación a stored procedures/functions

Después de crear 04_stored_procedures.sql, revisa los modelos de Node.js.

Cuando sea razonable y requerido para demostrar el ejercicio:

reemplaza operaciones SQL directas por llamadas a stored procedures/functions;

conserva pg;

conserva parámetros;

conserva interfaces de los modelos siempre que sea posible para no romper controladores;

evita modificar rutas/vistas si no es necesario.

Ejemplos válidos:

SELECT * FROM fn_listar_libros($1);

CALL sp_actualizar_stock($1, $2);

La aplicación sigue accediendo directamente a PostgreSQL con pg; por tanto, esto no introduce una API ni otra capa arquitectónica independiente.

Muy importante

No elimines 03_all_quieries_before_stored_procedures.sql; ese archivo debe conservar el SQL anterior como evidencia.

13. db/05_triggers.sql

Revisa primero los triggers existentes.

Crea únicamente triggers con una justificación real.

Como mínimo

Conserva la funcionalidad existente para actualizar automáticamente:

libros.fecha_actualizacion

cuando un libro cambia, si esa lógica ya existe.

No uses triggers para reemplazar reglas que funcionan mejor con:

PRIMARY KEY;

FOREIGN KEY;

UNIQUE;

CHECK;

índice único parcial.

Por ejemplo:

administrador único → preferentemente índice/restricción apropiada;

portada única → preferentemente índice único parcial si ya funciona correctamente;

precio negativo → CHECK;

stock negativo → CHECK.

Si agregas algún trigger adicional, debe responder a una necesidad real del dominio y debes justificarlo.

No agregues triggers artificiales únicamente para aumentar la cantidad.

14. db/06_views.sql

Crea vistas útiles para consulta y evidencia del ejercicio.

Revisa las consultas reales de la aplicación y diseña vistas que reduzcan joins repetitivos o expongan información segura.

Como mínimo evalúa crear vistas equivalentes a:

vw_catalogo_libros

Puede incluir:

ISBN;

título;

año;

precio;

stock;

formato;

categoría;

portada cuando corresponda.

vw_libro_conceptos

Puede incluir:

ISBN;

título;

concepto;

definición.

vw_libro_autores

Puede incluir:

ISBN;

título;

autor;

orden.

vw_libro_generos

Puede incluir:

ISBN;

título;

género.

vw_usuarios_resumen

Si se crea, no debe exponer password_hash.

No es obligatorio utilizar exactamente estos nombres si existe una mejor organización, pero las vistas deben tener utilidad real.

Cuando tenga sentido, actualiza consultas de lectura de Node.js para utilizar estas vistas sin romper la interfaz actual.

15. Integridad y reglas de negocio

Después de preparar los scripts, diseña las pruebas negativas necesarias para PostgreSQL.

Como mínimo deben verificarse posteriormente:

ISBN duplicado.

Stock negativo.

Precio inválido/negativo.

FK inexistente.

Eliminación que viole una relación protegida.

Creación de un segundo Administrador.

Segunda portada para el mismo libro.

Duplicación de una relación libro-autor.

Duplicación de una relación libro-género.

Duplicación de una relación libro-concepto cuando la PK lo impida.

Para cada prueba prepara:

sentencia;

precondición;

resultado esperado;

error de PostgreSQL esperado.

No inventes el error real observado si no ejecutaste la prueba.

16. Verificaciones de los scripts

Si tienes acceso a una base temporal segura, prueba en este orden:

00_create_database.sql   (sólo cuando aplique y nunca destruyendo library_db)
01_schema.sql
02_seed_30_per_table.sql
03_all_quieries_before_stored_procedures.sql
04_stored_procedures.sql
05_triggers.sql
06_views.sql

Nota sobre 03

Si 03_all_quieries_before_stored_procedures.sql es exclusivamente evidencia documental y contiene consultas con placeholders $1, $2, etc., no lo ejecutes como un script autónomo.
Aclara esta condición en el archivo y en el reporte.

Verifica después

conteo de tablas;

conteos por tabla;

PK/FK;

constraints;

índices;

stored procedures/functions;

triggers;

views;

usuario Administrador único;

libro de Cloud Computing;

sus 10 conceptos.

17. Consultas de verificación esperadas

Prepara o ejecuta consultas equivalentes a:

SELECT COUNT(*) FROM usuarios;
SELECT COUNT(*) FROM libros;
SELECT COUNT(*) FROM autores;
SELECT COUNT(*) FROM generos;
SELECT COUNT(*) FROM conceptos;
SELECT COUNT(*) FROM imagenes_libro;
SELECT COUNT(*) FROM libro_autor;
SELECT COUNT(*) FROM libro_genero;
SELECT COUNT(*) FROM libro_concepto;

Y:

SELECT email, es_administrador
FROM usuarios
WHERE es_administrador = TRUE;

Además verifica el libro de Cloud Computing y sus conceptos mediante una consulta con JOIN.

18. Compatibilidad con la aplicación

Después de cualquier cambio en los modelos Node.js:

ejecuta node --check sobre archivos modificados;

inicia la aplicación si el entorno está disponible;

comprueba que no se rompió:

login;

catálogo;

búsqueda;

detalle de libro;

CRUD de libro;

autores;

géneros;

conceptos;

imágenes.

No inventes resultados de pruebas que no hayas podido ejecutar.

19. No trabajar todavía en

No hagas en esta ronda:

Apache;

NGINX;

reverse proxy;

/library;

127.0.0.1:3000;

página de ubiquitous;

archivo .tar.gz;

SOAP;

REST;

GraphQL;

microservicios;

Ejercicio 03;

services/;

migración a TypeScript;

ORM;

React/Vue/Angular.

No modifiques despliegue todavía.

20. Archivos antiguos sql/

No elimines inmediatamente:

sql/schema.sql

sql/data.sql

Primero crea y valida la nueva carpeta db/.

Al finalizar:

indica si los archivos sql/ quedaron obsoletos;

recomienda si deben conservarse temporalmente como evidencia histórica o eliminarse posteriormente;

no los borres sin autorización explícita.

21. Documentación

No cambies el significado de:

docs/REQUIREMENTS.md

docs/ENGINEERING_DECISIONS.md

docs/NORMALIZATION_4FN.xlsx

Si detectas una contradicción real entre el modelo implementado y esos documentos:

detén ese cambio;

repórtalo;

explica cuál es la contradicción;

propón una solución.

Puedes proponer actualizaciones para docs/REQUIREMENTS_COMPLIANCE.md, pero no marques como validado algo que no se haya probado.

22. Entrega final esperada

Al terminar responde exactamente con esta estructura:

1. Resumen

Describe qué se realizó.

2. Archivos creados

Lista:

db/00_create_database.sql

db/01_schema.sql

db/02_seed_30_per_table.sql

db/03_all_quieries_before_stored_procedures.sql

db/04_stored_procedures.sql

db/05_triggers.sql

db/06_views.sql

y cualquier otro archivo realmente creado.

3. Archivos Node.js modificados

Para cada archivo:

ruta;

motivo;

stored procedure/function/view utilizada;

compatibilidad preservada.

4. Diseño de 00_create_database.sql

Explica:

usuario;

privilegios;

manejo de contraseña;

mínimo privilegio.

5. Diseño de 01_schema.sql

Resume:

tablas;

constraints;

índices;

administrador único;

portada única;

acciones referenciales.

6. Diseño de 02_seed_30_per_table.sql

Incluye:

conteo planeado por tabla;

Administrador único;

libro de Cloud Computing;

conceptos asociados.

7. Snapshot de consultas previas

Resume qué contiene 03_all_quieries_before_stored_procedures.sql.

8. Stored procedures/functions

Tabla con:

nombre;

tipo (PROCEDURE o FUNCTION);

propósito;

módulo que la utiliza.

9. Triggers

Tabla con:

nombre;

tabla;

evento;

propósito;

justificación.

10. Views

Tabla con:

nombre;

propósito;

si la aplicación la utiliza.

11. Pruebas ejecutadas

Sólo las pruebas realmente ejecutadas.

Para cada una:

comando;

resultado observado.

12. Pruebas pendientes

Explica qué debe ejecutar manualmente el desarrollador.

13. Riesgos o decisiones

Indica cualquier trade-off o limitación.

14. Estado de sql/schema.sql y sql/data.sql

Indica si siguen siendo necesarios.

15. Diff summary

Lista:

creados;

modificados;

eliminados.

No elimines archivos sin autorización.

23. Criterio final

El objetivo es transformar el trabajo actual de base de datos en una entrega reproducible y defendible del Ejercicio 02.

Debe ser posible explicar claramente:

Modelo 4FN
   ↓
Schema PostgreSQL
   ↓
Datos de prueba
   ↓
Consultas SQL originales
   ↓
Stored Procedures / Functions
   ↓
Triggers
   ↓
Views
   ↓
Aplicación Node.js mediante pg

sin cambiar la arquitectura monolítica ni romper la aplicación que ya funciona.