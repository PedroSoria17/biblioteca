# REQUISITOS DEL SISTEMA

## Aplicación Web Monolítica para Gestión de una Librería

**Asignatura:** Integración de Aplicaciones Computacionales  
**Arquitectura:** Monolítica server-side  
**Tecnologías principales:** Node.js, Express, EJS y PostgreSQL  
**Documento:** `docs/REQUIREMENTS.md`

---

## 1. Propósito

El propósito de este documento es definir los requisitos funcionales y no funcionales de la aplicación web monolítica para la gestión de una librería en línea, así como los actores, operaciones permitidas, supuestos, restricciones, riesgos iniciales y criterios de aceptación.

Este documento describe el **comportamiento objetivo del sistema**. El cumplimiento del código existente se revisará posteriormente mediante una matriz de trazabilidad y pruebas.

---

## 2. Alcance

La aplicación permitirá a usuarios registrados consultar el catálogo de libros y su información asociada. Un único usuario con rol de Administrador podrá gestionar los datos del sistema mediante operaciones CRUD.

El sistema manejará:

- Usuarios registrados.
- Libros.
- Autores.
- Géneros.
- Formatos.
- Categorías.
- Conceptos.
- Definiciones específicas de conceptos por libro.
- Imágenes asociadas a libros.
- Relaciones libro–autor.
- Relaciones libro–género.
- Relaciones libro–concepto.
- Precio y stock de cada libro.

La aplicación será una solución **monolítica con renderizado del lado del servidor**, sin APIs REST, GraphQL, SOAP ni microservicios para este ejercicio.

La carpeta `apps/services/` queda **fuera del alcance de este ejercicio**, ya que corresponde a actividades distintas.

---

# 3. Actores

## 3.1 Visitante

Usuario que no ha iniciado sesión.

### Operaciones permitidas

- Acceder a la pantalla de inicio de sesión.
- Acceder al formulario de registro.
- Crear una cuenta de usuario regular.
- Acceder únicamente a páginas expresamente definidas como públicas.

### Operaciones rechazadas

- Consultar el catálogo privado de libros.
- Consultar detalles privados de libros y conceptos.
- Ejecutar operaciones CRUD.
- Administrar usuarios.
- Administrar imágenes.
- Acceder a rutas administrativas.

---

## 3.2 Usuario Registrado

Usuario autenticado que no posee privilegios administrativos.

### Operaciones permitidas

- Iniciar y cerrar sesión.
- Consultar el catálogo de libros.
- Buscar libros por ISBN o título.
- Consultar el detalle de un libro.
- Consultar autores, géneros, formato, categoría, conceptos, definiciones e imágenes permitidas del libro.

### Operaciones rechazadas

- Crear, modificar o eliminar libros.
- Crear, modificar o eliminar catálogos.
- Modificar relaciones entre libros y autores, géneros o conceptos.
- Administrar imágenes.
- Administrar cuentas de otros usuarios.
- Acceder a funciones exclusivas del Administrador.

Cuando un usuario registrado intente acceder a una operación administrativa, el sistema deberá responder de forma controlada con acceso denegado.

---

## 3.3 Administrador

Usuario autenticado con privilegios administrativos.

### Operaciones permitidas

- Ejecutar todas las operaciones disponibles para un Usuario Registrado.
- Administrar libros.
- Administrar autores.
- Administrar géneros.
- Administrar formatos.
- Administrar categorías.
- Administrar conceptos.
- Administrar relaciones libro–autor.
- Administrar relaciones libro–género.
- Administrar relaciones libro–concepto.
- Administrar imágenes asociadas a libros.
- Administrar usuarios registrados cuando corresponda.
- Gestionar stock y precio.
- Ejecutar las funciones de mantenimiento disponibles en la interfaz administrativa.

### Restricción especial

En todo momento deberá existir **como máximo un Administrador** en la base de datos. Esta regla no dependerá únicamente de la lógica de la aplicación; deberá estar protegida también mediante una restricción de PostgreSQL.

---

# 4. Requisitos funcionales

## RF-01. Registro de usuarios

El sistema deberá permitir que un Visitante registre una nueva cuenta de usuario regular.

### Criterios de aceptación

- El formulario solicita los datos necesarios para crear la cuenta.
- El correo electrónico debe ser único.
- La contraseña nunca se almacena en texto plano.
- Una cuenta creada mediante registro público no obtiene privilegios de Administrador.
- Los errores de validación se muestran de forma controlada.

---

## RF-02. Inicio de sesión

El sistema deberá permitir que un usuario registrado inicie sesión mediante sus credenciales.

### Criterios de aceptación

- Credenciales válidas crean una sesión autenticada.
- Credenciales incorrectas no permiten el acceso.
- Un usuario inactivo no puede iniciar sesión.
- El mensaje de error no revela si falló específicamente el correo o la contraseña.
- La aplicación reconoce el rol del usuario autenticado.

---

## RF-03. Cierre de sesión

El sistema deberá permitir cerrar la sesión activa.

### Criterios de aceptación

- La sesión del usuario se invalida.
- Después del cierre de sesión, las rutas privadas vuelven a requerir autenticación.
- El usuario es redirigido a una página pública apropiada.

---

## RF-04. Control de acceso por autenticación

El sistema deberá impedir que un Visitante acceda a recursos definidos como privados.

### Criterios de aceptación

- Un Visitante que solicite una ruta privada es redirigido al inicio de sesión o recibe una respuesta controlada.
- El catálogo de libros requiere autenticación.
- Las rutas administrativas requieren autenticación y autorización.

---

## RF-05. Consulta del catálogo de libros

El sistema deberá permitir a los Usuarios Registrados y al Administrador consultar el catálogo de libros.

### Criterios de aceptación

- Se muestra una lista de libros disponibles en la base de datos.
- Cada libro presenta información suficiente para identificarlo.
- Desde el catálogo se puede acceder al detalle del libro.
- Un Visitante no puede consultar el catálogo privado.

---

## RF-06. Búsqueda de libros por ISBN y título

El sistema deberá permitir buscar libros utilizando ISBN o título.

### Criterios de aceptación

- Una búsqueda por ISBN devuelve el libro correspondiente cuando existe.
- Una búsqueda por una parte válida del título devuelve coincidencias.
- Una búsqueda sin coincidencias muestra un resultado vacío de forma controlada.
- La entrada del usuario se procesa mediante consultas SQL parametrizadas.

---

## RF-07. Consulta de detalle de libro

El sistema deberá mostrar el detalle de un libro a un usuario autorizado.

### Criterios de aceptación

El detalle puede incluir, según la información registrada:

- ISBN.
- Título.
- Año de publicación.
- Precio.
- Stock.
- Formato.
- Categoría.
- Autores.
- Géneros.
- Conceptos y definiciones.
- Imágenes.

---

## RF-08. CRUD de libros

El Administrador deberá poder crear, consultar, modificar y eliminar libros mediante la interfaz web.

### Criterios de aceptación

- Existe un formulario web para alta y edición.
- El ISBN no puede duplicarse.
- Se validan año, precio, stock, formato y categoría.
- La aplicación utiliza consultas SQL parametrizadas.
- Los errores se muestran de forma controlada.
- Las eliminaciones respetan las restricciones y relaciones definidas en PostgreSQL.

---

## RF-09. CRUD de autores

El Administrador deberá poder crear, consultar, modificar y eliminar autores.

### Criterios de aceptación

- Las operaciones se realizan mediante formularios HTML.
- Se validan los campos obligatorios.
- Una eliminación que viole integridad referencial debe rechazarse de forma controlada.

---

## RF-10. CRUD de géneros

El Administrador deberá poder crear, consultar, modificar y eliminar géneros.

### Criterios de aceptación

- El nombre de género respeta la restricción de unicidad definida en la base.
- Las operaciones se realizan mediante consultas parametrizadas.
- La integridad referencial se conserva.

---

## RF-11. CRUD de formatos

El Administrador deberá poder crear, consultar, modificar y eliminar formatos.

### Criterios de aceptación

- El nombre de formato debe ser único.
- No podrá eliminarse un formato cuando la operación viole una relación protegida con libros.
- Los errores se presentan de forma controlada.

---

## RF-12. CRUD de categorías

El Administrador deberá poder crear, consultar, modificar y eliminar categorías.

### Criterios de aceptación

- El nombre de categoría debe ser único.
- No podrá eliminarse una categoría cuando la operación viole una relación protegida con libros.
- Los errores se presentan de forma controlada.

---

## RF-13. CRUD de conceptos

El Administrador deberá poder crear, consultar, modificar y eliminar conceptos.

### Criterios de aceptación

- El nombre del concepto debe ser único.
- Un concepto puede reutilizarse en distintos libros.
- La definición específica no se almacena como atributo general del concepto, sino en la relación libro–concepto.

---

## RF-14. Asociación de múltiples autores a un libro

El Administrador deberá poder asociar varios autores a un mismo libro y un autor podrá estar asociado a varios libros.

### Criterios de aceptación

- La asociación se registra mediante la tabla puente correspondiente.
- No se almacena una lista de autores dentro de la tabla `libros`.
- Una misma asociación libro–autor no puede duplicarse.
- Puede conservarse el orden de participación del autor cuando aplique.

---

## RF-15. Asociación de múltiples géneros a un libro

El Administrador deberá poder asociar varios géneros a un mismo libro y un género podrá clasificar varios libros.

### Criterios de aceptación

- La asociación se registra mediante la tabla puente correspondiente.
- No se almacena una lista de géneros dentro de `libros`.
- Una misma asociación libro–género no puede duplicarse.

---

## RF-16. Conceptos y definiciones específicas por libro

El Administrador deberá poder asociar conceptos a libros y registrar una definición específica para cada relación libro–concepto.

### Criterios de aceptación

- Un libro puede contener múltiples conceptos.
- Un concepto puede aparecer en múltiples libros.
- La definición depende de la combinación `(ISBN, concepto_id)`.
- No se permite una relación libro–concepto sin definición.
- El sistema permite consultar la definición correspondiente desde el detalle del libro.

---

## RF-17. Gestión de imágenes de libros

El Administrador deberá poder cargar y eliminar imágenes asociadas a libros, administrar texto alternativo y marcar una imagen como portada.

### Criterios de aceptación

- Se aceptan únicamente imágenes JPG/JPEG, PNG y WebP.
- Se valida la extensión y el tipo MIME permitido.
- Se valida un tamaño máximo de archivo.
- El sistema genera el nombre físico del archivo y no utiliza directamente el nombre recibido del usuario.
- PostgreSQL almacena metadatos y la referencia o ruta del archivo.
- La ruta interna sensible del servidor no se expone al usuario.
- Como máximo una imagen puede estar marcada como portada para cada libro.
- El Administrador puede eliminar una imagen.
- El Administrador puede seleccionar cuál imagen será portada.

### Decisión técnica actual

El proyecto existente utiliza un límite técnico de **5 MB por imagen**. Este valor se considera una decisión de implementación y puede revisarse si el profesor solicita otro límite.

---

## RF-18. Control de precio y stock

El sistema deberá permitir registrar y modificar precio y stock de los libros.

### Criterios de aceptación

- El precio no puede ser negativo.
- El stock no puede ser negativo.
- PostgreSQL protege ambas reglas mediante restricciones `CHECK`.
- La aplicación valida los valores antes de enviar la operación a la base de datos.

---

## RF-19. Administración de usuarios

El Administrador deberá poder consultar y administrar usuarios registrados mediante las operaciones habilitadas por la aplicación.

### Criterios de aceptación

- Un usuario regular no puede acceder a la administración de usuarios.
- Los correos electrónicos permanecen únicos.
- El sistema puede impedir operaciones que comprometan la sesión o el control administrativo.
- Las contraseñas nunca se muestran ni se almacenan en texto plano.

---

## RF-20. Administrador único

El sistema deberá garantizar que exista como máximo un usuario con privilegios de Administrador.

### Criterios de aceptación

- PostgreSQL rechaza la creación de un segundo Administrador.
- La regla se mantiene incluso si una operación intenta omitir las validaciones de la aplicación.
- Cualquier transferencia de privilegios administrativos debe conservar la consistencia de la regla.

---

## RF-21. Validación server-side

Todos los formularios que modifiquen información deberán ser validados en el servidor.

### Criterios de aceptación

- No se depende únicamente de atributos HTML o JavaScript del navegador.
- Los campos obligatorios son revisados en el servidor.
- Los valores inválidos son rechazados.
- Los mensajes mostrados al usuario no revelan información interna sensible.

---

## RF-22. Manejo controlado de errores

La aplicación deberá manejar errores de forma controlada.

### Criterios de aceptación

- Un error interno no muestra consultas SQL, credenciales ni stack traces al usuario.
- Los errores HTTP conocidos se presentan mediante páginas o mensajes controlados.
- Los detalles técnicos necesarios pueden registrarse del lado del servidor para diagnóstico.

---

# 5. Requisitos no funcionales

## RNF-01. Seguridad de contraseñas

Las contraseñas deberán almacenarse mediante un algoritmo de hash seguro.

### Criterios de aceptación

- No existe una contraseña en texto plano dentro de la tabla de usuarios.
- La validación del login compara la contraseña mediante el algoritmo de hash utilizado por la aplicación.

---

## RNF-02. Protección de secretos y credenciales

Las credenciales, secretos, tokens y cadenas sensibles deberán mantenerse fuera del repositorio público.

### Criterios de aceptación

- Las credenciales de PostgreSQL se obtienen mediante variables de entorno.
- El secreto de sesión se obtiene mediante una variable de entorno.
- `.env` no se publica.
- Se proporciona `.env.example` sin valores reales.
- No se publican contraseñas, llaves SSH ni tokens en la página de evidencias.

---

## RNF-03. Protección frente a SQL Injection

Todas las operaciones que reciban valores del usuario deberán utilizar consultas SQL parametrizadas.

### Criterios de aceptación

- No se concatena directamente entrada del usuario dentro de consultas SQL.
- Se utilizan placeholders del controlador `pg`, por ejemplo `$1`, `$2`, etc.
- Las pruebas con caracteres especiales no alteran la estructura de la consulta.

---

## RNF-04. Autenticación y autorización separadas

La aplicación deberá diferenciar entre verificar que exista una sesión y verificar que el usuario posea privilegios administrativos.

### Criterios de aceptación

- Existe control para rutas que requieren usuario autenticado.
- Existe control adicional para rutas exclusivas del Administrador.
- Un Usuario Registrado recibe acceso denegado al intentar utilizar una operación administrativa.

---

## RNF-05. Integridad de datos

PostgreSQL deberá proteger la consistencia del modelo mediante PK, FK, `UNIQUE`, `CHECK`, índices y acciones referenciales justificadas.

### Criterios de aceptación

La base rechaza al menos:

- ISBN duplicado.
- Precio negativo.
- Stock negativo.
- FK inexistente.
- Duplicación de relaciones protegidas.
- Segundo Administrador.
- Segunda imagen de portada para el mismo libro.

---

## RNF-06. Modelo normalizado hasta 4FN

El modelo relacional deberá estar normalizado de forma demostrable hasta Cuarta Forma Normal.

### Criterios de aceptación

- Se documenta la evolución desde una estructura no normalizada.
- Se documentan 1FN, 2FN, 3FN/BCNF y 4FN.
- Las dependencias multivaluadas de autores, géneros, imágenes y conceptos se separan apropiadamente.
- Se conserva un diagrama ER final consistente con el esquema PostgreSQL.

---

## RNF-07. Mantenibilidad

El código deberá mantener separación de responsabilidades dentro del monolito.

### Criterios de aceptación

La solución distingue, al menos:

- Inicialización de Express.
- Configuración de PostgreSQL.
- Rutas.
- Controladores o lógica de aplicación.
- Middleware.
- Acceso a datos.
- Vistas EJS.
- Recursos estáticos.
- Manejo de uploads.

La lógica de negocio no deberá concentrarse completamente en `app.js` ni dentro de las vistas EJS.

---

## RNF-08. Renderizado server-side

Las vistas de la aplicación deberán generarse en el servidor mediante EJS.

### Criterios de aceptación

- El navegador recibe HTML renderizado por Node.js/Express.
- Los formularios HTML envían los datos directamente al monolito.
- No se requiere una SPA ni una API separada para la operación normal del ejercicio.

---

## RNF-09. Rendimiento básico

La aplicación deberá responder de forma adecuada para el volumen de datos esperado en un ejercicio académico.

### Criterios de aceptación

- La base cuenta con los índices necesarios cuando corresponda.
- Las búsquedas no requieren descargar todos los registros al navegador para filtrarlos.
- Las consultas se realizan directamente en PostgreSQL.

No se establece un SLA ni un tiempo máximo contractual, ya que el enunciado no define una métrica numérica de rendimiento.

---

## RNF-10. Usabilidad

La interfaz deberá proporcionar navegación y retroalimentación suficiente para completar las operaciones disponibles.

### Criterios de aceptación

- Los formularios identifican los campos necesarios.
- Los errores de validación son comprensibles.
- Una operación exitosa proporciona retroalimentación cuando corresponda.
- El usuario puede navegar entre catálogo, detalle y funciones habilitadas por su rol.

---

## RNF-11. Trazabilidad de errores

Los errores técnicos deberán poder diagnosticarse sin revelar detalles internos al usuario final.

### Criterios de aceptación

- Los errores internos pueden registrarse en el servidor.
- El usuario recibe un mensaje controlado.
- Las evidencias de prueba documentan el resultado observado cuando ocurra un error.

---

## RNF-12. Principio de mínimo privilegio en PostgreSQL

La aplicación web deberá conectarse a PostgreSQL mediante un usuario de aplicación y no mediante un superusuario.

### Criterios de aceptación

- El proceso Node.js utiliza una cuenta específica de aplicación.
- La cuenta posee únicamente los privilegios requeridos para operar el sistema.
- Las credenciales no se incluyen en el repositorio.

---

## RNF-13. Manejo seguro de sesiones

La aplicación deberá administrar sesiones de autenticación y permitir su invalidación.

### Criterios de aceptación

- La sesión se crea únicamente después de autenticación válida.
- El cierre de sesión invalida la sesión.
- El identificador de sesión no se utiliza como sustituto de la autorización por rol.
- La configuración de producción deberá revisar atributos de cookie adecuados al despliegue HTTP/HTTPS.

---

## RNF-14. Validación segura de archivos

Los archivos cargados deberán ser validados antes de su aceptación.

### Criterios de aceptación

- Se valida extensión.
- Se valida MIME.
- Se valida tamaño.
- Se genera un nombre de archivo propio del sistema.
- Los formatos no permitidos son rechazados.

---

## RNF-15. Disponibilidad básica

La aplicación deberá permanecer accesible mientras la instancia, PostgreSQL, el proceso Node.js y el reverse proxy se encuentren operativos.

No se establece un porcentaje de disponibilidad contractual, ya que el ejercicio no especifica un SLA.

---

## RNF-16. Despliegue mediante reverse proxy

La aplicación Node.js no deberá exponerse directamente a Internet en el despliegue final.

### Criterios de aceptación

- Node.js escucha en `127.0.0.1:3000`.
- Apache o NGINX publica la ruta `/library`.
- El reverse proxy reenvía las solicitudes al proceso Node.js.
- Funcionan correctamente vistas, formularios, sesiones, recursos estáticos, imágenes y redirecciones bajo `/library`.

---

# 6. Restricciones arquitectónicas y tecnológicas

| ID | Restricción |
|---|---|
| RA-01 | La solución debe ser monolítica. |
| RA-02 | El servidor de aplicación debe utilizar Node.js y Express. |
| RA-03 | Las vistas deben renderizarse server-side mediante EJS. |
| RA-04 | La aplicación debe acceder directamente a PostgreSQL mediante `pg`. |
| RA-05 | Las consultas que incorporen entrada del usuario deben ser parametrizadas. |
| RA-06 | No se desarrollarán APIs REST para este ejercicio. |
| RA-07 | No se utilizará GraphQL. |
| RA-08 | No se utilizará SOAP. |
| RA-09 | No se utilizarán microservicios para esta aplicación. |
| RA-10 | JSON y XML no se utilizarán como mecanismo de intercambio entre frontend y backend. |
| RA-11 | Los formularios HTML enviarán sus datos directamente al monolito. |
| RA-12 | Sólo usuarios registrados pueden acceder a las áreas privadas. |
| RA-13 | Debe existir como máximo un Administrador. |
| RA-14 | En producción Node.js deberá escuchar únicamente en `127.0.0.1:3000`. |
| RA-15 | El acceso externo final deberá realizarse mediante Apache o NGINX bajo `/library`. |

---

# 7. Supuestos

| ID | Supuesto |
|---|---|
| SUP-01 | La base de datos PostgreSQL del ejercicio ya se encuentra disponible en una máquina virtual de GCP para continuar el desarrollo. |
| SUP-02 | El modelo final de datos se documentará y mantendrá normalizado hasta 4FN. |
| SUP-03 | Los archivos de imagen se almacenarán en el filesystem de la aplicación y PostgreSQL conservará su ruta y metadatos. |
| SUP-04 | El volumen de información corresponde a un entorno académico y no requiere escalamiento horizontal en esta versión. |
| SUP-05 | El Administrador es responsable de la administración de catálogos y datos maestros del sistema. |
| SUP-06 | Los servicios ubicados en `apps/services/` no forman parte del alcance de este ejercicio monolítico. |
| SUP-07 | Las evidencias de despliegue en el servidor de la materia se prepararán después de completar implementación, seguridad y pruebas. |

---

# 8. Riesgos iniciales

| ID | Riesgo | Consecuencia posible | Tratamiento requerido |
|---|---|---|---|
| R-01 | Acceso no autorizado | Consulta o modificación de información sin permiso | Autenticación, sesiones y autorización por rol |
| R-02 | SQL Injection | Lectura, modificación o eliminación no autorizada de datos | Consultas parametrizadas y validación server-side |
| R-03 | Subida de archivos peligrosos | Ejecución o almacenamiento de contenido no permitido | Validación de extensión, MIME, tamaño y nombre |
| R-04 | Exposición de credenciales | Compromiso de PostgreSQL o de las sesiones | Variables de entorno, `.gitignore` y `.env.example` |
| R-05 | Eliminación accidental de información | Pérdida de datos o ruptura de relaciones | FK, acciones referenciales justificadas y confirmaciones de interfaz |
| R-06 | Publicación de datos sensibles | Exposición de secretos en GitHub o en el servidor de evidencias | Revisión previa a publicación y exclusión de secretos |
| R-07 | Creación de un segundo Administrador | Violación de la regla de negocio | Restricción a nivel PostgreSQL y prueba negativa |
| R-08 | Dos portadas para un mismo libro | Inconsistencia visual y de datos | Restricción de unicidad por libro |
| R-09 | Datos inválidos de precio o stock | Inconsistencia del catálogo | Validación de aplicación y restricciones `CHECK` |
| R-10 | Error interno expuesto al usuario | Fuga de estructura SQL o información técnica | Manejador de errores controlado |

---

# 9. Matriz resumida de permisos

| Operación | Visitante | Usuario Registrado | Administrador |
|---|:---:|:---:|:---:|
| Registro | Sí | No requerido | No requerido |
| Login | Sí | Sí | Sí |
| Logout | No | Sí | Sí |
| Consultar catálogo | No | Sí | Sí |
| Buscar por ISBN/título | No | Sí | Sí |
| Consultar detalle | No | Sí | Sí |
| CRUD libros | No | No | Sí |
| CRUD autores | No | No | Sí |
| CRUD géneros | No | No | Sí |
| CRUD formatos | No | No | Sí |
| CRUD categorías | No | No | Sí |
| CRUD conceptos | No | No | Sí |
| Asociar autores | No | No | Sí |
| Asociar géneros | No | No | Sí |
| Asociar conceptos/definiciones | No | No | Sí |
| Gestionar imágenes | No | No | Sí |
| Administrar usuarios | No | No | Sí |

---

# 10. Criterios globales de aceptación

Se considerará que los requisitos de esta versión han sido satisfechos cuando:

1. El registro, login y logout funcionen de acuerdo con los roles definidos.
2. Un Visitante no pueda acceder al catálogo privado ni a rutas administrativas.
3. Un Usuario Registrado pueda consultar y buscar libros, pero no ejecutar operaciones administrativas.
4. El Administrador pueda completar el CRUD de las tablas administrables desde la interfaz web.
5. La búsqueda funcione por ISBN y título.
6. Las relaciones libro–autor, libro–género y libro–concepto se gestionen correctamente.
7. Las definiciones se almacenen en la relación libro–concepto.
8. La carga de imágenes acepte únicamente JPG/JPEG, PNG y WebP y valide MIME, tamaño y nombre.
9. PostgreSQL impida ISBN duplicado, stock negativo, precio negativo, FK inválidas, segundo Administrador y segunda portada para el mismo libro.
10. Las contraseñas se almacenen mediante hash.
11. Las consultas que reciban entrada del usuario sean parametrizadas.
12. Las rutas administrativas estén protegidas por rol.
13. Los errores internos no expongan SQL, stack traces ni credenciales al usuario.
14. El modelo final esté documentado hasta 4FN y sea consistente con el diagrama ER.
15. La aplicación pueda ejecutarse detrás de Apache o NGINX mediante `/library`.
16. Las pruebas funcionales, de autorización, integridad, validación y despliegue cuenten con evidencia reproducible.

---

# 11. Trazabilidad posterior

Los identificadores definidos en este documento (`RF-*`, `RNF-*`, `RA-*` y `R-*`) deberán utilizarse posteriormente en:

- `TEST_PLAN.xlsx` o `TEST_PLAN.md`.
- `SECURITY_REVIEW.md`.
- Evidencias de pruebas.
- Matriz de cumplimiento del sistema actual.
- Reporte técnico.
- Página web final de evidencias.

Esto permitirá relacionar cada requisito con su implementación, prueba y resultado observado.
