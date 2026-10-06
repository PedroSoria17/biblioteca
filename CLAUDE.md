# CLAUDE.md — Actividad de microservicios (Library)

## Vigencia de este archivo

Este archivo describe la **actividad actual**: evolucionar el proyecto Library
hacia microservicios Python/Flask con JWT + Redis.

`docs/CLAUDE.md` pertenece al **ejercicio monolítico anterior (Ejercicio 02)**.
Se conserva como historial del proyecto y **no debe borrarse**, pero sus
restricciones de alcance **ya no aplican** a esta actividad, en particular:

- "no implementar microservicios";
- "no introducir REST / JSON / XML";
- "no modificar `apps/services/`".

En esta actividad **sí está permitido y es requerido** trabajar en
`apps/services/`. Sus reglas de seguridad (consultas parametrizadas, sin
secretos en el repositorio, hashes de contraseñas, mínimo privilegio en
PostgreSQL, un solo administrador) **siguen vigentes**.

## Componentes del repositorio

| Ruta | Qué es | Estado en esta actividad |
| ---- | ------ | ------------------------ |
| `apps/web-monolito01/backend-node/` | Monolito Node/Express/EJS (Ejercicio 02) | Conservar. No romper. |
| `apps/Electron-app/` | Cliente Electron que consume XML de Books | Conservar. |
| `apps/services/login/` | Microservicio Flask de login (sesión Flask, bcrypt, verificación de correo, XML/JSON) | Se migrará a JWT + Redis en la fase 2. |
| `apps/services/soap/` | **Microservicio Books** (REST `/books`, `/books/<isbn>`, ... + SOAP `/soap` + WSDL) | Evolucionará con CRUD, JWT y caché Redis. **No** renombrar ni duplicar. |
| `apps/services/soap/desktop_client/` | App Tkinter actual | Se ampliará después (login, tokens, CRUDs, semáforos). No reescribir aún. |
| `apps/services/shared/` | Paquete `library_shared` (JWT, Redis, autorización, CORS) | Base común para todos los servicios. |
| `apps/services/users/`, `authors/`, `orders/`, `payments/` | Futuros microservicios | Aún no existen. |
| `data/` | Scripts SQL de `library_db` | Migraciones nuevas = archivos nuevos. |

### Books = `apps/services/soap/`

No crear `apps/services/books/`. El servicio `soap` ya expone los endpoints de
libros y sus clientes (Electron, Tkinter) dependen de su URL/puerto (5000). Si
alguna vez se considera necesario renombrarlo, primero documentar la razón
técnica y pedir confirmación; nunca hacerlo automáticamente.

## Arquitectura objetivo

- Microservicios Flask: `login`, `books` (= `soap`), `users`, `authors`,
  `orders`, `payments`.
- Una sola base PostgreSQL: `library_db` (fuente de verdad).
- Redis compartido para: sesiones, refresh tokens, revocación de JWT
  (`jwt:revoked:<jti>`), caché de catálogo (`books:<isbn>`,
  `books:list:<filtros-normalizados>`) y coordinación temporal.
- Desarrollo local en Windows + VS Code; despliegue en VM de Google Cloud con
  CentOS 10 (PostgreSQL y Redis ya instalados ahí).
- HTTPS termina en un reverse proxy (NGINX/Apache). Los servicios Flask no
  gestionan certificados.

## Cómo se ejecutan los servicios Python (importante para imports)

- Cada servicio se arranca con `python app.py` **desde su propia carpeta** y
  usa imports de primer nivel (`config`, `db`, `utils`, `routes`, `catalog`,
  `soap`...). Los nombres `config` y `db` existen en varios servicios.
- El código compartido vive en `apps/services/shared/library_shared/` (nombre
  único) y se instala en el venv de cada servicio con
  `pip install -e ../shared`. No usar `sys.path.append` ni copiar código.
- Pruebas: `python -m pytest` desde la carpeta del servicio (login, shared);
  `python -m unittest discover -s tests` en soap.

## Reglas de seguridad de esta actividad

### JWT
- Firmado con `JWT_SECRET_KEY` (variable de entorno, ≥ 32 caracteres, el mismo
  valor en todos los servicios). Nunca hardcodear.
- Algoritmo fijo **HS256**; nunca aceptar el `alg` que traiga el token.
- Access token: 20 minutos. Claims obligatorios: `user_id`, `role_id`, `jti`,
  `iat`, `exp`, `type` (`access`/`refresh`).
- Refresh token: mayor duración, su propio `jti`, controlado en Redis,
  revocable y **rotado** en cada uso.
- Usar siempre `library_shared.jwt_tokens` / `token_store` / `flask_auth`; no
  reimplementar validación de JWT en cada servicio.

### Autorización
- POST/PUT/PATCH/DELETE en users, authors, books, orders y payments exigen
  `Authorization: Bearer <JWT>`.
- 401: token ausente, malformado, expirado, revocado, firma inválida, claims
  inválidos o tipo incorrecto. 403: autenticado sin el rol requerido. Nunca
  confundirlos.
- Operaciones administrativas: rol ADMIN (`role_id = 2`). GET públicos del
  catálogo pueden seguir públicos; GET administrativos requieren auth + rol.

### Redis
- `REDIS_URL=redis://:password@host:6379/0` por variable de entorno.
- **Opcional** para caché: si falla, registrar (sin secretos) y responder
  desde PostgreSQL.
- **Crítico** para sesiones, refresh tokens y revocación: si falla, rechazar
  (503). Nunca permitir una operación protegida porque Redis falló.
- Toda clave con TTL explícito. Usar `library_shared.keys` para los nombres.
- Tras POST/PUT/PATCH/DELETE de libros: invalidar `books:<isbn>` y
  `books:list:*`.

### Logs y secretos
- Nunca registrar contraseñas, JWT completos, refresh tokens,
  `JWT_SECRET_KEY` ni `REDIS_URL` con contraseña.
- `.env` fuera de Git; `.env.example` solo con placeholders.
- Conservar bcrypt para contraseñas (compatible con hashes del monolito).

### CORS
- `CORS_ALLOWED_ORIGINS` con orígenes explícitos. En producción nunca `*`
  (`library_shared.settings` lo rechaza con `APP_ENV=production`).

## Base de datos

- `data/01_schema.sql` y los scripts 00–06 + `login_microservice.sql` son
  historial: **no modificarlos destructivamente**.
- Cambios de esquema = migración nueva, idempotente, en una transacción.
- `data/07_microservices_auth_orders_payments.sql` agrega `roles`,
  `usuarios.role_id` (sincronizado con `es_administrador` por trigger + CHECK),
  `pedidos`, `pedido_detalle` (precio histórico) y `pagos`.
- `usuarios.es_administrador` se conserva (lo usa el monolito). La regla de un
  único administrador sigue garantizada por `ux_usuarios_un_solo_administrador`.
- Operaciones que modifiquen stock deben ser transaccionales.

## Plan por fases

1. **Fase 1 (hecha)**: análisis, este archivo, migración 07, paquete
   `library_shared`, variables de entorno, pruebas unitarias.
2. **Fase 2 (hecha)**: Login → JWT access + refresh, sesiones Redis,
   `/refresh` con rotación atómica, `/logout` con revocación. Se retiró la
   sesión/cookie Flask. Registro, verificación de correo, XML/JSON y
   `/health` (ahora con Redis) se conservan.
3. **Fase 3 (hecha) — Books (soap)**: CRUD `POST/PUT/PATCH/DELETE /books`
   con Bearer + ADMIN, caché Redis cache-aside (`books:<isbn>`,
   `books:list:*`) con invalidación tras commit, `/health?details=true`, y
   `sql/03_books_crud_grants.sql`. SOAP, WSDL y GET existentes sin cambios.
4. **Users, Authors, Orders, Payments**: nuevos servicios con la misma base.
5. **Tkinter**: login, manejo y renovación de tokens, CRUDs, semáforos de
   disponibilidad.
6. **Despliegue CentOS 10**: reverse proxy HTTPS, systemd, variables de
   entorno reales fuera del repositorio.

## Disciplina de cambios

- Analizar el código existente antes de editar; cambios pequeños y revisables.
- No eliminar el monolito, SOAP, Electron ni funcionalidades existentes.
- No romper las pruebas existentes (login: pytest; soap: unittest).
- Preservar las respuestas XML/JSON existentes (`?format=xml|json`, XML por
  defecto).
- No hacer commit ni push salvo petición explícita.
- No ejecutar nada contra la VM de producción sin petición explícita.
- Documentar cualquier conflicto con estas instrucciones y elegir la opción
  menos destructiva.
