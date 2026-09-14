PROMPT 04 — Auditoría Técnica antes de Probar la Base de Datos — Ejercicio 02

Objetivo

Antes de ejecutar cualquier script nuevo sobre PostgreSQL, realiza una auditoría técnica del trabajo generado en el Prompt 03.

Esta ronda NO es para desplegar, NO es para ejecutar scripts destructivos y NO es para modificar la base real library_db.

El objetivo es revisar y corregir, únicamente si es necesario, cuatro riesgos concretos:

Dependencias entre Views y Functions/Procedures.

Compatibilidad del seed con una base limpia y con una base ya existente.

Riesgo de múltiples registros de imágenes apuntando al mismo archivo físico.

Compatibilidad real entre las firmas de Node.js y las funciones/procedures de PostgreSQL.

1. Lee primero estos archivos

Revisa antes de modificar cualquier cosa:

CLAUDE.md

docs/REQUIREMENTS.md

docs/ENGINEERING_DECISIONS.md

docs/REQUIREMENTS_COMPLIANCE.md

03-prompt-base-datos-ejercicio02.md

Después inspecciona obligatoriamente:

db/00_create_database.sql
db/01_schema.sql
db/02_seed_30_per_table.sql
db/03_all_quieries_before_stored_procedures.sql
db/04_stored_procedures.sql
db/05_triggers.sql
db/06_views.sql

y también:

apps/web-monolito01/backend-node/src/modules/libros/libro.model.js
apps/web-monolito01/backend-node/src/modules/libros/asociaciones.model.js
apps/web-monolito01/backend-node/src/modules/usuarios/usuario.model.js
apps/web-monolito01/backend-node/src/lib/catalogoFactory.js

Además revisa los controladores relacionados con imágenes para saber si al eliminar una imagen también se elimina el archivo físico del filesystem.

2. Regla principal

NO ejecutes:

DROP DATABASE library_db

DROP ROLE library_user

TRUNCATE

seeds sobre library_db

migraciones destructivas sobre library_db

No modifiques credenciales reales.

No trabajes todavía en:

Apache

NGINX

reverse proxy

/library

despliegue

SOAP

REST

GraphQL

microservicios

Exercise 03

services/

Esta auditoría es sólo de código y scripts.

3. Auditoría A — Dependencias Views ↔ Functions

En el Prompt 03 se reportó que algunas functions usan internamente views como:

vw_catalogo_libros

vw_libro_autores

vw_libro_generos

vw_libro_conceptos

vw_usuarios_resumen

Pero actualmente:

las functions/procedures viven en db/04_stored_procedures.sql;

las views viven en db/06_views.sql.

Debes revisar

Qué functions de 04_stored_procedures.sql dependen de views.

Si esas functions pueden crearse antes de que existan las views.

Si el orden actual de ejecución:

01 schema

02 seed

04 routines

05 triggers

06 views

es realmente válido.

Si detectas una dependencia inválida

Corrige el diseño de la manera más mantenible.

Preferencias:

Opción recomendada A

Si las views son dependencias reales de las functions, mueve la creación de esas views antes de las functions, pero mantén el archivo requerido 06_views.sql como entregable.

Una solución válida puede ser:

eliminar la dependencia de las functions respecto a las views y usar SQL directo dentro de la function;

o cambiar el orden de ejecución documentado si PostgreSQL realmente lo permite y queda reproducible;

o separar conceptualmente la dependencia sin duplicar objetos.

No dupliques la misma view en dos archivos.

Resultado esperado

Debe existir un orden de instalación inequívoco y ejecutable desde cero.

Documenta el orden final.

4. Auditoría B — Seed y base existente

El seed debe estar pensado principalmente para una base limpia de laboratorio.

Actualmente el proyecto ya tiene una base real library_db con:

usuarios existentes;

exactamente un Administrador real de prueba;

libros y catálogos creados durante pruebas funcionales.

Debes comprobar

Si 02_seed_30_per_table.sql asume una base vacía.

Si podría fallar al ejecutarse sobre una base con datos existentes.

Si intenta crear un Administrador adicional.

Si depende de IDs SERIAL específicos.

Si usa IDs hardcodeados que podrían ser diferentes en una base existente.

Si los inserts son reproducibles en una base limpia.

Si debe ser idempotente o si basta con documentar que sólo debe ejecutarse sobre una base limpia.

Regla

NO conviertas el seed en una migración para library_db.

Lo preferido es dejar claro en la cabecera del archivo:

Este seed está diseñado para una base limpia de laboratorio y no debe ejecutarse sobre una base existente con datos de producción/prueba.

Si el script necesita correcciones para funcionar correctamente sobre una base limpia, hazlas.

No cambies el objetivo de tener al menos 30 registros por tabla/relación.

5. Auditoría C — Imágenes físicas compartidas

En el Prompt 03 se reportó que múltiples filas de imagenes_libro reutilizan archivos JPG reales existentes en:

src/public/uploads/libros/

Esto puede ser peligroso si al eliminar una imagen el sistema también elimina físicamente el archivo.

Debes inspeccionar

controlador de imágenes;

modelo de asociaciones;

utilidades filesystem;

cualquier fs.unlink, unlinkSync, rm, rmSync o equivalente;

flujo de eliminación de libros;

flujo de eliminación de imágenes.

Determina

Caso 1

Si eliminar una fila también elimina el archivo físico:

Entonces NO permitas que múltiples filas del seed compartan el mismo nombre_archivo/ruta física.

Corrige el seed de alguna de estas formas:

usa archivos únicos existentes, si hay suficientes;

o evita poblar metadatos que apunten a archivos compartidos;

o crea datos de imagen seguros que no causen referencias compartidas destructivas.

No agregues binarios innecesarios.

Caso 2

Si eliminar una fila NO elimina el archivo físico:

Puedes mantener reutilización sólo si no rompe la interfaz y queda claramente documentado.

Resultado esperado

El seed nunca debe crear una situación donde eliminar una imagen pueda romper visualmente imágenes de otros libros.

6. Auditoría D — Firmas Node.js ↔ PostgreSQL

Esta es la revisión más importante.

Para cada llamada desde:

libro.model.js

asociaciones.model.js

usuario.model.js

catalogoFactory.js

compara exactamente con la rutina correspondiente de:

db/04_stored_procedures.sql

Revisa para cada llamada

Nombre exacto.

Número de parámetros.

Orden de parámetros.

Tipos PostgreSQL esperados.

Uso correcto de:

SELECT * FROM fn_xxx(...)

SELECT fn_xxx(...)

CALL sp_xxx(...)

Nombre de columnas retornadas.

Forma del resultado usado por Node:

rows

rows[0]

rowCount

Valores booleanos.

NULL.

IDs SERIAL/BIGSERIAL/INTEGER.

ISBN como texto.

Precio/numeric.

fechas/timestamps.

transacciones encapsuladas.

comportamiento de errores.

Atención especial

Revisa que funciones como:

fn_libro_crear

fn_libro_actualizar

fn_libro_imagen_agregar

fn_libro_imagen_actualizar

fn_usuario_crear

fn_usuario_actualizar_perfil

fn_catalogo_crear

fn_catalogo_actualizar

fn_autor_crear

fn_autor_actualizar

retornen exactamente lo que el código Node espera.

También verifica que los procedures que no retornan filas no sean tratados como si devolvieran registros.

7. Catálogos polimórficos

Revisa especialmente:

fn_catalogo_listar
fn_catalogo_obtener
fn_catalogo_crear
fn_catalogo_actualizar
sp_catalogo_eliminar

Comprueba:

valores permitidos para el parámetro que identifica el catálogo;

que el valor nunca venga directamente sin validar desde input del usuario;

que no exista SQL dinámico inseguro;

que formatos, categorias, generos y conceptos estén cubiertos;

que el adaptador de catalogoFactory.js reconstruya correctamente nombres como:

formato_id

categoria_id

genero_id

concepto_id

No rompas las vistas EJS existentes.

8. Transacciones movidas a PostgreSQL

Revisa cuidadosamente:

agregar imagen;

marcar portada;

transferir administración.

Comprueba que las routines mantengan atomicidad.

En particular:

Marcar portada

Debe evitar estados intermedios inválidos con dos portadas.

Transferir administración

Debe mantener exactamente un Administrador.

Además revisa si existe actualmente una validación del usuario destino.

Si el destino no existe o está inactivo y eso representa un riesgo claro, repórtalo antes de cambiar comportamiento funcional.

No amplíes el alcance silenciosamente.

9. Stored procedures/functions y privilegios

Revisa 00_create_database.sql y 04_stored_procedures.sql.

Comprueba:

que library_user pueda ejecutar las rutinas necesarias;

que no tenga privilegios DDL;

que las rutinas no requieran privilegios que el usuario no posea;

que no se use SECURITY DEFINER innecesariamente;

compatibilidad razonable con PostgreSQL moderno.

Si el script depende de una versión específica, documenta la dependencia.

10. fecha_actualizacion

Comprueba que:

db/01_schema.sql
db/05_triggers.sql

sean coherentes.

El schema debe declarar la columna.

El trigger debe:

existir una sola vez;

actualizarla en BEFORE UPDATE;

no entrar en recursión;

no requerir que Node la envíe manualmente.

11. Pruebas estáticas obligatorias

Después de cualquier corrección:

ejecuta node --check sobre todos los JS modificados;

busca referencias a functions/procedures inexistentes;

busca routines declaradas pero nunca utilizadas;

busca duplicados de nombres;

busca parámetros inconsistentes;

busca SQL directo que haya quedado accidentalmente en los cuatro modelos migrados;

revisa que 03_all_quieries_before_stored_procedures.sql permanezca como evidencia histórica y no haya sido eliminado.

Si no tienes PostgreSQL disponible, dilo claramente.

No inventes validación runtime.

12. No cambies por estilo

No reescribas código que ya es correcto sólo por preferencia personal.

Sólo corrige:

errores reales;

dependencias inválidas;

incompatibilidades;

riesgos concretos;

inconsistencias con el Prompt 03.

Mantén el diff pequeño.

13. Entrega final

Responde exactamente con:

1. Resultado general

Indica si encontraste problemas reales o si el diseño era válido.

2. Dependencias Views ↔ Functions

Explica:

qué encontraste;

si había un problema;

qué corregiste;

orden final de ejecución.

3. Seed

Explica:

si es sólo para base limpia;

si depende de IDs;

comportamiento con base existente;

cualquier corrección.

4. Imágenes

Explica:

si el filesystem elimina archivos;

si había riesgo por rutas compartidas;

corrección aplicada.

5. Compatibilidad Node ↔ PostgreSQL

Incluye una tabla:

Archivo Node

Rutina

Parámetros compatibles

Retorno compatible

Estado

No omitas ninguna rutina llamada por los cuatro archivos migrados.

6. Catálogos polimórficos

Explica cómo se validan y si el adaptador conserva las interfaces.

7. Transacciones

Resume:

imágenes;

portada;

transferencia de admin.

8. Privilegios

Explica si library_user podrá ejecutar todo lo necesario.

9. Archivos modificados

Lista cada archivo y el cambio exacto.

10. Pruebas ejecutadas

Sólo pruebas realmente ejecutadas.

11. Riesgos restantes

No ocultes incertidumbres.

12. Recomendación para siguiente paso

Indica si el proyecto está listo para crear una base temporal library_db_test y ejecutar los scripts uno por uno.

14. Criterio de aprobación

Considera esta auditoría aprobada sólo si puedes afirmar, con base en revisión real de código, que:

Node.js
  ↓
Firmas compatibles
  ↓
Functions / Procedures
  ↓
Views / Tables
  ↓
Constraints / Triggers

tiene coherencia estática completa y que el seed es seguro para ejecutarse en una base temporal limpia.

No afirmes que PostgreSQL funciona en runtime si no pudiste ejecutarlo.