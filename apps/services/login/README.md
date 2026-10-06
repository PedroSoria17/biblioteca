# Login Microservice — Ejercicio de integración

Microservicio Flask **independiente** de autenticación y gestión básica de
usuarios. No integra ni depende de `apps/Electron-app/`, `apps/web-monolito01/`
ni `apps/services/soap/`; usa la **misma** base PostgreSQL (`library_db`) que
ya usa el resto del proyecto, sin crear una base nueva.

La autenticación es **JWT + Redis** (access token de 20 minutos, refresh token
rotativo, sesiones y revocación en Redis), construida sobre el paquete
compartido `library_shared` (`apps/services/shared/`). Desde la Fase 2 ya **no**
se usa la sesión/cookie de Flask.

## Arquitectura

```text
                    Flask app (app.py)
                          |
        +-----------------+-----------------+
        |                                   |
        v                                   v
   routes/health.py                   routes/auth.py
   GET /health                        POST /register, /login, /refresh, /logout
   (PostgreSQL + Redis)               GET  /session, /verify-email
        |                                   |
        |                     +-------------+--------------+
        |                     v                            v
        |          services/auth_service.py      services/token_service.py
        |          (validación, bcrypt,          (sesión, rotación, logout;
        |           transacciones)                usa library_shared)
        |                     |                            |
        |        +------------+-----------+                v
        |        v                        v        library_shared (JWT HS256,
        |  repositories/           services/       RedisGateway, token_store,
        |  user_repository.py      email_service   flask_auth, CORS)
        v        |                                         |
   db/connection.py (psycopg 3)                            v
        |                                           Redis (auth:session:*,
        v                                           auth:refresh:*, jwt:revoked:*)
   PostgreSQL library_db (usuarios + role_id, usuario_detalle,
                           usuario_verificacion_email)
```

- `utils/responses.py`: capa central que serializa **el mismo** dict de
  respuesta como XML o JSON (`?format=xml|json`, XML por defecto) y atrapa
  cualquier error para devolver siempre XML/JSON, nunca una página HTML de
  Flask.
- `utils/errors.py`: errores de dominio (`ServiceError`) con código HTTP y
  mensaje ya pensados para ser bilingües.
- `utils/validators.py` / `utils/tokens.py`: normalización/validación de
  email y contraseña, generación y hashing del token de verificación.
- `repositories/user_repository.py`: único lugar que ejecuta SQL contra
  `usuarios`, `usuario_detalle` y `usuario_verificacion_email`.
- `services/auth_service.py`: reglas de negocio de registro/login/verificación
  (transacciones, bcrypt, mensajes de error genéricos).
- `services/email_service.py`: envío de correo desacoplado (Postfix local o
  SMTP relay), sin credenciales embebidas.
- `services/token_service.py`: ciclo de vida de la sesión (login → refresh →
  logout). Solo orquesta funciones de `library_shared`; no reimplementa JWT ni
  acceso a Redis.

## Requisitos

- Python 3.11+ (probado con 3.14).
- Acceso a la instancia PostgreSQL del proyecto (`library_db`, la misma VM de
  GCP que usan el monolito y el servicio SOAP), con la migración
  `data/07_microservices_auth_orders_payments.sql` aplicada (aporta
  `usuarios.role_id`).
- Un Redis accesible mediante `REDIS_URL` (obligatorio: sesiones, refresh
  tokens y revocación).
- Para probar el envío real de correo: un Postfix accesible desde la VM (ver
  sección "Correo y Postfix" más abajo). No es necesario para desarrollar ni
  para correr las pruebas automatizadas.

## Instalación

Desde `apps/services/login/`:

```bash
python -m venv .venv
```

Activar el entorno virtual:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

Instalar dependencias (**desde `apps/services/login/`**: `requirements.txt`
incluye `-e ../shared`, una ruta relativa al directorio actual que instala el
paquete compartido `library_shared` junto con PyJWT, redis y flask-cors):

```bash
pip install -r requirements.txt
```

## Configuración

Copiar `.env.example` a `.env` (nunca commitear `.env` ni credenciales
reales):

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

Editar `.env` con los valores reales de conexión a `library_db` y, si se
quiere probar correo, los datos del Postfix/SMTP disponible. Variables
mínimas (ver `.env.example` para la lista completa y comentarios):

```text
FLASK_ENV, FLASK_HOST, FLASK_PORT, SECRET_KEY
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
MAIL_ENABLED, MAIL_HOST, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS, MAIL_FROM
PUBLIC_BASE_URL, EMAIL_TOKEN_EXPIRATION_MINUTES
APP_ENV, JWT_SECRET_KEY, JWT_ACCESS_TTL_MINUTES, JWT_REFRESH_TTL_DAYS
REDIS_URL, REDIS_CONNECT_TIMEOUT_SECONDS, REDIS_SOCKET_TIMEOUT_SECONDS
CORS_ALLOWED_ORIGINS
```

Si falta alguna variable indispensable (`SECRET_KEY`, `DB_HOST`, `DB_NAME`,
`DB_USER`, `DB_PASSWORD`, `JWT_SECRET_KEY`, `REDIS_URL`), `config.py` lanza
`ConfigurationError` con un mensaje claro al arrancar, en vez de fallar más
adelante de forma confusa. `JWT_SECRET_KEY` debe tener al menos 32 caracteres
y ser **el mismo** en todos los microservicios. Con `APP_ENV=production`,
`CORS_ALLOWED_ORIGINS=*` se rechaza al arrancar.

`FLASK_PORT` por defecto es `5001` para no chocar con el servicio SOAP
(`5000`) ni con el monolito Node.js (`3000`).

## Base de datos

Este microservicio **reutiliza** `library_db`; no crea una base nueva ni
modifica `usuarios` de forma incompatible. Antes de arrancar el servicio hay
que aplicar una sola vez:

```bash
psql -U <admin> -d library_db -f ../../../data/login_microservice.sql
```

y después la migración de microservicios (agrega `roles` y
`usuarios.role_id`, que `/login` y `/refresh` leen):

```bash
psql -U <admin> -d library_db -v ON_ERROR_STOP=1 -f ../../../data/07_microservices_auth_orders_payments.sql
```

`login_microservice.sql` crea únicamente dos tablas nuevas (ver comentarios dentro del
archivo para el detalle):

- `usuario_detalle`: datos 1:1 adicionales del usuario (nombre desglosado,
  `email_verificado`), enlazada a `usuarios.usuario_id` mediante FK/PK
  compartida.
- `usuario_verificacion_email`: tokens de verificación de correo, guardando
  solo su hash (nunca el valor en texto plano).

No borra, renombra ni recrea nada existente. Es seguro volver a aplicarlo
sobre una base que ya tenía `01_schema.sql`/`02_seed_30_per_table.sql`
corridos: fallará con "already exists" si las tablas nuevas ya estaban
creadas (no las vuelve a crear silenciosamente encima).

### Compatibilidad con usuarios existentes

- Los usuarios creados por el monolito (`usuarios.password_hash` generado
  con `bcryptjs`) **no se migran ni se tocan**. Este servicio usa la
  librería `bcrypt` de Python, que produce y valida el mismo formato de hash
  ($2a$/$2b$), así que puede autenticarlos sin cambios.
- Un usuario legado **sin fila en `usuario_detalle`** puede iniciar sesión
  normalmente: `POST /login` solo depende de `usuarios.email`,
  `usuarios.password_hash`, `usuarios.activo` y `usuarios.role_id`. La verificación de correo
  (`usuario_detalle.email_verificado`) solo aplica a cuentas creadas a
  través de `POST /register` de este microservicio; este servicio no
  bloquea el login de nadie por no tener esa fila.

## Ejecución

Desde `apps/services/login/`, con el entorno virtual activado y `.env`
configurado:

```bash
python app.py
```

Debería quedar un servidor Flask escuchando en `http://127.0.0.1:5001`
(o el `FLASK_HOST`/`FLASK_PORT` configurado).

## Endpoints disponibles

| Método | Endpoint        | Autenticación                        | Función |
| ------ | --------------- | ------------------------------------ | ------- |
| POST   | `/register`     | pública                              | Registrar un nuevo usuario |
| POST   | `/login`        | pública (email + contraseña)         | Validar credenciales y emitir access + refresh token |
| POST   | `/refresh`      | `Authorization: Bearer <refresh>`    | Rotar: consumir el refresh y emitir un par nuevo |
| POST   | `/logout`       | `Authorization: Bearer <access>`     | Revocar el access token, la sesión y su refresh |
| GET    | `/session`      | opcional `Bearer <access>`           | Consultar la sesión actual |
| GET    | `/health`       | pública                              | Estado de Flask, PostgreSQL y Redis |
| GET    | `/verify-email` | pública (token del correo)           | Validar el token enviado al correo del usuario |

Todos aceptan `?format=xml` o `?format=json`; **XML es el formato por
defecto** si no se envía `format`. Esto aplica también a respuestas de
error (validación, credenciales inválidas, 401, 503, 404, 500, etc.).

### Tokens

| Token   | Algoritmo | Duración | Claims |
| ------- | --------- | -------- | ------ |
| access  | HS256     | 20 min (`JWT_ACCESS_TTL_MINUTES`) | `user_id`, `role_id`, `jti`, `iat`, `exp`, `type="access"`, `sid` |
| refresh | HS256     | 7 días (`JWT_REFRESH_TTL_DAYS`)   | `user_id`, `role_id`, `jti`, `iat`, `exp`, `type="refresh"`, `sid` |

`sid` identifica la sesión lógica. Ambos se firman con `JWT_SECRET_KEY`; la
validación fija HS256 (no acepta el `alg` que traiga el token). Un access
token **no** sirve en `/refresh` y un refresh token **no** sirve en
`/logout` ni `/session` (401).

### Claves Redis

| Clave                  | Contenido | TTL |
| ---------------------- | --------- | --- |
| `auth:session:<sid>`   | `user_id`, `role_id`, `email`, `created_at`, `refreshed_at`, `refresh_jti` | vida del refresh (se renueva en cada `/refresh`) |
| `auth:refresh:<jti>`   | `user_id`, `role_id`, `sid` | hasta el `exp` del refresh |
| `jwt:revoked:<jti>`    | `1` | hasta el `exp` del access revocado |

Nunca se guardan contraseñas, hashes, `JWT_SECRET_KEY` ni tokens completos:
el refresh se controla por su `jti`.

### Flujo

- **Login**: valida email/contraseña con bcrypt contra PostgreSQL (incluye
  `activo`), lee `role_id`, crea `sid`, emite el par de tokens, guarda la
  sesión y el refresh en Redis y **solo entonces** responde. Si Redis falla a
  mitad de camino, se borra lo que se hubiera escrito y se responde 503 sin
  tokens.
- **Refresh (rotación)**: valida firma/HS256/expiración/claims/`type`;
  comprueba que la sesión exista y que su `refresh_jti` sea este token; vuelve
  a leer al usuario en PostgreSQL (rol **actual**, `activo`); consume el
  refresh de forma **atómica** (`RedisGateway.pop`, MULTI/EXEC); emite un par
  nuevo con el mismo `sid`; guarda el nuevo refresh y actualiza la sesión
  (`refresh_jti`, `role_id`, TTL). Si dos peticiones usan el mismo refresh a
  la vez, solo una obtiene el token de Redis; la otra recibe 401. Los
  chequeos de sesión y PostgreSQL se hacen antes del `pop` para que una
  caída de PostgreSQL no "queme" el refresh del cliente.
- **Logout**: valida el access token (incluida revocación), crea
  `jwt:revoked:<jti>` con TTL = vida restante del token, borra el refresh
  vigente de la sesión y la sesión. Un segundo logout con el mismo token
  responde 401 `TOKEN_REVOKED`.

### Errores de autenticación

Las respuestas de error de autenticación incluyen `code`, además de
`success` y `message`, para que el cliente sepa qué hacer:

| HTTP | `code` | Significado / acción del cliente |
| ---- | ------ | -------------------------------- |
| 401  | `MISSING_TOKEN`, `INVALID_AUTHORIZATION_HEADER` | Enviar `Authorization: Bearer ...` |
| 401  | `INVALID_TOKEN` | Token malformado, firma/algoritmo/claims/tipo incorrectos |
| 401  | `TOKEN_EXPIRED` | Access expirado → llamar `/refresh` |
| 401  | `TOKEN_REVOKED` | Sesión cerrada o refresh ya usado → volver a hacer login |
| 503  | `AUTH_BACKEND_UNAVAILABLE` | Redis caído → reintentar; **no** descartar los tokens |

`POST /login` con credenciales incorrectas conserva su respuesta previa:
`401 {"success": false, "message": "Invalid credentials"}`.

### Ejemplos JSON

Login correcto (`POST /login?format=json`):

```json
{
  "success": true,
  "message": "Login successful",
  "user": { "id": 1, "email": "usuario@example.com", "role_id": 1 },
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 1200,
  "refresh_expires_in": 604800
}
```

Login incorrecto (mismo mensaje para email inexistente, password incorrecto o
usuario inactivo):

```json
{ "success": false, "message": "Invalid credentials" }
```

Refresh correcto (`POST /refresh?format=json` con `Authorization: Bearer
<refresh_token>`):

```json
{
  "success": true,
  "message": "Token refreshed",
  "access_token": "eyJ... (nuevo jti)",
  "refresh_token": "eyJ... (nuevo jti)",
  "token_type": "Bearer",
  "expires_in": 1200,
  "refresh_expires_in": 604800,
  "user": { "id": 1, "email": "usuario@example.com", "role_id": 1 }
}
```

Refresh reutilizado:

```json
{ "success": false, "message": "Token has been revoked.", "code": "TOKEN_REVOKED" }
```

Logout (`POST /logout?format=json` con `Authorization: Bearer <access_token>`):

```json
{ "success": true, "message": "Logged out" }
```

Redis no disponible (login, refresh, logout, session):

```json
{ "success": false, "message": "Authentication backend temporarily unavailable.", "code": "AUTH_BACKEND_UNAVAILABLE" }
```

Registro correcto (`201 Created`):

```json
{
  "success": true,
  "message": "User registered. Check your email to verify your account.",
  "user": { "id": 5, "email": "usuario@example.com" }
}
```

`GET /session` sin header `Authorization`:

```json
{ "success": true, "authenticated": false }
```

`GET /session` con un access token válido:

```json
{
  "success": true,
  "authenticated": true,
  "user": { "id": 1, "email": "usuario@example.com", "role_id": 1 }
}
```

`GET /health?format=json`:

```json
{ "success": true, "service": "login", "status": "healthy", "database": "connected", "redis": "connected" }
```

Con Redis caído responde `503` con `"redis": "unavailable"` (sin host ni
contraseña).

### Ejemplos XML

Login correcto en XML (formato por defecto):

```xml
<?xml version='1.0' encoding='utf-8'?>
<response>
    <success>true</success>
    <message>Login successful</message>
    <user>
        <id>1</id>
        <email>usuario@example.com</email>
        <role_id>1</role_id>
    </user>
    <access_token>eyJhbGciOiJIUzI1NiIs...</access_token>
    <refresh_token>eyJhbGciOiJIUzI1NiIs...</refresh_token>
    <token_type>Bearer</token_type>
    <expires_in>1200</expires_in>
    <refresh_expires_in>604800</refresh_expires_in>
</response>
```

Error de credenciales en XML:

```xml
<?xml version='1.0' encoding='utf-8'?>
<response>
    <success>false</success>
    <message>Invalid credentials</message>
</response>
```

Token expirado en XML:

```xml
<?xml version='1.0' encoding='utf-8'?>
<response>
    <success>false</success>
    <message>Token has expired.</message>
    <code>TOKEN_EXPIRED</code>
</response>
```

## Manual API Test Flow

Estas pruebas se hacen **sin** Electron, sin el monolito web, sin SOAP y sin
ninguna interfaz gráfica del proyecto: solo Postman o `curl` contra el
microservicio corriendo de forma aislada (`python app.py`).

Se asume `FLASK_PORT=5001`, es decir base `http://127.0.0.1:5001`.

### 1. Health

```bash
curl "http://127.0.0.1:5001/health?format=json"
```

Verifica en la respuesta `"success": true`, `"database": "connected"`
(Flask y PostgreSQL ambos operativos).

```bash
curl "http://127.0.0.1:5001/health?format=xml"
curl "http://127.0.0.1:5001/health"
```

La última (sin `format`) debe devolver XML.

### 2. Register (JSON)

```bash
curl -X POST "http://127.0.0.1:5001/register?format=json" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Pedro",
    "apellido_paterno": "Soria",
    "apellido_materno": "Gonzalez",
    "email": "pedro.prueba@example.com",
    "password": "PasswordSeguro123!"
  }'
```

Comprobar en PostgreSQL:

```sql
SELECT usuario_id, nombre_completo, email, password_hash FROM usuarios WHERE email = 'pedro.prueba@example.com';
SELECT * FROM usuario_detalle WHERE usuario_id = (SELECT usuario_id FROM usuarios WHERE email = 'pedro.prueba@example.com');
SELECT verificacion_id, usuario_id, fecha_expiracion, fecha_verificacion FROM usuario_verificacion_email WHERE usuario_id = (SELECT usuario_id FROM usuarios WHERE email = 'pedro.prueba@example.com');
```

- `password_hash` debe empezar con `$2b$` (bcrypt), nunca texto plano.
- Debe existir exactamente una fila en `usuario_detalle` para ese
  `usuario_id`.
- Debe existir una fila en `usuario_verificacion_email` con
  `fecha_verificacion` en `NULL` (todavía no verificado).

### 3. Register (respuesta XML) y XML por defecto

```bash
curl -X POST "http://127.0.0.1:5001/register?format=xml" \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Ana","apellido_paterno":"Lopez","apellido_materno":"Diaz","email":"ana.prueba@example.com","password":"OtraSegura123!"}'

curl -X POST "http://127.0.0.1:5001/register" \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Luis","apellido_paterno":"Perez","apellido_materno":"Ruiz","email":"luis.prueba@example.com","password":"OtraSegura123!"}'
```

Ambas respuestas deben venir en XML; la segunda confirma que XML es el
formato por defecto.

### 4. Email duplicado

```bash
curl -X POST "http://127.0.0.1:5001/register?format=json" \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Pedro","apellido_paterno":"Soria","apellido_materno":"Gonzalez","email":"pedro.prueba@example.com","password":"PasswordSeguro123!"}'
```

Debe responder `409 Conflict` con `"message": "Email already registered"`,
sin crear una segunda fila en `usuarios`.

### 5. Email inválido

```bash
curl -X POST "http://127.0.0.1:5001/register?format=json" \
  -H "Content-Type: application/json" \
  -d '{"nombre":"X","apellido_paterno":"Y","apellido_materno":"Z","email":"correo-invalido","password":"PasswordSeguro123!"}'
```

Debe responder `400 Bad Request` y **no** debe crearse ningún usuario.

### 6. Verificación del correo

Con `MAIL_ENABLED=true` y Postfix configurado (ver siguiente sección), el
correo de verificación debe llegar a la bandeja del destinatario con un
enlace del estilo:

```text
http://127.0.0.1:5001/verify-email?token=<token>
```

Abrir ese enlace (o repetirlo con curl):

```bash
curl "http://127.0.0.1:5001/verify-email?token=<token>&format=json"
```

Comprobar en PostgreSQL que `usuario_detalle.email_verificado` pasó a
`TRUE` y que `usuario_verificacion_email.fecha_verificacion` ya no es
`NULL`. Repetir la misma llamada debe seguir respondiendo éxito (operación
idempotente), sin error.

Durante desarrollo, si `MAIL_ENABLED=false` y `DEV_SHOW_VERIFICATION_LINK=true`,
la URL de verificación se imprime en la consola del servidor al registrar,
para poder probar este flujo sin un servidor de correo real.

### 7. Login incorrecto

```bash
curl -X POST "http://127.0.0.1:5001/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email":"no-existe@example.com","password":"cualquier"}'

curl -X POST "http://127.0.0.1:5001/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email":"pedro.prueba@example.com","password":"password-incorrecto"}'
```

Ambos deben responder `401` con el mismo mensaje genérico
`"Invalid credentials"`.

### 8. Login correcto (obtener tokens)

```bash
curl -X POST "http://127.0.0.1:5001/login?format=json" \
  -H "Content-Type: application/json" \
  -d '{"email":"pedro.prueba@example.com","password":"PasswordSeguro123!"}'
```

Comprobar `"success": true`, `user.role_id`, `access_token`, `refresh_token`,
`"token_type": "Bearer"` y `"expires_in": 1200`. Copiar ambos tokens:

```bash
ACCESS="<access_token>"
REFRESH="<refresh_token>"
```

En Redis deben existir `auth:session:<sid>` y `auth:refresh:<jti>` con TTL.
La respuesta ya **no** trae `Set-Cookie`.

### 9. Session

```bash
curl -H "Authorization: Bearer $ACCESS" "http://127.0.0.1:5001/session?format=json"
```

Debe responder `"authenticated": true` con el usuario y su `role_id`.

### 10. Refresh (rotación)

```bash
curl -X POST -H "Authorization: Bearer $REFRESH" "http://127.0.0.1:5001/refresh?format=json"
# repetir EXACTAMENTE la misma llamada:
curl -X POST -H "Authorization: Bearer $REFRESH" "http://127.0.0.1:5001/refresh?format=json"
```

La primera devuelve un par nuevo; la segunda `401 TOKEN_REVOKED` (el refresh
anterior quedó inutilizable). Guardar los tokens nuevos en `ACCESS`/`REFRESH`.
Enviar un access token a `/refresh` también debe responder 401.

### 10b. Logout

```bash
curl -X POST -H "Authorization: Bearer $ACCESS" "http://127.0.0.1:5001/logout?format=json"
curl -H "Authorization: Bearer $ACCESS" "http://127.0.0.1:5001/session?format=json"
curl -X POST -H "Authorization: Bearer $REFRESH" "http://127.0.0.1:5001/refresh?format=json"
```

El logout responde `200`; las dos llamadas siguientes `401 TOKEN_REVOKED`.

### 11. XML en todas las operaciones

Repetir los pasos 2, 7, 8, 9, 10, 10b y el health check reemplazando
`?format=json` por `?format=xml` (o quitando el parámetro, ya que XML es el
default) y confirmar que cada respuesta viene en XML bien formado.

## Pruebas automatizadas

```bash
python -m pytest
```

Cubren (sin necesidad de una base de datos ni de un Redis reales: ambos se
sustituyen por fakes en memoria en `tests/conftest.py`):

- flujo JWT completo a través de la app Flask real: login, claims y TTL,
  sesión/refresh en Redis, rotación, reutilización y uso concurrente del
  refresh, cambio de rol, usuario desactivado, logout y revocación, 401/503,
  XML/JSON, `/session`, `/health` con Redis caído, CORS, configuración
  obligatoria y ausencia de secretos en logs (`tests/test_jwt_auth_flow.py`);
- regresión de `/register`, `/verify-email` y 404 en XML/JSON
  (`tests/test_register_and_verify_preserved.py`);

- selección de formato XML/JSON y formato por defecto (`tests/test_responses.py`);
- serialización genérica dict → XML/JSON (`tests/test_responses.py`);
- validación de email/contraseña (`tests/test_validators.py`);
- generación y hashing del token de verificación (`tests/test_tokens.py`);
- hashing/verificación de contraseñas con bcrypt, incluida la compatibilidad
  con hashes estilo bcryptjs del monolito (`tests/test_password_hashing.py`).

No hay pruebas de integración contra PostgreSQL real en este repositorio
(el proyecto no expone credenciales de la VM de GCP en el entorno de
pruebas). Para agregarlas localmente: crear `tests/test_integration_*.py`
que llame directamente a `repositories/user_repository.py` o a
`services/auth_service.py` contra una base de pruebas (nunca la productiva),
limpiando los datos que crean al final de cada test; no truncar ni borrar
tablas compartidas con el monolito.

## Correo electrónico y Postfix

`services/email_service.py` no contiene credenciales SMTP; todo llega por
variables de entorno (`MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`,
`MAIL_PASSWORD`, `MAIL_USE_TLS`, `MAIL_FROM`). El código nunca ejecuta
`yum`, `dnf`, `systemctl` ni `postconf`: la configuración del propio
Postfix es responsabilidad de la infraestructura de la VM, no de este
microservicio.

Para usar un Postfix local en la VM de Google Cloud (Linux/CentOS):

```text
MAIL_ENABLED=true
MAIL_HOST=localhost
MAIL_PORT=25
MAIL_USE_TLS=false
MAIL_USERNAME=
MAIL_PASSWORD=
```

Si más adelante se necesita un SMTP relay externo en vez de (o encadenado
con) Postfix, basta con cambiar `MAIL_HOST`/`MAIL_PORT`/`MAIL_USERNAME`/
`MAIL_PASSWORD`/`MAIL_USE_TLS`: el código no asume ningún proveedor
específico.

Para comprobar manualmente que Postfix está listo (sin este microservicio):

```bash
# Postfix activo
systemctl status postfix

# Puerto SMTP escuchando
ss -ltnp | grep :25

# Enviar un correo de prueba directo desde la VM
echo "prueba" | mail -s "prueba postfix" tu_correo@example.com

# Ver colas / logs si un correo no llega
mailq
tail -f /var/log/maillog
```

Estos comandos son de verificación manual de infraestructura; no se ejecutan
automáticamente desde el código del microservicio.

## Desarrollo local sin Postfix

Con `MAIL_ENABLED=false`, `POST /register` sigue funcionando completo
(usuario + token creados en PostgreSQL), pero no intenta enviar correo real:
solo registra en el log que el envío está deshabilitado. Nunca se imprime la
contraseña ni el hash de la contraseña. Con `DEV_SHOW_VERIFICATION_LINK=true`
(solo pensado para desarrollo, nunca producción) también se imprime en
consola la URL de verificación completa, para poder probar
`GET /verify-email` sin correo real.

## Configuración pendiente en la VM (fuera de este repositorio)

- Instalar/activar Postfix (o el MTA que se decida) y abrir el puerto SMTP
  correspondiente si el microservicio corre en un proceso separado.
- Crear/echar a andar la variable `DB_PASSWORD` real (y el resto de
  variables de `.env`) directamente en el entorno de la VM, nunca en Git.
- Si se expone `FLASK_PORT` fuera de `localhost`, revisar firewall/reglas de
  GCP para ese puerto.
- Configurar `SESSION_COOKIE_SECURE=true` únicamente cuando el servicio
  quede detrás de HTTPS real.

## HTTPS

El servicio no gestiona certificados TLS. En la VM debe quedar detrás de un
reverse proxy (NGINX/Apache) que termine HTTPS y reenvíe a `127.0.0.1:5001`.
Los tokens viajan en el header `Authorization`, así que sin HTTPS serían
interceptables: no exponer el puerto 5001 directamente a Internet.

## Alcance de esta entrega

- Fase 2 (actual): Login migrado a JWT + Redis con refresh rotativo y logout
  con revocación, reutilizando `library_shared`.
- La sesión/cookie de Flask se retiró: solo la usaban `/login`, `/logout` y
  `/session`, y ningún cliente del repositorio dependía de ella (registro y
  verificación de correo nunca la usaron). `SECRET_KEY` sigue siendo
  obligatoria para Flask.
- Todavía **no** se integra con Electron, el monolito web, SOAP/Books ni
  Tkinter.
