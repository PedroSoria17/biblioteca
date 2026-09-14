# ENGINEERING_DECISIONS.md

## Aplicación Web Monolítica para Gestión de una Librería

**Asignatura:** Integración de Aplicaciones Computacionales  
**Arquitectura:** Monolítica server-side  
**Tecnologías principales:** Node.js, Express, EJS y PostgreSQL  
**Propósito:** Registrar y justificar decisiones técnicas relevantes del ejercicio.

---

# 1. Objetivo del registro de decisiones

Este documento conserva las principales decisiones de ingeniería tomadas durante el diseño e implementación de la aplicación web de gestión de una librería.

Cada decisión se documenta mediante el siguiente esquema:

**Necesidad o problema → alternativas consideradas → decisión tomada → justificación técnica → beneficios → riesgos o limitaciones → condición futura de cambio → evidencia de validación**

El objetivo no es únicamente registrar qué tecnología se utilizó, sino explicar por qué fue elegida, qué consecuencias tiene y cómo se verificará que la decisión continúa siendo adecuada.

---

# 2. Resumen de decisiones

| ID | Decisión | Estado |
|---|---|---|
| ADR-01 | Utilizar una arquitectura monolítica | Aceptada |
| ADR-02 | Acceso directo a PostgreSQL mediante `pg` | Aceptada |
| ADR-03 | Renderizado server-side mediante EJS | Aceptada |
| ADR-04 | Organizar el monolito con separación modular de responsabilidades | Aceptada |
| ADR-05 | Utilizar PostgreSQL como fuente principal de persistencia relacional | Aceptada |
| ADR-06 | Almacenar imágenes en filesystem y metadatos en PostgreSQL | Aceptada |
| ADR-07 | Utilizar autenticación basada en sesión y hash de contraseñas | Aceptada |
| ADR-08 | Mantener secretos y configuración mediante variables de entorno | Aceptada |
| ADR-09 | Publicar la aplicación mediante reverse proxy Apache/NGINX | Planeada para despliegue |

---

# ADR-01. Arquitectura monolítica

## Necesidad o problema

La aplicación debe permitir autenticación, consulta de catálogo, operaciones CRUD, administración de relaciones entre libros y catálogos, manejo de imágenes y acceso a PostgreSQL dentro de una solución que pueda desarrollarse, probarse y desplegarse de forma sencilla para un ejercicio académico.

## Alternativas consideradas

1. **Arquitectura monolítica server-side.**
2. Aplicación frontend y backend desacoplados mediante API REST.
3. Arquitectura basada en microservicios.

## Decisión tomada

Se utilizará una **arquitectura monolítica server-side con Node.js y Express**, donde presentación, lógica de aplicación, middleware y acceso a datos forman parte de una sola unidad desplegable.

## Justificación técnica

El alcance del sistema es suficientemente acotado para mantenerse dentro de una sola aplicación. El monolito reduce la cantidad de componentes que deben desplegarse, configurarse y monitorearse, evita la complejidad de comunicación distribuida y facilita la depuración del flujo completo.

Además, el ejercicio establece explícitamente que no se desarrollarán APIs REST, GraphQL, SOAP ni microservicios.

## Beneficios

- Un único proceso de aplicación.
- Despliegue más sencillo.
- Menor complejidad operativa.
- Depuración más directa.
- Menor cantidad de configuraciones de red.
- Consistencia sencilla entre lógica de negocio y acceso a datos.
- Adecuado para el tamaño actual del sistema y del equipo.

## Riesgos o limitaciones

- Todos los módulos comparten la misma unidad de despliegue.
- Un cambio pequeño puede requerir volver a desplegar toda la aplicación.
- El escalamiento independiente de módulos no es posible.
- A medida que crezca el sistema puede aumentar el acoplamiento.
- Una falla grave en el proceso puede afectar todas las funcionalidades.

## Condición futura que podría justificar un cambio

Podría reconsiderarse esta decisión si el sistema creciera en volumen, número de usuarios, equipos de desarrollo o dominios de negocio, y existiera una necesidad real de desplegar, escalar o evolucionar componentes de manera independiente.

## Evidencia de validación

- Diagrama `docs/ARCHITECTURE_MONOLITHIC.png`.
- Estructura modular del proyecto Node.js.
- Prueba de ejecución de todas las funcionalidades dentro de un único proceso.
- Despliegue final del monolito detrás de Apache o NGINX.

---

# ADR-02. Acceso directo a PostgreSQL mediante `pg`

## Necesidad o problema

La aplicación necesita leer y modificar información relacional relacionada con usuarios, libros, autores, géneros, formatos, categorías, conceptos, imágenes y tablas puente.

## Alternativas consideradas

1. Acceso directo a PostgreSQL mediante el controlador `pg`.
2. Uso de un ORM como Sequelize o TypeORM.
3. Acceso a datos mediante una API independiente.
4. Uso de procedimientos externos o una capa de microservicios.

## Decisión tomada

La aplicación accederá directamente a PostgreSQL utilizando el paquete **`pg`** y consultas SQL parametrizadas.

## Justificación técnica

El acceso mediante `pg` permite controlar directamente las consultas SQL, comprender claramente las operaciones realizadas sobre el modelo relacional y mantener visible la relación entre la aplicación y el esquema normalizado.

Para este ejercicio resulta especialmente apropiado porque permite demostrar de forma directa el uso de PK, FK, restricciones, vistas, triggers, stored procedures y reglas de integridad implementadas en PostgreSQL.

## Beneficios

- Control explícito del SQL ejecutado.
- Menor abstracción entre aplicación y base de datos.
- Facilidad para demostrar consultas parametrizadas.
- Aprovechamiento directo de restricciones de PostgreSQL.
- Dependencias adicionales mínimas.
- Facilita relacionar código, pruebas y evidencias SQL.

## Riesgos o limitaciones

- Mayor cantidad de SQL escrito manualmente.
- El desarrollador debe administrar correctamente errores y transacciones.
- Consultas repetidas pueden generar duplicación si no se organiza adecuadamente el acceso a datos.
- Mayor dependencia directa del modelo PostgreSQL.

## Condición futura que podría justificar un cambio

Podría evaluarse un ORM o una capa de persistencia diferente si el proyecto creciera considerablemente, existieran múltiples motores de base de datos o fuera necesario reducir código repetitivo mediante abstracciones bien justificadas.

## Evidencia de validación

- Configuración centralizada de conexión a PostgreSQL.
- Uso de placeholders como `$1`, `$2`, etc.
- Pruebas con entradas que contengan caracteres especiales.
- Revisión de código para verificar que no se concatena directamente entrada del usuario en consultas SQL.
- Evidencias de operaciones CRUD ejecutadas correctamente.

---

# ADR-03. Renderizado server-side mediante EJS

## Necesidad o problema

La aplicación necesita generar páginas para login, registro, catálogo, detalle de libro y operaciones administrativas sin introducir una arquitectura frontend independiente.

## Alternativas consideradas

1. Renderizado server-side mediante EJS.
2. SPA con React, Angular o Vue.
3. Frontend independiente consumiendo una API REST.
4. Generación manual de HTML sin motor de plantillas.

## Decisión tomada

Las vistas se generarán en el servidor mediante **EJS**, y los formularios HTML enviarán sus datos directamente a la aplicación monolítica.

## Justificación técnica

EJS permite integrar las vistas directamente con Express, generar HTML dinámico y mantener un flujo tradicional de solicitud-respuesta.

Este enfoque evita introducir una API adicional y es consistente con la arquitectura monolítica solicitada. También reduce la cantidad de código JavaScript necesario en el cliente para realizar las operaciones principales.

## Beneficios

- Integración sencilla con Express.
- Flujo HTTP fácil de comprender.
- Menor complejidad frontend.
- No requiere API REST.
- El servidor controla autenticación, autorización y renderizado.
- Adecuado para formularios y operaciones CRUD tradicionales.

## Riesgos o limitaciones

- Mayor dependencia del servidor para actualizar vistas.
- Menor interactividad que una SPA en escenarios complejos.
- Las vistas pueden volverse difíciles de mantener si se introduce lógica de negocio en EJS.
- Cada navegación principal puede requerir una nueva solicitud HTTP.

## Condición futura que podría justificar un cambio

Podría evaluarse un frontend desacoplado si la aplicación requiriera alta interactividad en cliente, consumo por múltiples tipos de clientes o una API compartida por aplicaciones web y móviles.

## Evidencia de validación

- Archivos `.ejs` utilizados para renderizar páginas.
- Formularios HTML enviando solicitudes al monolito.
- Pruebas de navegación y operaciones CRUD.
- Ausencia de una API REST como mecanismo principal de comunicación frontend-backend.

---

# ADR-04. Separación modular dentro del monolito

## Necesidad o problema

Una aplicación monolítica puede convertirse rápidamente en un archivo central difícil de mantener si toda la lógica se concentra en `app.js`, en las rutas o en las vistas.

## Alternativas consideradas

1. Concentrar rutas, consultas y lógica en pocos archivos.
2. Separar responsabilidades mediante una organización tipo MVC o server-side equivalente.
3. Dividir el sistema en servicios independientes.

## Decisión tomada

El monolito se organizará en módulos con responsabilidades diferenciadas para configuración, rutas, controladores o lógica de aplicación, middleware, acceso a datos, vistas y recursos estáticos.

## Justificación técnica

La separación interna permite conservar las ventajas operativas del monolito sin renunciar a mantenibilidad y claridad. Modularizar no convierte la solución en microservicios, ya que todos los módulos siguen formando parte de una sola unidad desplegable.

## Beneficios

- Mayor legibilidad.
- Cambios localizados.
- Menor acoplamiento interno.
- Facilita pruebas y mantenimiento.
- Evita consultas SQL dentro de las vistas.
- Facilita justificar responsabilidades durante la evaluación.

## Riesgos o limitaciones

- Una separación excesiva puede crear archivos pequeños sin valor real.
- Puede existir duplicación si no se identifican responsabilidades comunes.
- Sigue existiendo dependencia entre módulos dentro del mismo proceso.

## Condición futura que podría justificar un cambio

Si un módulo adquiriera un ciclo de vida, carga, disponibilidad o equipo responsable claramente independiente, podría evaluarse su extracción a un componente desacoplado.

## Evidencia de validación

- Estructura de directorios del proyecto.
- Diagrama de macro-arquitectura.
- Revisión de que las vistas no ejecutan consultas SQL.
- Revisión de que `app.js` se concentra en configuración y montaje de módulos.

---

# ADR-05. PostgreSQL como persistencia relacional principal

## Necesidad o problema

Los datos de la librería poseen relaciones, restricciones de integridad, asociaciones N:M y reglas de negocio que deben mantenerse consistentes.

## Alternativas consideradas

1. PostgreSQL.
2. Base de datos documental.
3. Archivos locales.
4. Combinación de diferentes motores de persistencia.

## Decisión tomada

Se utilizará **PostgreSQL** como sistema principal de gestión de datos del ejercicio.

## Justificación técnica

El dominio contiene relaciones estructuradas entre libros, autores, géneros, conceptos, formatos, categorías e imágenes. PostgreSQL permite representar estas relaciones mediante claves primarias, foráneas, restricciones `UNIQUE`, `CHECK`, índices y otras reglas de integridad.

El modelo final se documenta normalizado hasta 4FN.

## Beneficios

- Integridad referencial.
- Soporte de transacciones.
- Restricciones declarativas.
- Consultas SQL expresivas.
- Adecuado para relaciones N:M.
- Permite proteger reglas incluso cuando la aplicación falla en validarlas.

## Riesgos o limitaciones

- Cambios importantes al esquema requieren migraciones controladas.
- El diseño debe mantenerse consistente con el código de la aplicación.
- La aplicación depende de la disponibilidad de PostgreSQL.

## Condición futura que podría justificar un cambio

No se prevé sustituir PostgreSQL para este alcance. Sólo tendría sentido reconsiderar la persistencia si aparecieran necesidades de datos no relacionales claramente incompatibles con el modelo actual.

## Evidencia de validación

- `docs/NORMALIZATION_4FN.xlsx`.
- `docs/DB_DESIGN_ER_4FN.png`.
- `db/01_schema.sql`.
- Pruebas negativas de restricciones e integridad.

---

# ADR-06. Almacenamiento de imágenes en filesystem y metadatos en PostgreSQL

## Necesidad o problema

Los libros pueden tener múltiples imágenes. El sistema necesita conservar tanto el archivo binario como información asociada a cada imagen.

## Alternativas consideradas

1. Guardar los archivos en filesystem y los metadatos/ruta en PostgreSQL.
2. Guardar las imágenes como datos binarios dentro de PostgreSQL.
3. Utilizar almacenamiento de objetos externo.

## Decisión tomada

Los archivos de imagen se almacenarán en el **filesystem de la aplicación**, mientras PostgreSQL almacenará su ruta o referencia y sus metadatos.

## Justificación técnica

Para el alcance académico del ejercicio, el almacenamiento local simplifica la implementación y evita aumentar innecesariamente el tamaño de la base de datos con contenido binario.

PostgreSQL conserva la información necesaria para relacionar una imagen con su libro, texto alternativo, orden y estado de portada.

## Beneficios

- Implementación sencilla.
- Base de datos más ligera.
- Fácil servicio de archivos estáticos.
- Metadatos protegidos mediante el modelo relacional.
- Permite varias imágenes por libro.

## Riesgos o limitaciones

- El filesystem y PostgreSQL deben mantenerse sincronizados.
- El despliegue en múltiples instancias complicaría el uso de almacenamiento local.
- Una pérdida del directorio de uploads puede dejar referencias inválidas.
- Se requieren validaciones fuertes de archivos.

## Condición futura que podría justificar un cambio

Si la aplicación escalara horizontalmente, manejara grandes volúmenes de archivos o necesitara alta disponibilidad de imágenes, podría migrarse a almacenamiento de objetos como Google Cloud Storage.

## Evidencia de validación

- Pruebas de carga JPG/JPEG, PNG y WebP.
- Pruebas negativas de extensión, MIME y tamaño.
- Consulta de metadatos de imagen en PostgreSQL.
- Verificación de archivos creados y eliminados en el directorio de uploads.

---

# ADR-07. Autenticación mediante sesión y hash de contraseñas

## Necesidad o problema

El sistema debe distinguir entre Visitante, Usuario Registrado y Administrador y evitar almacenar contraseñas en texto plano.

## Alternativas consideradas

1. Sesiones del lado del servidor con cookie de sesión.
2. Tokens JWT.
3. Autenticación básica HTTP.
4. Autenticación administrada por un proveedor externo.

## Decisión tomada

Para la aplicación server-side se utilizará **autenticación basada en sesión**, manteniendo en la sesión la información necesaria del usuario autenticado. Las contraseñas se almacenarán exclusivamente mediante hash seguro.

## Justificación técnica

El patrón de sesión encaja naturalmente con Express y EJS. La aplicación no necesita entregar tokens a clientes externos ni exponer una API, por lo que JWT introduciría complejidad sin una necesidad clara en este ejercicio.

## Beneficios

- Integración directa con el flujo server-side.
- Control centralizado de sesión.
- Logout sencillo.
- No es necesario exponer tokens de acceso al frontend.
- Compatible con autorización por rol.

## Riesgos o limitaciones

- La configuración de cookies debe endurecerse en producción.
- Si existieran múltiples instancias sería necesario compartir el almacenamiento de sesiones.
- Una configuración insegura de sesión puede introducir riesgo de secuestro de sesión.

## Condición futura que podría justificar un cambio

Podría evaluarse autenticación basada en tokens si el sistema incorporara clientes móviles, APIs externas o múltiples aplicaciones desacopladas.

## Evidencia de validación

- Pruebas de login correcto e incorrecto.
- Prueba de logout.
- Prueba de acceso de Visitante a ruta privada.
- Prueba de Usuario Registrado intentando acceder a una ruta administrativa.
- Verificación de que la contraseña almacenada no coincide con el texto original.

---

# ADR-08. Variables de entorno para configuración y secretos

## Necesidad o problema

La aplicación requiere parámetros como conexión a PostgreSQL, puerto y secreto de sesión. Publicar estos valores en código fuente o repositorio generaría un riesgo de seguridad.

## Alternativas consideradas

1. Variables de entorno mediante archivo `.env` local.
2. Valores escritos directamente en código.
3. Archivo de configuración versionado con credenciales reales.
4. Gestor externo de secretos.

## Decisión tomada

Los valores sensibles se proporcionarán mediante **variables de entorno**. El archivo `.env` no se publicará y se mantendrá un `.env.example` únicamente con nombres de variables y valores de ejemplo no sensibles.

## Justificación técnica

Esta decisión desacopla configuración y código, evita almacenar secretos directamente en Git y permite cambiar credenciales entre ambientes sin modificar el código fuente.

## Beneficios

- Reduce riesgo de exposición en GitHub.
- Permite configuraciones distintas por ambiente.
- Evita recompilar o modificar código al cambiar credenciales.
- Facilita preparar una entrega sin secretos.

## Riesgos o limitaciones

- El archivo `.env` sigue siendo sensible en la máquina donde existe.
- Una mala configuración de `.gitignore` puede provocar una publicación accidental.
- Las variables de entorno deben configurarse correctamente en cada ambiente.

## Condición futura que podría justificar un cambio

En un entorno productivo de mayor escala podría utilizarse un gestor especializado de secretos, por ejemplo un servicio administrado del proveedor cloud.

## Evidencia de validación

- `.env` excluido del repositorio.
- `.env.example` sin credenciales reales.
- Revisión del archivo `.tar.gz` antes de la publicación.
- Verificación de ausencia de secretos en la página de evidencias.

---

# ADR-09. Reverse proxy mediante Apache o NGINX

## Necesidad o problema

La aplicación no debe exponer directamente el proceso Node.js a Internet y deberá publicarse bajo el prefijo `/library`.

## Alternativas consideradas

1. Exponer directamente Node.js en un puerto público.
2. Publicar Node.js detrás de Apache.
3. Publicar Node.js detrás de NGINX.

## Decisión tomada

En el despliegue final Node.js escuchará únicamente en **`127.0.0.1:3000`** y el acceso externo se realizará mediante **Apache o NGINX como reverse proxy**, publicando `/library`.

La selección definitiva entre Apache y NGINX se realizará durante la fase de despliegue según el entorno del servidor.

## Justificación técnica

El reverse proxy permite separar la exposición pública del proceso de aplicación, manejar el prefijo de publicación y centralizar la entrada HTTP/HTTPS.

## Beneficios

- Node.js no queda expuesto directamente.
- Punto de entrada único.
- Facilita publicar la aplicación bajo `/library`.
- Permite administrar posteriormente TLS, cabeceras y reglas de proxy.

## Riesgos o limitaciones

- Introduce una configuración adicional.
- Las rutas, redirecciones, recursos estáticos y cookies deben probarse bajo el prefijo `/library`.
- Una configuración incorrecta del proxy puede impedir el funcionamiento de formularios o archivos estáticos.

## Condición futura que podría justificar un cambio

En otro entorno de despliegue podría utilizarse un balanceador administrado o proxy diferente. Para este ejercicio se mantendrá Apache o NGINX.

## Evidencia de validación

- Node.js accesible localmente mediante `127.0.0.1:3000`.
- Aplicación accesible externamente mediante `/library`.
- Pruebas de login, sesiones, formularios, recursos estáticos, imágenes y redirecciones detrás del proxy.

---

# 3. Relación con otros artefactos

Estas decisiones deberán mantenerse consistentes con:

- `docs/REQUIREMENTS.md`
- `docs/NORMALIZATION_4FN.xlsx`
- `docs/DB_DESIGN_ER_4FN.png`
- `docs/ARCHITECTURE_MONOLITHIC.png`
- `docs/SECURITY_REVIEW.md`
- `docs/TEST_PLAN.xlsx` o `docs/TEST_PLAN.md`
- `db/01_schema.sql`
- Código fuente de la aplicación

---

# 4. Revisión de decisiones

Una decisión podrá actualizarse cuando:

1. Cambie un requisito del ejercicio.
2. Se detecte un riesgo no contemplado.
3. Una prueba demuestre que la decisión no satisface el comportamiento esperado.
4. Cambie el entorno de despliegue.
5. Se realice una evolución futura de la arquitectura.

Cuando una decisión cambie, deberá conservarse la justificación del cambio y actualizarse la evidencia correspondiente.

---

# 5. Conclusión

Las decisiones registradas priorizan una solución coherente con el alcance académico del ejercicio: arquitectura monolítica, renderizado server-side, acceso directo a PostgreSQL, separación modular, controles de seguridad y despliegue mediante reverse proxy.

El propósito de este registro es demostrar que cada elección técnica responde a una necesidad concreta, reconoce alternativas y trade-offs, y puede validarse mediante evidencia reproducible.
