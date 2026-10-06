# Microservicio Orders (puerto 5004)

Crea y consulta pedidos (`pedidos`, `pedido_detalle`), administra su estado
y reserva/devuelve stock de `libros` con transacciones PostgreSQL.

| Servicio | Puerto |
| -------- | ------ |
| Books / SOAP | 5000 |
| Login | 5001 |
| Users | 5002 |
| Authors | 5003 |
| **Orders** | **5004** |
| Payments | 5005 (fase 7) |

**No** procesa pagos (no escribe `pagos`), no crea usuarios ni libros, no
toca autores, no emite JWT ni maneja sesiones.

**Orders does not physically delete orders; cancellation is represented by
status.** No existe `DELETE /orders/<id>` (responde 405): los pedidos son
historial comercial, `pedido_detalle` guarda el precio histórico y `pagos`
(RESTRICT) dependerá de ellos.

## Modelo real (migración 07)

```sql
pedidos (pedido_id BIGSERIAL PK,
         usuario_id BIGINT NOT NULL  -> usuarios ON DELETE RESTRICT (fk_pedidos_usuario),
         estado VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (estado IN ('pending','paid','completed','cancelled')),  -- ck_pedidos_estado
         total NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (total >= 0),             -- ck_pedidos_total
         fecha_creacion, fecha_actualizacion TIMESTAMPTZ DEFAULT now())

pedido_detalle (pedido_id -> pedidos ON DELETE CASCADE, isbn -> libros ON DELETE RESTRICT,
                cantidad INTEGER CHECK (> 0), precio_unitario NUMERIC(10,2) CHECK (>= 0),
                subtotal NUMERIC(12,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED,
                PRIMARY KEY (pedido_id, isbn))

libros.stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)   -- libros_stock_check
```

Triggers: `trg_pedido_detalle_recalcular_total` (AFTER INSERT/UPDATE/DELETE
en `pedido_detalle`: recalcula `pedidos.total`), y
`trg_*_set_fecha_actualizacion` en `pedidos` y `libros`. No hay triggers de
stock. Índices: `ix_pedidos_usuario_id`, `ix_pedidos_estado`,
`ix_pedido_detalle_isbn`.

## Endpoints y permisos

| Método | Ruta | Permiso |
| ------ | ---- | ------- |
| GET | `/health` | público |
| GET | `/orders?limit&offset&estado&usuario_id&desde&hasta` | ADMIN |
| GET | `/orders/me?limit&offset&estado` | autenticado (solo los propios) |
| GET | `/orders/<pedido_id>` | dueño o ADMIN |
| GET | `/orders/<pedido_id>/items` | dueño o ADMIN |
| POST | `/orders` | autenticado (USER o ADMIN; siempre para sí mismo) |
| PATCH | `/orders/<pedido_id>/status` | ADMIN |

Todos (salvo `/health`) exigen `Authorization: Bearer <access_token>`,
validado por `library_shared` (HS256, exp, `type=access`, claims y
revocación en Redis).

**Ownership**: el dueño de un pedido sale **siempre** de `claims.user_id`.
`POST /orders` no acepta `usuario_id` (400) y `/orders/me` rechaza
`?usuario_id=`. Un USER que pide un pedido ajeno recibe **404
`ORDER_NOT_FOUND`**, idéntico a uno inexistente, para no revelar qué ids
existen. No hay endpoint para que ADMIN compre a nombre de otro.

Filtros de `GET /orders`: `estado` (uno de los 4), `usuario_id`, `desde`
(incluido) y `hasta` (excluido) sobre `fecha_creacion`, en ISO 8601; una
fecha sola en `hasta` cubre todo ese día; sin zona horaria = UTC. Orden:
más recientes primero. `limit` 1–200 (50), `offset` ≥ 0.

## POST /orders

```json
{"items": [{"isbn": "9781000000000", "cantidad": 2},
           {"isbn": "9781000000017", "cantidad": 1}]}
```

- Solo `items`, y en cada item solo `isbn` y `cantidad` (nombres del esquema).
- `cantidad`: entero 1–10000 (no `2.0`, `"2"`, `true`). Máximo 100 entradas.
- `isbn`: mismo formato que el CHECK de `libros`; se normaliza como Books
  (`strip()` + mayúsculas).
- **ISBN repetido → se consolida** en una sola línea (2 + 3 = 5), porque la
  PK de `pedido_detalle` es `(pedido_id, isbn)`.
- Rechazados con **400 `FIELDS_NOT_ALLOWED`**: `pedido_id`, `usuario_id`,
  `estado`/`status`, `total`, `fecha_creacion`, `fecha_actualizacion`, y en
  los items `precio_unitario`, `precio`, `subtotal`, `pedido_id`. Otros
  campos → **400 `UNKNOWN_FIELDS`**.

Respuesta 201: el pedido (`pedido_id`, `usuario_id`, `estado` = `pending`,
`total`, `items_count`, fechas) más `items` con `isbn`, `titulo`,
`cantidad`, `precio_unitario`, `subtotal`. Importes como string decimal
(misma convención que Books).

## Atomicidad, stock y concurrencia

Todo el pedido es **una** transacción, controlada por el servicio (los
repositorios nunca hacen commit):

```text
BEGIN
  usuarios: existe y activo           SELECT ... FOR KEY SHARE    -> 403 USER_INACTIVE
  libros: bloquear los ISBN pedidos   SELECT ... ORDER BY isbn FOR UPDATE
  validar existencia                  -> 404 BOOK_NOT_FOUND (details.isbns)
  validar stock                       -> 409 INSUFFICIENT_STOCK (details.items)
  INSERT pedidos (usuario_id)         estado/total/fechas = DEFAULT
  INSERT pedido_detalle por línea     precio_unitario = libros.precio (congelado)
  UPDATE libros SET stock = stock - cantidad
  releer pedido                       total ya calculado por el trigger
COMMIT
-> invalidar caché de Books (books:<isbn>, books:list:*)
```

Cualquier excepción provoca **ROLLBACK completo**: nunca queda un pedido sin
líneas, líneas sin pedido ni stock descontado sin pedido.

- **Bloqueo**: `FOR UPDATE` sobre las filas de `libros`. Un segundo comprador
  del mismo libro espera hasta el commit del primero y después lee el stock
  ya descontado. Con stock 1 y dos compras simultáneas: una 201 y otra 409.
- **Orden de bloqueo determinista (por ISBN)**: todas las transacciones
  bloquean los libros en el mismo orden, así que dos pedidos `[A, B]` y
  `[B, A]` no pueden bloquearse mutuamente (deadlock). La cancelación usa el
  mismo orden. Si aun así PostgreSQL detectara un deadlock o un fallo de
  serialización → **409 `TRANSACTION_CONFLICT`** (con rollback; se puede reintentar).
- **Stock**: solo cambia tras validar existencia, cantidad y stock. Stock
  exactamente igual a la cantidad → se permite y queda en 0. El CHECK
  `stock >= 0` es la última barrera (si salta → 409 `INSUFFICIENT_STOCK`).
- **Usuario inactivo**: aunque el access token siga vigente (hasta 20 min),
  se comprueba `usuarios.activo` en la misma transacción.
- **Reserva**: el stock se descuenta al crear el pedido (`pending`) y solo se
  devuelve al cancelarlo. Un pedido `pending` que nunca se paga mantiene su
  reserva hasta que ADMIN lo cancele (expiración automática: pendiente).

## Precio y total

- `pedido_detalle.precio_unitario` copia `libros.precio` dentro de la misma
  transacción, con la fila bloqueada. Cambiar después el precio del libro no
  altera pedidos ya creados.
- `subtotal` es columna generada y `pedidos.total` lo mantiene el trigger de
  la migración 07. Orders **no** calcula el total en Python: lo relee de
  PostgreSQL. El cliente nunca envía precios ni totales.

## Estados

Estados reales (`ck_pedidos_estado`), con el significado documentado en la
migración 07:

| Estado | Significado |
| ------ | ----------- |
| `pending` | creado, esperando pago (DEFAULT, único editable) |
| `paid` | existe un pago **aprobado** por el total |
| `completed` | entregado / cerrado (final) |
| `cancelled` | cancelado (final) |

`PATCH /orders/<id>/status` (ADMIN), body `{"estado": "cancelled"}`:

| Transición | Quién | Efecto |
| ---------- | ----- | ------ |
| `pending → cancelled` | Orders | devuelve exactamente las cantidades del detalle al stock, en la misma transacción |
| `paid → completed` | Orders | sin cambios de stock |
| `pending → paid` | **Payments (fase 7)** | Orders responde 409: marcar pagado sin pago aprobado rompería el significado de `paid` |
| `paid → cancelled` | **Payments (fase 7)** | requiere reembolso (`pagos.estado = 'refunded'`); Orders responde 409 |
| cualquier otra | — | 409 `INVALID_STATUS_TRANSITION` (`details.from/to`) |

La tabla vive en `services/status.py` para que Payments la reutilice.

**Cancelación idempotente**: la fila del pedido se bloquea
(`SELECT ... FOR UPDATE`) antes de validar. Una segunda cancelación (también
concurrente) espera, ve `cancelled` y recibe **409
`ORDER_ALREADY_CANCELLED`**: el stock se devuelve una sola vez. El pedido y
sus líneas se conservan.

Contrato para Payments: bloquear la fila de `pedidos` (`FOR UPDATE`) y
comprobar `estado` antes de aprobar o reembolsar, para no competir con una
cancelación.

## Redis

Orders no tiene caché propia. Redis se usa para:

1. revocación de JWT (vía `library_shared`). **Crítico**: si Redis no
   responde, **todos** los endpoints protegidos devuelven 503;
2. tras un commit que cambia stock (crear o cancelar), borrar las entradas de
   la caché de Books (`books:<isbn>`, `books:list:*`), porque incluyen
   `stock`. Es una operación **opcional**: si falla, el pedido sigue
   confirmado y la entrada obsoleta expira con el TTL de Books (60 s).

## Health

| PostgreSQL | Redis | `status` | HTTP |
| ---------- | ----- | -------- | ---- |
| conectado | conectado | `healthy` | 200 |
| cualquiera caído | | `unavailable` | 503 |

No hay estado `degraded`: todos los endpoints necesitan token (Redis) y
PostgreSQL. No se muestran credenciales.

## Errores

`{"success": false, "code": "...", "message": "...", "details": {...}?}`

| HTTP | `code` |
| ---- | ------ |
| 400 | `INVALID_INPUT`, `UNKNOWN_FIELDS`, `FIELDS_NOT_ALLOWED` |
| 401 | `MISSING_TOKEN`, `INVALID_AUTHORIZATION_HEADER`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `TOKEN_REVOKED` |
| 403 | `FORBIDDEN` (rol), `USER_INACTIVE` |
| 404 | `ORDER_NOT_FOUND`, `BOOK_NOT_FOUND`, `NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` (p. ej. DELETE) |
| 409 | `INSUFFICIENT_STOCK`, `INVALID_STATUS_TRANSITION`, `ORDER_ALREADY_CANCELLED`, `TRANSACTION_CONFLICT` |
| 503 | `AUTH_BACKEND_UNAVAILABLE`, `DATABASE_UNAVAILABLE` |
| 500 | `INTERNAL_ERROR` |

## PostgreSQL y permisos

`library_user` ya tiene `SELECT, INSERT, UPDATE, DELETE` sobre `pedidos`,
`pedido_detalle` (migración 07), `libros` y `usuarios`, y uso de
`pedidos_pedido_id_seq`. **No se necesitan grants nuevos** ni cambios de
esquema. Orders nunca ejecuta DELETE.

## Variables de entorno

Ver `.env.example`. Obligatorias: `DB_HOST`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `JWT_SECRET_KEY` (≥ 32, **igual** en todos los servicios) y
`REDIS_URL` (el mismo Redis). Opcionales: `FLASK_HOST` (`127.0.0.1`),
`FLASK_PORT` (`5004`), `FLASK_DEBUG`, `APP_ENV`, `DB_PORT`,
`REDIS_*_TIMEOUT_SECONDS`, `REDIS_HEALTH_CHECK_INTERVAL_SECONDS`,
`CORS_ALLOWED_ORIGINS` (sin `*` en producción).

## Instalación, ejecución y pruebas

```powershell
# Windows, desde apps\services\orders
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env      # completar
python -m pytest
python app.py                    # http://127.0.0.1:5004
```

```bash
# CentOS 10 (despliegue conjunto), desde apps/services/orders
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
python app.py    # 127.0.0.1:5004 detrás del reverse proxy HTTPS
```

Integración real (`tests/test_integration_postgres.py`): solo si existe
`ORDERS_IT_DB_NAME`, que **debe terminar en `_test`**. Necesita una base
desechable con 01, 02, 06, 04, 05, `login_microservice.sql` y 07. Incluye
pruebas concurrentes con hilos y conexiones reales (último ejemplar,
pedidos multi-libro en orden inverso, cancelación doble).

```powershell
$env:ORDERS_IT_DB_PORT="5432"; $env:ORDERS_IT_DB_NAME="library_orders_test"
$env:ORDERS_IT_DB_USER="library_user"; $env:ORDERS_IT_DB_PASSWORD="<password local>"
python -m pytest
```

## Ejemplos (curl)

`$USER` / `$ADMIN`: access tokens de Login. En PowerShell usar `curl.exe`.

```bash
# Crear pedido (USER) -> 201
curl -s -X POST http://127.0.0.1:5004/orders -H "Authorization: Bearer $USER" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"isbn":"9781000000000","cantidad":2},{"isbn":"9781000000017","cantidad":1}]}'

# Mis pedidos / un pedido / sus líneas
curl -s -H "Authorization: Bearer $USER" "http://127.0.0.1:5004/orders/me?estado=pending"
curl -s -H "Authorization: Bearer $USER" http://127.0.0.1:5004/orders/1
curl -s -H "Authorization: Bearer $USER" http://127.0.0.1:5004/orders/1/items

# Todos los pedidos (ADMIN) con filtros
curl -s -H "Authorization: Bearer $ADMIN" "http://127.0.0.1:5004/orders?estado=pending&desde=2026-10-01&hasta=2026-10-31"

# USER listando todos -> 403
curl -s -H "Authorization: Bearer $USER" http://127.0.0.1:5004/orders

# Cancelar (ADMIN) -> 200 y stock devuelto; repetir -> 409 ORDER_ALREADY_CANCELLED
curl -s -X PATCH http://127.0.0.1:5004/orders/1/status -H "Authorization: Bearer $ADMIN" \
  -H "Content-Type: application/json" -d '{"estado":"cancelled"}'

# Stock insuficiente -> 409 INSUFFICIENT_STOCK con details.items
curl -s -X POST http://127.0.0.1:5004/orders -H "Authorization: Bearer $USER" \
  -H "Content-Type: application/json" -d '{"items":[{"isbn":"9781000000000","cantidad":9999}]}'

# Precio enviado por el cliente -> 400 FIELDS_NOT_ALLOWED
curl -s -X POST http://127.0.0.1:5004/orders -H "Authorization: Bearer $USER" \
  -H "Content-Type: application/json" -d '{"items":[{"isbn":"9781000000000","cantidad":1,"precio_unitario":"0.01"}]}'

# Redis caído -> 503 AUTH_BACKEND_UNAVAILABLE; /health -> 503
curl -s http://127.0.0.1:5004/health
```
