# Microservicio Users (puerto 5002)

Administra los registros de la tabla existente `usuarios` de `library_db`:
nombre, email, contraseña, rol y estado activo/inactivo.

| Servicio      | Puerto |
| ------------- | ------ |
| Books / SOAP  | 5000   |
| Login         | 5001   |
| **Users**     | **5002** |
| Authors       | 5003 (futuro) |
| Orders        | 5004 (futuro) |
| Payments      | 5005 (futuro) |

## Qué hace y qué NO hace

Users **no** autentica ni emite tokens. Login sigue siendo responsable de
`/register`, `/login`, `/refresh`, `/logout`, `/session`, la verificación de
correo y la generación de JWT. Users **solo valida** los access tokens que
emite Login, con `library_shared` (mismo `JWT_SECRET_KEY` y mismo Redis).

Respuestas en **JSON** (servicio nuevo, sin contrato XML histórico).

## Endpoints y permisos

| Método | Ruta | Permiso | Respuesta OK |
| ------ | ---- | ------- | ------------ |
| GET | `/health` | público | 200 / 503 |
| GET | `/users?limit=50&offset=0` | ADMIN | 200 |
| GET | `/users/me` | cualquier usuario autenticado | 200 |
| GET | `/users/<usuario_id>` | ADMIN | 200 |
| POST | `/users` | ADMIN | 201 |
| PUT | `/users/<usuario_id>` | ADMIN | 200 |
| PATCH | `/users/<usuario_id>` | ADMIN | 200 |
| DELETE | `/users/<usuario_id>` | ADMIN | 200 |

- Todas (salvo `/health`) exigen `Authorization: Bearer <access_token>`.
- La validación es la de `library_shared` (`require_auth` / `require_roles(ROLE_ADMIN)`):
  firma, HS256 fijo, expiración, `type=access`, claims `user_id`, `role_id`,
  `jti`, `iat`, `exp`, y revocación `jwt:revoked:<jti>` en Redis.
- `GET /users/me` toma la identidad **solo** del token; cualquier
  `usuario_id` en la URL o el query se ignora.
- `limit` 1–200 (por defecto 50), `offset` ≥ 0.

Formato de éxito:

```json
{"success": true, "data": {"usuario_id": 7, "nombre_completo": "Ana Torres",
 "email": "ana.torres@example.com", "role_id": 1, "role": "USER",
 "activo": true, "fecha_registro": "2026-10-05T19:00:00+00:00"}}
```

`GET /users` agrega `"pagination": {"limit": 50, "offset": 0, "total": 31}`.

Formato de error (igual para los 401/403/503 de `library_shared`):

```json
{"success": false, "code": "EMAIL_ALREADY_EXISTS", "message": "Email is already in use."}
```

`password` y `password_hash` **nunca** aparecen en una respuesta ni en los logs.

## Campos aceptados

| Campo | Tipo | POST | PUT | PATCH |
| ----- | ---- | ---- | --- | ----- |
| `nombre_completo` | string 1–150 (se recorta) | obligatorio | obligatorio | opcional |
| `email` | string, formato válido, ≤ 255 (se normaliza `strip().lower()`) | obligatorio | obligatorio | opcional |
| `password` | string, ≥ 8 caracteres, ≤ 72 bytes UTF-8 | obligatorio | **opcional** | opcional |
| `role_id` | entero existente en `roles` | opcional (1 = USER) | obligatorio | opcional |
| `activo` | boolean | opcional (`true`) | obligatorio | opcional |

- Rechazados con **400 `FIELDS_NOT_ALLOWED`**: `password_hash`,
  `es_administrador`, `fecha_registro`, `usuario_id`.
- Cualquier otro campo desconocido: **400 `UNKNOWN_FIELDS`** (con la lista en
  `details.fields`).
- Tipos estrictos: `"2"` o `true` no valen como `role_id`; `null` no es válido.
- **PUT**: reemplaza todos los campos administrativos. `password` es
  opcional a propósito: es una credencial, no forma parte de la
  representación del usuario (nunca se devuelve). Si no se envía, se conserva
  el hash actual; si se envía, se reemplaza.
- **PATCH**: solo cambia los campos enviados (p. ej. `{"activo": false}` no
  toca nombre, email, contraseña ni rol). Cuerpo vacío → 400.
- `usuario_id` y `fecha_registro` nunca se modifican.

## Contraseñas

- **Cambio de contraseña**: una sola estrategia, `PATCH /users/<id>` con
  `{"password": "..."}` (ADMIN). No hay endpoint aparte.
- Se guarda un hash **bcrypt** (`$2b$`, coste 12), el mismo esquema con el que
  Login crea hashes y con el que verifica (`bcrypt.checkpw`). También es
  compatible con los hashes `bcryptjs` del monolito.
- Mínimo 8 caracteres (igual que `/register` de Login). Máximo 72 bytes:
  bcrypt ignora lo que pasa de 72 bytes, así que se rechaza en lugar de
  truncarlo en silencio.
- El hash se calcula **fuera** de la transacción (bcrypt es lento a propósito).

## Roles y la regla de un único ADMIN

- Roles: `1 = USER`, `2 = ADMIN` (tabla `roles`). Un `role_id` inexistente →
  **400 `INVALID_ROLE`**.
- Users **solo escribe `role_id`**; nunca `es_administrador`. El trigger
  `trg_usuarios_sincronizar_rol` (migración 07) sincroniza `es_administrador`
  y `ck_usuarios_role_admin_sync` + `ux_usuarios_un_solo_administrador`
  siguen siendo la barrera final.
- Crear o promover a ADMIN cuando ya existe uno → **409 `ADMIN_ALREADY_EXISTS`**.
  Si dos peticiones compiten, el índice único lo impide y el error de
  PostgreSQL se traduce al mismo 409 (nunca 500).
- Un ADMIN debe estar activo: crear/promover un ADMIN inactivo →
  **409 `ADMIN_MUST_BE_ACTIVE`**.

### Protección del último ADMIN

Con un único ADMIN posible, cualquiera de estas operaciones dejaría el
sistema sin administrador funcional y se rechaza con
**409 `LAST_ADMIN_REQUIRED`**:

- `DELETE` del ADMIN;
- `PATCH`/`PUT` con `activo: false` sobre el ADMIN;
- `PATCH`/`PUT` con `role_id: 1` sobre el ADMIN.

La regla cuenta “otros ADMIN activos”, así que seguiría siendo correcta si
algún día se permitiera más de uno. El ADMIN sí puede editar su nombre, email
y contraseña. La transferencia de administración (degradar al actual y
promover a otro en una sola transacción) **no** está en esta fase; el
monolito tiene `sp_usuario_transferir_administracion` para eso.

## DELETE e historial

Cada escritura bloquea la fila (`SELECT ... FOR UPDATE`) y valida dentro de
la misma transacción.

| Situación | Resultado |
| --------- | --------- |
| Usuario sin pedidos | **200**, borrado físico. `usuario_detalle` y `usuario_verificacion_email` se borran por su `ON DELETE CASCADE` (son datos del registro de Login, no historial). |
| Usuario con pedidos | **409 `USER_HAS_ORDER_HISTORY`**. No se borra nada (ni usuario ni pedidos ni pagos); no se usa CASCADE. Alternativa: `PATCH {"activo": false}`. |
| Pedido creado justo entre la comprobación y el DELETE | `fk_pedidos_usuario` (`ON DELETE RESTRICT`) lo impide → el mismo 409. |
| Otra FK futura que lo impida | **409 `USER_HAS_DEPENDENCIES`**. |
| Usuario inexistente | **404 `USER_NOT_FOUND`**. |
| El ADMIN | **409 `LAST_ADMIN_REQUIRED`**. |

## Activo / inactivo y tokens existentes (riesgo conocido)

- Login ya rechaza el `/login` de un usuario inactivo, y `/refresh` relee
  `activo` y `role_id` en PostgreSQL, así que un usuario desactivado **no
  puede renovar** su sesión.
- Users **no** revoca los access tokens vigentes al desactivar, borrar o
  cambiar el rol de un usuario: esos tokens siguen siendo válidos hasta su
  expiración (**máximo 20 minutos**). Durante ese tiempo `role_id` del token
  puede no coincidir con la base. El impacto es acotado porque el único ADMIN
  no puede degradarse ni desactivarse. **Pendiente** (fuera de esta fase):
  revocación por usuario (p. ej. `user:<id>:tokens_valid_after` en Redis) o
  consulta del estado en PostgreSQL en operaciones sensibles.

## Códigos de respuesta

| HTTP | `code` | Cuándo |
| ---- | ------ | ------ |
| 400 | `INVALID_INPUT`, `UNKNOWN_FIELDS`, `FIELDS_NOT_ALLOWED`, `INVALID_ROLE` | validación |
| 401 | `MISSING_TOKEN`, `INVALID_AUTHORIZATION_HEADER`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `TOKEN_REVOKED` | token ausente, malformado, firma/alg/claims inválidos, refresh usado como access, expirado o revocado |
| 403 | `FORBIDDEN` | autenticado sin rol ADMIN |
| 404 | `USER_NOT_FOUND`, `NOT_FOUND` | usuario o ruta inexistente |
| 405 | `METHOD_NOT_ALLOWED` | método no soportado |
| 409 | `EMAIL_ALREADY_EXISTS`, `ADMIN_ALREADY_EXISTS`, `ADMIN_MUST_BE_ACTIVE`, `LAST_ADMIN_REQUIRED`, `USER_HAS_ORDER_HISTORY`, `USER_HAS_DEPENDENCIES` | conflictos de negocio |
| 503 | `AUTH_BACKEND_UNAVAILABLE` | Redis caído: no se puede comprobar la revocación → se rechaza (nunca se deja pasar porque el JWT “parece válido”) |
| 503 | `DATABASE_UNAVAILABLE` | PostgreSQL inaccesible |
| 500 | `INTERNAL_ERROR` | error inesperado (sin detalles internos) |

## Health

`GET /health` (público):

```json
{"success": true, "service": "users", "status": "healthy", "database": "connected", "redis": "connected"}
```

Devuelve **503** si PostgreSQL o Redis no responden: sin Redis el servicio no
puede atender ninguna operación autenticada de forma segura. No incluye
hosts, usuarios ni contraseñas.

## Redis

Solo se usa para la infraestructura de seguridad (revocación de JWT, vía
`library_shared`). Users **no** crea claves de caché.

## PostgreSQL y permisos

- Base `library_db`, usuario `library_user`.
- No se necesita script de grants nuevo: `library_user` ya tiene
  `SELECT, INSERT, UPDATE, DELETE` sobre `usuarios`, `usuario_detalle`,
  `usuario_verificacion_email` y `pedidos` (`00_create_database.sql` partes
  B/C, `login_microservice.sql`, migración 07) y `SELECT` sobre `roles`
  (migración 07). Las cascadas y la verificación RESTRICT las ejecuta
  PostgreSQL sin privilegios extra. Usa la secuencia `usuarios_usuario_id_seq`
  (cubierta por `GRANT USAGE, SELECT ON ALL SEQUENCES`, parte C).
- No se modifica ninguna tabla.

## Variables de entorno

Ver `.env.example`. Obligatorias: `DB_HOST`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `JWT_SECRET_KEY` (≥ 32, **igual** que en Login y Books) y
`REDIS_URL` (el **mismo** Redis que Login). Sin ellas el servicio no arranca.

| Variable | Default |
| -------- | ------- |
| `FLASK_HOST` | `127.0.0.1` |
| `FLASK_PORT` | `5002` |
| `FLASK_DEBUG` | `false` |
| `APP_ENV` | `development` (en `production` se prohíbe `*` en CORS) |
| `DB_PORT` | `5432` |
| `REDIS_CONNECT_TIMEOUT_SECONDS` / `REDIS_SOCKET_TIMEOUT_SECONDS` | `2` |
| `REDIS_HEALTH_CHECK_INTERVAL_SECONDS` | `30` |
| `CORS_ALLOWED_ORIGINS` | vacío = sin CORS |

## Instalación y ejecución

Windows (PowerShell), desde `apps\services\users`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt   # o requirements.txt sin pytest
Copy-Item .env.example .env           # y completar valores reales
python app.py                         # http://127.0.0.1:5002
```

CentOS 10, desde `apps/services/users`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && chmod 600 .env   # valores reales fuera del repo
python app.py
```

En la VM, HTTPS termina en el reverse proxy (NGINX/Apache) que reenvía a
`127.0.0.1:5002`; el servicio no gestiona certificados.

## Pruebas

```powershell
python -m pytest
```

- Unitarias: no necesitan PostgreSQL ni Redis (fakes en `tests/conftest.py`
  que reproducen UNIQUE, índice de un solo ADMIN, FK de rol, RESTRICT de
  pedidos, el trigger de rol y el rollback).
- Compatibilidad con Login: una prueba ejecuta en un subproceso el
  `_check_password` **real** de `apps/services/login` sobre un hash generado
  por Users (sin copiar código).
- **Integración** (`tests/test_integration_postgres.py`): se ejecuta solo si
  existe `USERS_IT_DB_NAME`, que **debe terminar en `_test`** porque las
  pruebas borran todos los usuarios y pedidos. Necesita una base desechable
  con el esquema completo (01, 06, 04, 05, `login_microservice.sql`, 07).
  Incluye un login real con `login_user` de Login contra la misma base.

```powershell
$env:USERS_IT_DB_HOST="127.0.0.1"; $env:USERS_IT_DB_PORT="5432"
$env:USERS_IT_DB_NAME="library_users_test"; $env:USERS_IT_DB_USER="library_user"
$env:USERS_IT_DB_PASSWORD="<password local>"
python -m pytest
```

## Ejemplos (curl)

En PowerShell usar `curl.exe` (no el alias `curl`). `$ADMIN` / `$USER` son
access tokens obtenidos de Login (`POST http://127.0.0.1:5001/login?format=json`).

```bash
# GET /users con ADMIN -> 200
curl -s -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5002/users

# GET /users con USER -> 403 FORBIDDEN
curl -s -H "Authorization: Bearer $USER" http://127.0.0.1:5002/users

# GET /users/me (cualquier usuario autenticado)
curl -s -H "Authorization: Bearer $USER" http://127.0.0.1:5002/users/me

# POST -> 201
curl -s -X POST http://127.0.0.1:5002/users \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"nombre_completo":"Ana Torres","email":"ana@example.com","password":"ClaveSegura123","role_id":1,"activo":true}'

# PATCH parcial (desactivar)
curl -s -X PATCH http://127.0.0.1:5002/users/7 \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"activo":false}'

# Cambio de contraseña
curl -s -X PATCH http://127.0.0.1:5002/users/7 \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"password":"NuevaClave456"}'

# DELETE (sin pedidos) -> 200
curl -s -X DELETE -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5002/users/7

# Último ADMIN -> 409 LAST_ADMIN_REQUIRED
curl -s -X PATCH http://127.0.0.1:5002/users/1 \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d '{"role_id":1}'

# Usuario con pedidos -> 409 USER_HAS_ORDER_HISTORY
curl -s -X DELETE -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5002/users/12

# Redis caído -> 503 AUTH_BACKEND_UNAVAILABLE (y /health -> 503, "redis":"unavailable")
curl -s -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5002/users
```
