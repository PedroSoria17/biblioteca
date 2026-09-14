PROMPT 05 — Cierre de gaps funcionales y calidad del seed — Ejercicio 02

Contexto

El Ejercicio 02 ya fue probado realmente contra PostgreSQL usando una base temporal library_db_test.

Hasta este punto se confirmó en runtime:

db/01_schema.sql ejecuta correctamente.

db/02_seed_30_per_table.sql ejecuta correctamente.

db/06_views.sql ejecuta correctamente.

db/04_stored_procedures.sql ejecuta correctamente.

db/05_triggers.sql ejecuta correctamente.

Las views pueden consultarse.

Las functions/procedures principales pueden invocarse.

El trigger de libros.fecha_actualizacion funciona.

library_user puede trabajar con mínimo privilegio.

La aplicación Node.js conectada a library_db_test funciona.

CRUD de libros, autores, géneros, conceptos y catálogos funciona.

Gestión de imágenes funciona.

Búsqueda, detalle y autenticación funcionan.

La arquitectura debe continuar siendo:

Browser
  ↓
Node.js + Express + EJS
  ↓
pg
  ↓
Functions / Procedures / Views
  ↓
PostgreSQL

No introduzcas REST, GraphQL, SOAP, microservicios, ORM ni frontend SPA.

1. Objetivo de esta ronda

Corrige únicamente estos tres gaps conocidos:

Portadas sintéticas sin relación con el libro en el seed.

Transferencia de administrador insegura, que puede dejar cero administradores si el usuario destino no existe o está inactivo.

Archivos físicos huérfanos al eliminar un libro, porque las filas de imagenes_libro se eliminan por ON DELETE CASCADE, pero los archivos no se eliminan del filesystem.

Mantén el diff pequeño.

No reescribas módulos que ya funcionan.

2. Archivos que debes revisar primero

Lee:

CLAUDE.md

03-prompt-base-datos-ejercicio02.md

04-prompt-auditoria-bd-ejercicio02.md

docs/REQUIREMENTS.md

docs/ENGINEERING_DECISIONS.md

docs/REQUIREMENTS_COMPLIANCE.md

Después inspecciona obligatoriamente:

db/01_schema.sql
db/02_seed_30_per_table.sql
db/04_stored_procedures.sql
db/05_triggers.sql
db/06_views.sql

y:

apps/web-monolito01/backend-node/src/modules/libros/libro.controller.js
apps/web-monolito01/backend-node/src/modules/libros/libro.model.js
apps/web-monolito01/backend-node/src/modules/libros/asociaciones.model.js
apps/web-monolito01/backend-node/src/modules/usuarios/usuario.model.js
apps/web-monolito01/backend-node/src/modules/usuarios/usuario.controller.js

Busca también todas las vistas EJS donde se rendericen imágenes de libros.

No asumas nombres de funciones o rutas: verifica el código real.

3. Regla de seguridad

NO ejecutes cambios contra:

library_db

La base real no debe tocarse.

Tampoco ejecutes automáticamente cambios destructivos sobre library_db_test.

Esta ronda debe modificar código/scripts y hacer pruebas estáticas.

Si tienes acceso a PostgreSQL temporal y puedes probar sin riesgo, puedes hacerlo únicamente contra una base temporal claramente identificada, pero no es obligatorio.

No:

DROP DATABASE library_db;

TRUNCATE sobre library_db;

modificar credenciales reales;

publicar contraseñas;

cambiar .env;

tocar deployment/reverse proxy;

trabajar en Exercise 03 o services/.

4. GAP 1 — Portadas sintéticas incorrectas

Problema observado

El seed ya usa URLs únicas, pero algunos registros de imagenes_libro todavía apuntan a imágenes reales existentes de pruebas anteriores.

Como esos archivos pertenecen visualmente a otros libros, la interfaz puede mostrar:

Título sintético A
+
portada real de otro libro B

Esto es funcionalmente válido pero visualmente incorrecto y no es adecuado para la evidencia final.

Objetivo

Ningún libro sintético del seed debe mostrar una portada real perteneciente a otro libro.

5. Solución esperada para las portadas

Inspecciona primero cómo las EJS muestran las imágenes.

Implementa una solución segura y simple basada en estas reglas:

A. Seed

db/02_seed_30_per_table.sql NO debe reutilizar imágenes reales cargadas manualmente durante pruebas.

Todos los registros sintéticos de imagenes_libro deben utilizar:

URLs únicas;

nombres seguros;

sin compartir ruta física entre filas;

sin apuntar a portadas reales de otros libros.

Puedes usar nombres sintéticos del estilo:

/uploads/libros/seed-cover-001.jpg
/uploads/libros/seed-cover-002.jpg
...

Los archivos pueden no existir físicamente siempre que la interfaz tenga fallback visual correcto.

Mantén:

imagenes_libro >= 30

y máximo una portada por libro.

B. Placeholder visual

Agrega un único asset estático neutral para cuando una portada no exista.

Preferencia:

src/public/images/book-placeholder.svg

Puede ser un SVG simple y limpio, por ejemplo:

icono/forma de libro;

texto Book Cover;

sin nombres de libros específicos.

Esto es un asset interno de UI, NO un archivo subido por el usuario, por lo que no modifica las reglas MIME de uploads.

C. Fallback en vistas

Todas las vistas EJS que presenten una portada proveniente de la base deben manejar el error de carga y reemplazarla por el placeholder.

No debe producir loops de onerror.

Revisa:

catálogo;

detalle;

formulario/edición;

gestión de imágenes;

cualquier otra vista que renderice imagen.url.

D. Compatibilidad futura con /library

Evita, si es posible, introducir una dependencia innecesaria que haga imposible servir el placeholder posteriormente bajo el prefijo /library.

No implementes todavía reverse proxy, pero mantén la solución razonablemente portable.

6. GAP 2 — Transferencia segura de Administrador

Problema confirmado

Actualmente sp_usuario_transferir_administracion(usuario_id) puede:

quitar privilegios al Administrador actual;

intentar promover el usuario destino;

si ese usuario no existe, afectar 0 filas;

terminar con cero administradores.

También debe evitarse transferir la administración a un usuario inactivo.

Objetivo

La transferencia debe mantener la regla:

exactamente un Administrador después de una transferencia exitosa

y una transferencia inválida no debe modificar el estado actual.

7. Comportamiento requerido de sp_usuario_transferir_administracion

Antes de degradar al Administrador actual, valida el destino.

Debe comprobar:

usuario_id destino existe.

destino está activo.

destino no representa una operación inválida.

existe un estado coherente para realizar la transferencia.

Usa PostgreSQL de forma atómica.

Una estrategia válida es:

buscar/bloquear el usuario destino;

si no existe → RAISE EXCEPTION;

si está inactivo → RAISE EXCEPTION;

sólo entonces realizar los UPDATE.

No confíes únicamente en rowCount de Node después de haber degradado al administrador.

No elimines el índice único parcial que impide dos Administradores.

No uses SECURITY DEFINER salvo justificación imprescindible.

8. Casos esperados de transferencia

Diseña el SP para que estos casos puedan probarse:

Caso A — destino válido y activo

1 admin antes
→ transferencia
→ 1 admin después
→ nuevo admin = destino

Caso B — usuario inexistente

1 admin antes
→ intento
→ ERROR controlado
→ 1 admin después
→ admin original permanece

Caso C — usuario inactivo

1 admin antes
→ intento
→ ERROR controlado
→ 1 admin después
→ admin original permanece

Caso D — destino ya es el administrador actual

Decide explícitamente un comportamiento seguro:

no-op controlado;

o excepción clara.

Documenta la decisión.

No permitas que termine con 0 o 2 administradores.

9. GAP 3 — Archivos físicos huérfanos al eliminar libro

Problema confirmado

Actualmente:

DELETE libro
  ↓
ON DELETE CASCADE
  ↓
se eliminan filas de imagenes_libro

pero los archivos físicos permanecen en:

src/public/uploads/libros/

La eliminación individual de imágenes ya usa fs.unlink, pero la eliminación del libro completo no.

Objetivo

Cuando un Administrador elimina un libro:

obtener previamente las imágenes asociadas;

eliminar el libro de PostgreSQL;

después de confirmar la eliminación BD, intentar eliminar los archivos físicos asociados;

archivos inexistentes no deben hacer fallar la operación;

nunca debe eliminarse un archivo fuera del directorio permitido.

10. Seguridad al borrar archivos

No uses directamente una ruta arbitraria almacenada en BD sin normalización.

Para cada URL/nombre almacenado:

extrae únicamente el nombre de archivo esperado;

usa path.basename(...) o mecanismo equivalente;

construye la ruta desde el directorio fijo de uploads;

evita path traversal;

no permitas borrar:

archivos de código;

placeholder;

archivos fuera de src/public/uploads/libros/.

El asset:

src/public/images/book-placeholder.svg

nunca debe entrar al flujo de eliminación de uploads.

11. Semántica de eliminación

La prioridad es:

Base de datos primero
Filesystem después

Razón:

si PostgreSQL rechaza el DELETE por integridad, no debemos haber borrado los archivos;

si PostgreSQL elimina correctamente pero un archivo físico ya no existe, el libro debe seguir considerándose eliminado.

Usa manejo tolerante como Promise.allSettled, catch, o mecanismo equivalente.

No ocultes errores graves de programación, pero un ENOENT de un archivo ya inexistente no debe tumbar la operación.

12. No modifiques innecesariamente las routines de imágenes

La corrección de archivos huérfanos puede vivir en el controlador Node si esa es la opción más natural.

No conviertas todo en una nueva function/procedure únicamente por estilo.

Preserva las interfaces actuales de:

libro.model.js;

asociaciones.model.js;

controladores;

rutas.

13. Revisar eliminación individual

Mientras trabajas en filesystem, revisa también que la eliminación individual existente:

eliminarImagen

construya una ruta segura.

Si actualmente concatena una URL arbitraria de BD de manera insegura, corrígelo utilizando la misma función/utilidad segura usada para eliminar imágenes al borrar un libro.

Evita duplicar lógica.

Si tiene sentido, crea una pequeña utilidad interna reutilizable para resolver/eliminar archivos de uploads.

No crees una arquitectura nueva.

14. db/02_seed_30_per_table.sql

Después de corregir el seed:

verifica estáticamente:

usuarios >= 30;

formatos >= 30;

categorias >= 30;

generos >= 30;

autores >= 30;

conceptos >= 30;

libros >= 30;

libro_autor >= 30;

libro_genero >= 30;

imagenes_libro >= 30;

libro_concepto >= 30.

Además:

exactamente 1 admin;

10 conceptos Cloud Computing;

0 URLs duplicadas en imagenes_libro;

0 referencias intencionales a archivos reales subidos manualmente;

máximo 1 portada por ISBN.

No cambies el resto del dataset si no es necesario.

15. Pruebas estáticas

Ejecuta después de los cambios:

node --check

sobre todos los JS modificados.

Además busca:

fs.unlink;

fs.rm;

construcción de rutas;

referencias al placeholder;

llamadas a sp_usuario_transferir_administracion;

URLs duplicadas del seed;

rutas reales antiguas reutilizadas por el seed.

Verifica que no hayas introducido:

SQL directo nuevamente en los modelos migrados;

nuevas credenciales;

dependencias innecesarias.

16. Pruebas SQL si PostgreSQL no está disponible

Si no puedes ejecutar PostgreSQL:

NO afirmes que el SP está validado en runtime.

Entrega exactamente los comandos que el desarrollador deberá ejecutar después contra library_db_test.

Como mínimo prepara:

Contar administradores

SELECT usuario_id, email, activo, es_administrador
FROM usuarios
WHERE es_administrador = TRUE;

Usuario inexistente

Prepara un CALL con un ID claramente inexistente.

Usuario inactivo

Identifica del seed un usuario inactivo y prepara el CALL.

Usuario activo

Identifica del seed un usuario regular activo y prepara el CALL.

Para los casos que deben fallar, explica que se debe verificar que el Administrador original sigue siendo administrador.

17. Pruebas manuales que deberá repetir el desarrollador

Después de aplicar los cambios en library_db_test, deberá comprobar:

Portadas

catálogo no muestra portadas de libros ajenos;

URLs sintéticas faltantes muestran placeholder;

detalle muestra placeholder;

una imagen real subida posteriormente sigue apareciendo normalmente.

Eliminación de imagen

subir imagen real;

eliminarla;

fila desaparece;

archivo físico desaparece.

Eliminación de libro

crear libro de prueba;

subir una o más imágenes reales;

confirmar archivos en uploads;

eliminar libro;

confirmar:

libro eliminado;

filas imagenes_libro eliminadas;

archivos físicos eliminados.

Transferencia de Administrador

destino inexistente → falla sin cambiar admin;

destino inactivo → falla sin cambiar admin;

destino válido → transferencia exitosa y queda exactamente uno.

18. No tocar todavía

No hagas:

deployment;

Apache;

NGINX;

/library;

binding 127.0.0.1;

ubiquitous;

tar.gz final;

Exercise 03;

SOAP;

REST;

GraphQL;

microservicios;

services/.

19. Documentación

Actualiza únicamente docs/REQUIREMENTS_COMPLIANCE.md si existe un hallazgo previamente documentado que quede claramente resuelto por el código.

Pero:

diferencia entre implementado y validado runtime;

no marques una prueba como ejecutada si no la ejecutaste;

no modifiques el .xlsx en esta ronda.

20. Entrega final

Responde exactamente con:

1. Resumen

Qué gaps se corrigieron.

2. Portadas sintéticas

causa;

solución;

archivos modificados;

comportamiento del placeholder.

3. Transferencia de Administrador

problema anterior;

validaciones nuevas;

comportamiento para inexistente/inactivo/mismo usuario/válido;

atomicidad.

4. Eliminación física de imágenes

eliminación individual;

eliminación al borrar libro;

protección path traversal;

manejo de archivos inexistentes.

5. Seed

Incluye conteos y resultado de:

URLs únicas;

administrador único;

conceptos Cloud Computing;

portadas únicas.

6. Archivos creados

Lista exacta.

7. Archivos modificados

Lista exacta y motivo.

8. Pruebas ejecutadas

Sólo las realmente ejecutadas.

9. Pruebas runtime pendientes

Da comandos/recorrido exacto.

10. Riesgos restantes

Indica cualquier gap que permanezca.

11. Diff summary

creados;

modificados;

eliminados.

No elimines archivos sin autorización.

21. Criterio de cierre

Esta ronda queda lista para prueba runtime cuando:

Seed
  ├── no usa portadas reales ajenas
  └── mantiene URLs únicas

UI
  └── muestra placeholder neutral si falta archivo

Admin transfer
  ├── valida destino antes de modificar admin actual
  └── nunca deja 0 admins por destino inválido

Delete book
  ├── PostgreSQL elimina primero
  └── filesystem se limpia después de forma segura

No afirmes cierre runtime hasta que estas condiciones hayan sido probadas contra library_db_test.