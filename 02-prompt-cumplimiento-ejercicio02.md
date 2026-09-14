# PROMPT 02 — Correcciones de Cumplimiento del Ejercicio 02

## Contexto

Este repositorio corresponde actualmente al **Ejercicio 02** de la materia **Integración de Aplicaciones Computacionales**.

La aplicación activa es una librería web monolítica desarrollada con:

- Node.js
- Express
- EJS
- PostgreSQL
- `pg`
- `express-session`
- `bcryptjs`
- `multer`

La solución debe permanecer como un **monolito server-side**.

La carpeta `services/`, cualquier trabajo SOAP, microservicios, XML o material del Ejercicio 03 está fuera del alcance y no debe ser reintroducido.

---

# 1. Archivos que debes revisar antes de modificar código

Lee primero, en este orden:

1. `CLAUDE.md`
2. `docs/REQUIREMENTS.md`
3. `docs/ENGINEERING_DECISIONS.md`
4. `docs/REQUIREMENTS_COMPLIANCE.md`
5. `01-prompt-monolito.md`

Después inspecciona el código actual del monolito, especialmente:

- `apps/web-monolito01/backend-node/src/app.js`
- `apps/web-monolito01/backend-node/src/server.js`
- `apps/web-monolito01/backend-node/src/config/db.js`
- `apps/web-monolito01/backend-node/src/middleware/auth.js`
- `apps/web-monolito01/backend-node/src/middleware/upload.js`
- `apps/web-monolito01/backend-node/src/middleware/errorHandler.js`
- `apps/web-monolito01/backend-node/src/modules/auth/`
- `apps/web-monolito01/backend-node/src/modules/libros/`
- `apps/web-monolito01/backend-node/src/modules/usuarios/`
- `apps/web-monolito01/backend-node/src/lib/catalogoFactory.js`
- `apps/web-monolito01/backend-node/src/views/`
- `apps/web-monolito01/backend-node/.env.example`
- `apps/web-monolito01/backend-node/.gitignore`
- `apps/web-monolito01/backend-node/package.json`
- `sql/schema.sql`

No asumas que la documentación describe exactamente el código actual: primero confirma cada hallazgo revisando la implementación.

---

# 2. Objetivo general

Implementa en una sola ronda de trabajo las correcciones prioritarias **P0-01 a P0-05** documentadas en `docs/REQUIREMENTS_COMPLIANCE.md`.

El objetivo es llevar la aplicación actual a cumplimiento con los requisitos prioritarios sin rehacer el sistema ni modificar su arquitectura.

Debes trabajar sobre la implementación existente y realizar los cambios mínimos necesarios.

---

# 3. P0-01 — Proteger catálogo y detalle de libro

## Requisitos relacionados

- RF-04
- RF-05
- RF-07
- RA-12

## Resultado requerido

El catálogo y el detalle de libros deben ser privados.

Debe cumplirse lo siguiente:

- `GET /libros` requiere usuario autenticado.
- `GET /libros/:isbn` requiere usuario autenticado.
- Usuario Registrado puede acceder.
- Administrador puede acceder.
- Visitante no autenticado debe ser redirigido de forma controlada al login o recibir la respuesta de autenticación ya definida por el proyecto.
- Login y registro continúan siendo públicos.
- Las operaciones administrativas continúan protegidas por `requireAdmin`.

## Restricción

Reutiliza el middleware existente. No crees un segundo sistema de autenticación.

---

# 4. P0-02 — Búsqueda por ISBN y título

## Requisito relacionado

- RF-06

## Resultado requerido

La búsqueda del catálogo debe permitir encontrar libros por:

- ISBN
- título

La implementación debe continuar utilizando SQL parametrizado mediante `pg`.

## Debe probarse

- ISBN completo.
- Fragmento válido de título.
- Búsqueda sin coincidencias.
- Entrada con caracteres especiales.
- La entrada del usuario nunca debe concatenarse directamente al SQL.

Actualiza también el texto o placeholder de la interfaz si actualmente indica que sólo busca por título.

---

# 5. P0-03 — Endurecer gestión de imágenes

## Requisitos relacionados

- RF-17
- RNF-14

## Formatos permitidos

Únicamente:

- JPG
- JPEG
- PNG
- WebP

GIF no está permitido para este ejercicio.

## Resultado requerido

La carga de imágenes debe validar:

1. extensión permitida;
2. MIME permitido;
3. tamaño máximo;
4. nombre físico generado por el sistema.

Mantén el límite actual de **5 MB**, salvo que exista una razón técnica real para cambiarlo.

No utilices directamente el nombre original enviado por el usuario como nombre final del archivo.

## También debes revisar

La funcionalidad de imágenes debe permitir o conservar:

- carga;
- eliminación;
- selección de portada;
- texto alternativo;
- orden de presentación cuando aplique.

Si actualmente el texto alternativo u orden sólo pueden asignarse durante la carga pero no editarse después, implementa el cambio mínimo necesario para que puedan administrarse desde la interfaz existente.

## Integridad

Debe mantenerse la regla de máximo una portada por libro.

## Manejo de errores

Un archivo inválido debe producir un mensaje controlado y no un stack trace.

---

# 6. P0-04 — Eliminar fallbacks sensibles y usar usuario de aplicación PostgreSQL

## Requisitos relacionados

- RNF-02
- RNF-12

## Contexto

La base de datos utilizada por el ejercicio es:

- `library_db`

El usuario de aplicación es:

- `library_user`

La contraseña real no debe escribirse en ningún archivo versionado.

## Resultado requerido

Revisa:

- `src/config/db.js`
- `src/app.js`
- `.env.example`

y realiza los cambios necesarios para que:

- no exista contraseña PostgreSQL hardcodeada como fallback;
- no exista un secreto de sesión inseguro usado como fallback de producción;
- la aplicación use variables de entorno;
- `.env.example` contenga únicamente placeholders no sensibles;
- `.env.example` use como ejemplo:
  - `PGDATABASE=library_db`
  - `PGUSER=library_user`
- no se recomiende utilizar el superusuario `postgres` para ejecutar la aplicación;
- el código falle de forma clara y controlada al iniciar si faltan variables sensibles indispensables.

No escribas la contraseña real en el repositorio, comentarios, documentación ni salida final.

No modifiques el archivo `.env` real si existe.

---

# 7. P0-05 — Completar validación server-side

## Requisito relacionado

- RF-21

## Objetivo

Revisa las entradas recibidas por formularios y completa validaciones faltantes del lado del servidor.

Como mínimo revisa:

### Autenticación / usuarios

- campos obligatorios;
- formato básico de email;
- IDs de usuario cuando correspondan;
- estados o banderas permitidas.

### Libros

- ISBN requerido;
- título requerido;
- año de publicación válido;
- precio numérico no negativo;
- stock entero no negativo;
- formato y categoría válidos.

### Asociaciones

- `autor_id`;
- `genero_id`;
- `concepto_id`;
- ISBN;
- orden;
- definición requerida cuando corresponda.

Los IDs deben validarse como valores numéricos/enteros antes de utilizarlos cuando corresponda.

### Imágenes

- extensión;
- MIME;
- tamaño;
- texto alternativo;
- orden;
- indicador de portada.

## Principio

La existencia de restricciones HTML o PostgreSQL no sustituye la validación server-side.

PostgreSQL seguirá actuando como última barrera de integridad.

## Manejo de errores

No expongas:

- SQL;
- stack traces;
- credenciales;
- rutas internas sensibles.

---

# 8. Restricciones obligatorias durante esta tarea

No hagas ninguno de los siguientes cambios todavía:

- no implementes reverse proxy;
- no configures Apache;
- no configures NGINX;
- no cambies aún Node.js a `127.0.0.1:3000`;
- no implementes aún `/library`;
- no crees microservicios;
- no crees una API REST;
- no agregues GraphQL;
- no agregues SOAP;
- no uses JSON/XML como mecanismo principal frontend-backend;
- no reemplaces EJS;
- no agregues React, Vue, Angular ni otro frontend SPA;
- no agregues ORM;
- no migres el proyecto a TypeScript;
- no cambies el modelo de datos 4FN sin una necesidad demostrable;
- no modifiques material del Ejercicio 03;
- no recrees `services/`;
- no realices refactors amplios no relacionados.

---

# 9. Reglas de implementación

Para cada cambio:

1. inspecciona primero la implementación existente;
2. reutiliza funciones y middleware actuales cuando sea posible;
3. realiza el cambio mínimo necesario;
4. mantén SQL parametrizado;
5. conserva la organización modular actual;
6. no rompas funcionalidades existentes;
7. evita dependencias nuevas salvo que sean realmente necesarias;
8. si necesitas una dependencia nueva, justifica por qué antes de instalarla.

Si detectas que un punto ya cumple correctamente, no lo reescribas sólo por cambiar código.

---

# 10. Validación requerida

Después de implementar P0-01 a P0-05:

## A. Revisión estática

Revisa el diff completo y confirma:

- no se introdujeron secretos;
- no hay SQL concatenado con entrada del usuario;
- no se introdujo una API;
- no se rompió el patrón EJS;
- no se modificó material fuera del alcance;
- no se agregaron cambios de despliegue.

## B. Pruebas disponibles

Ejecuta las pruebas automatizadas existentes si el proyecto tiene un comando válido para ello.

No inventes resultados.

Si no existe una suite automatizada suficiente, indícalo claramente.

## C. Verificación manual propuesta

Entrega una lista exacta de pruebas manuales para validar:

### Autenticación

- visitante → `/libros`;
- visitante → detalle;
- usuario registrado → catálogo;
- usuario registrado → detalle;
- administrador → catálogo;
- administrador → CRUD.

### Búsqueda

- ISBN;
- título;
- sin resultados;
- caracteres especiales.

### Uploads

- JPG válido;
- PNG válido;
- WebP válido;
- GIF;
- MIME falso;
- archivo demasiado grande;
- cambio de portada;
- edición de texto alternativo/orden.

### Validaciones

- email inválido;
- precio negativo;
- stock negativo;
- año inválido;
- IDs inválidos;
- asociación incompleta.

### Configuración

- aplicación con variables correctas;
- comportamiento cuando falta un secreto requerido.

---

# 11. Entrega final esperada

Al terminar, responde con este formato:

## 1. Resumen

Explica brevemente qué se corrigió.

## 2. Archivos modificados

Para cada archivo:

- ruta;
- cambio realizado;
- requisito(s) relacionado(s).

## 3. P0-01

- implementación;
- resultado esperado;
- riesgo relevante.

## 4. P0-02

- implementación;
- resultado esperado;
- riesgo relevante.

## 5. P0-03

- implementación;
- resultado esperado;
- riesgo relevante.

## 6. P0-04

- implementación;
- resultado esperado;
- riesgo relevante.

## 7. P0-05

- implementación;
- resultado esperado;
- riesgo relevante.

## 8. Pruebas ejecutadas

Indica únicamente las que realmente ejecutaste.

Para cada una:

- comando;
- resultado.

## 9. Pruebas manuales pendientes

Entrega pasos concretos para que el desarrollador pueda verificarlas.

## 10. Riesgos o asuntos pendientes

Documenta cualquier comportamiento que todavía requiera atención.

## 11. Diff summary

Resume qué archivos fueron creados, modificados o eliminados.

---

# 12. Actualización de documentación

Después de realizar las modificaciones:

- **NO marques automáticamente como "Cumple" un requisito que no hayas podido verificar.**
- Puedes proponer qué estados deberían cambiar en `docs/REQUIREMENTS_COMPLIANCE.md`, pero no actualices esa matriz sin distinguir entre:
  - implementación realizada;
  - verificación estática;
  - prueba ejecutada;
  - prueba manual pendiente.

No modifiques `docs/REQUIREMENTS.md` ni `docs/ENGINEERING_DECISIONS.md` salvo que detectes una contradicción real. En ese caso, repórtala antes de editar.

---

# 13. Criterio final

El objetivo no es crear una nueva aplicación.

El objetivo es corregir la aplicación existente para cumplir P0-01, P0-02, P0-03, P0-04 y P0-05, preservando:

- arquitectura monolítica;
- Express;
- EJS;
- PostgreSQL;
- `pg`;
- sesiones;
- separación de responsabilidades;
- modelo de datos 4FN;
- funcionalidades que ya trabajan correctamente.
