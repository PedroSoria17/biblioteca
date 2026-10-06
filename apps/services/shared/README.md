# library_shared — infraestructura común JWT / Redis / CORS

Paquete Python reutilizable por los microservicios Flask del proyecto
Library: `login`, `soap` (= Books), `users`, `authors`, `orders`, `payments`.

En esta fase **solo existe la infraestructura**; ningún servicio la importa
todavía. La integración se hará servicio por servicio en las fases
siguientes.

## Por qué un paquete instalable (y no un `sys.path` hack)

Cada servicio se ejecuta con `python app.py` desde su propia carpeta y usa
imports de primer nivel (`from config import ...`, `from db.connection
import ...`, `from utils...`, `from soap...`). Por eso:

- el código compartido usa un nombre de paquete **único**
  (`library_shared`) que no choca con `config`, `db`, `utils`, `catalog` o
  `soap` de cada servicio;
- se instala en el venv de cada servicio con `pip install -e ../shared`, de
  modo que el import funciona sin importar el directorio de trabajo (VS Code,
  terminal, pytest o systemd en CentOS), sin copiar código ni manipular
  `sys.path`.

## Instalación (en el venv de un servicio)

```powershell
# Windows, desde apps/services/<servicio>/ con su .venv activado
pip install -e ..\shared
```

```bash
# Linux/CentOS, desde apps/services/<servicio>/ con su .venv activado
pip install -e ../shared
```

Dependencias nuevas (declaradas en `pyproject.toml`):

| Paquete      | Uso                                          |
| ------------ | -------------------------------------------- |
| `PyJWT`      | firmar/validar JWT HS256                     |
| `redis`      | cliente Redis (sesiones, refresh, revocación, caché) |
| `flask-cors` | CORS con orígenes explícitos                 |
| `Flask`      | mismo rango que ya usan login y soap (`>=3.0,<4.0`) |

## Módulos

| Módulo            | Responsabilidad |
| ----------------- | --------------- |
| `settings.py`     | Lee y valida variables de entorno (`JWT_*`, `REDIS_*`, `CORS_ALLOWED_ORIGINS`, `BOOKS_CACHE_TTL_SECONDS`). Falla al arrancar si falta algo crítico. `repr()` nunca muestra secretos. |
| `errors.py`       | `AuthError` (401/403/503), `RedisUnavailableError`, `ConfigurationError`. |
| `jwt_tokens.py`   | Crear access/refresh token, `jti`, validar firma, **HS256 fijo**, expiración, claims obligatorios y tipo de token. |
| `redis_client.py` | `RedisGateway`: operaciones **opcionales** `cache_*` (nunca lanzan) y **críticas** `get/set/exists/delete/pop` (lanzan `RedisUnavailableError`). Timeouts, health check, métricas, TTL obligatorio. `cache_invalidate(keys, patterns)` devuelve `False` si falló (para marcar una ventana de caché obsoleta). `cache_cooldown_seconds` (opt-in, 0 por defecto): tras un fallo de `cache_get`/`cache_set`, la caché se omite ese tiempo para no pagar el connect timeout en cada petición; nunca afecta a operaciones críticas ni a invalidaciones. |
| `token_store.py`  | Revocación `jwt:revoked:<jti>`, refresh tokens `auth:refresh:<jti>` (consumo atómico para rotación), sesiones `auth:session:<id>`, y `authenticate_access_token` (validación completa + revocación). |
| `flask_auth.py`   | `init_auth`, `require_auth`, `require_roles`, lectura de `Authorization: Bearer`, manejo 401/403 con renderer propio de cada servicio (XML/JSON). |
| `cache.py`        | `cached_json`: lectura con caché y fallback a PostgreSQL. |
| `keys.py`         | Convención única de claves Redis (`books:<isbn>`, `books:list:<filtros-normalizados>`, ...). |
| `cors.py`         | `init_cors` con orígenes explícitos. |
| `roles.py`        | `ROLE_USER = 1`, `ROLE_ADMIN = 2` (tabla `roles`). |
| `redaction.py`    | `redact_url`, `mask_secret` para logs seguros. |
| `metrics.py`      | Contadores en memoria (cache hit/miss, errores Redis). |

## Reglas de seguridad implementadas

- **JWT**: siempre HS256 (se valida el header `alg` y se fija
  `algorithms=["HS256"]`; `none`, HS384, HS512 se rechazan). Claims
  obligatorios: `user_id`, `role_id`, `jti`, `iat`, `exp`, `type`
  (`access`/`refresh`), opcional `sid` (id de sesión). Un refresh token
  nunca se acepta como access token.
- **Access token**: 20 minutos por defecto (`JWT_ACCESS_TTL_MINUTES`).
  Refresh: 7 días por defecto (`JWT_REFRESH_TTL_DAYS`), siempre mayor que el
  access.
- **401 vs 403**: 401 = header ausente/malformado, token inválido, expirado,
  revocado, firma o claims incorrectos. 403 = autenticado pero sin el rol.
  `require_roles` autentica primero, así que nunca devuelve 403 a quien no
  está autenticado.
- **Redis crítico vs opcional**:
  - revocación, sesiones y refresh tokens → si Redis falla, la operación
    protegida **se rechaza con 503** (`AUTH_BACKEND_UNAVAILABLE`). Nunca se
    concede acceso porque Redis no respondió. Se eligió 503 y no 401 porque
    el token puede ser válido: el cliente no debe descartarlo.
  - caché de catálogo → si Redis falla se registra un warning (sin host ni
    contraseña) y se consulta PostgreSQL directamente.
- **TTL explícitos**: toda escritura en Redis exige TTL > 0. La clave
  `jwt:revoked:<jti>` expira exactamente cuando el JWT habría expirado.
- **Logs**: nunca se registran contraseñas, JWT completos, refresh tokens,
  `JWT_SECRET_KEY` ni `REDIS_URL` con contraseña (se usa `redact_url` /
  `mask_secret`; los errores de Redis solo registran el tipo de excepción).

## Variables de entorno

| Variable | Default | Notas |
| -------- | ------- | ----- |
| `APP_ENV` (o `FLASK_ENV`) | `development` | En `production` se prohíbe `*` en CORS. |
| `JWT_SECRET_KEY` | — (obligatoria) | ≥ 32 caracteres. Igual en todos los servicios. |
| `JWT_ACCESS_TTL_MINUTES` | `20` | |
| `JWT_REFRESH_TTL_DAYS` | `7` | Debe dar más vida que el access. |
| `REDIS_URL` | — (obligatoria si se usa Redis) | `redis://:password@host:6379/0` |
| `REDIS_CONNECT_TIMEOUT_SECONDS` | `2` | |
| `REDIS_SOCKET_TIMEOUT_SECONDS` | `2` | |
| `REDIS_HEALTH_CHECK_INTERVAL_SECONDS` | `30` | |
| `BOOKS_CACHE_TTL_SECONDS` | `60` | |
| `CORS_ALLOWED_ORIGINS` | vacío | Lista separada por comas de orígenes exactos. |

## Ejemplo de integración (fases siguientes)

```python
from library_shared.flask_auth import init_auth, require_roles
from library_shared.redis_client import RedisGateway
from library_shared.roles import ROLE_ADMIN
from library_shared.settings import load_jwt_settings, load_redis_settings

gateway = RedisGateway.from_settings(load_redis_settings())
init_auth(app, load_jwt_settings(), gateway, error_renderer=render_auth_error_xml_json)

@app.delete("/books/<isbn>")
@require_roles(ROLE_ADMIN)
def delete_book(isbn): ...
```

## HTTPS

Los microservicios Flask **no** gestionan certificados TLS. En la VM de
CentOS 10, HTTPS debe terminar en un reverse proxy (NGINX o Apache), que
reenvía a los servicios escuchando en `127.0.0.1`. Al integrar, cada
servicio deberá confiar en `X-Forwarded-Proto` solo desde ese proxy
(`werkzeug.middleware.proxy_fix.ProxyFix` con `x_proto=1`).

## Pruebas

```powershell
cd apps\services\shared
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[test]"
python -m pytest
```

Las pruebas no necesitan Redis ni PostgreSQL: Redis se sustituye por un
fake en memoria (`tests/conftest.py`) y por un cliente "roto" que simula
la caída; además una prueba usa el cliente real de redis-py contra un puerto
cerrado para comprobar timeouts y el manejo de errores.
