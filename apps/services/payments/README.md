# Microservicio Payments (puerto 5005)

Registra intentos de pago, los confirma (aprueba/rechaza), gestiona
reembolsos y coordina el estado financiero de `pedidos`, con transacciones
PostgreSQL.

| Servicio | Puerto |
| -------- | ------ |
| Books / SOAP | 5000 |
| Login | 5001 |
| Users | 5002 |
| Authors | 5003 |
| Orders | 5004 |
| **Payments** | **5005** |

No crea pedidos ni líneas, no descuenta stock al comprar (eso es Orders), no
crea usuarios ni libros, no autentica ni emite JWT.

**Los pagos son historial financiero: no hay DELETE, PUT ni PATCH (405).**
Los cambios de estado solo ocurren mediante `approve`, `reject` y `refund`.

## Esquema real (migración 07)

```sql
pagos (pago_id BIGSERIAL PK,
       pedido_id BIGINT NOT NULL -> pedidos ON DELETE RESTRICT        -- fk_pagos_pedido
       monto NUMERIC(12,2) NOT NULL CHECK (monto > 0)                  -- ck_pagos_monto
       metodo_pago VARCHAR(30) CHECK IN ('credit_card','debit_card','bank_transfer','cash')
       estado VARCHAR(20) DEFAULT 'pending' CHECK IN ('pending','approved','rejected','refunded')
       referencia VARCHAR(100) NOT NULL UNIQUE                         -- uq_pagos_referencia
       fecha_pago TIMESTAMPTZ,  fecha_creacion / fecha_actualizacion TIMESTAMPTZ DEFAULT now(),
       CHECK ((estado IN ('approved','refunded') AND fecha_pago IS NOT NULL)
              OR estado IN ('pending','rejected')))                    -- ck_pagos_fecha_pago
UNIQUE INDEX ux_pagos_un_aprobado_por_pedido ON pagos (pedido_id) WHERE estado = 'approved'
```

- Índices: `ix_pagos_pedido_id`, `ix_pagos_estado`. Trigger:
  `trg_pagos_set_fecha_actualizacion`.
- `pagos` no guarda `usuario_id`: el dueño es `pedidos.usuario_id`.
- Varios intentos por pedido, **a lo sumo uno aprobado**.
- No hay pagos parciales: el monto es el total del pedido.
- El reembolso **sí** está representado (`refunded`, "de un pago antes aprobado").

Estados de pedido (`ck_pedidos_estado`): `pending`, `paid`, `completed`,
`cancelled`. Payments ejecuta exactamente las dos transiciones que Orders le
delega (`apps/services/orders/services/status.py`): `pending → paid` y
`paid → cancelled`. Una prueba comprueba que ambos módulos siguen alineados.

## Flujo

Se eligió "el usuario registra un intento, el ADMIN lo confirma", porque es
lo que modela el esquema (`pending` = "registrado, sin confirmar"). No hay
pasarela ni aleatoriedad: la confirmación es una acción administrativa
explícita (simulación académica de la conciliación del pago).

| Paso | Endpoint | Quién | `pagos.estado` | `pedidos.estado` | Stock |
| ---- | -------- | ----- | -------------- | ---------------- | ----- |
| 1. Registrar intento | `POST /payments` | dueño del pedido (o ADMIN) | → `pending` | sin cambio (`pending`) | — |
| 2a. Aprobar | `POST /payments/<id>/approve` | ADMIN | `pending → approved` (+ `fecha_pago`) | `pending → paid` | — |
| 2b. Rechazar | `POST /payments/<id>/reject` | ADMIN | `pending → rejected` | sin cambio | — |
| 3. Reembolsar | `POST /payments/<id>/refund` | ADMIN | `approved → refunded` | `paid → cancelled` | se devuelve |

- **Monto**: siempre `pedidos.total` (calculado por el trigger de la 07),
  copiado al registrar el intento. El cliente no puede enviarlo. Al aprobar
  se verifica que siga coincidiendo (`PAYMENT_AMOUNT_MISMATCH` si no).
  Cambios posteriores de precios no alteran el monto guardado.
- **Rechazo**: el intento se conserva, el pedido sigue `pending`, el stock
  no cambia y se puede registrar un nuevo intento.
- **Varios intentos**: permitidos (el esquema lo permite). Cuando uno se
  aprueba, los demás `pending` ya no pueden aprobarse (409
  `ORDER_NOT_PAYABLE`) y pueden rechazarse.
- **Referencia**: opcional (p. ej. número de transferencia); si no se envía,
  se genera `PAY-<uuid>`. Es única: repetirla → 409
  `PAYMENT_REFERENCE_EXISTS` (evita registrar dos veces la misma operación).
- Un pedido con total 0 no es pagable (`ck_pagos_monto` exige monto > 0).
- **Interacción con Orders**: si Orders cancela un pedido `pending`, sus
  intentos quedan `pending` y ya no pueden aprobarse; el ADMIN puede
  rechazarlos.

## Atomicidad y locking

Cada escritura es **una** transacción, controlada por el servicio (los
repositorios nunca hacen commit). Orden de bloqueo, siempre igual:

```text
1. pedidos  SELECT ... FOR UPDATE          (el mismo lock que toma Orders para cancelar)
2. pagos    SELECT ... FOR UPDATE
3. libros   SELECT ... ORDER BY isbn FOR UPDATE   (solo reembolso, mismo orden que Orders)
```

Todas las validaciones se hacen **después** de tomar los locks, sobre el
estado actual:

```text
Aprobar:     BEGIN · lock pedido · lock pago · pago pending · pedido pending ·
             sin otro aprobado · monto = total · pago approved + fecha_pago · pedido paid · COMMIT
Reembolsar:  BEGIN · lock pedido · lock pago · pago approved · pedido paid ·
             lock libros (ISBN) · stock += cantidades de pedido_detalle ·
             pago refunded · pedido cancelled · COMMIT · invalidar caché Books
```

Cualquier fallo → **ROLLBACK** completo. No puede quedar un pago aprobado
con el pedido `pending`, un pedido `paid` sin pago aprobado ni un reembolso
sin cancelar el pedido. Los constraints son la última barrera
(`ux_pagos_un_aprobado_por_pedido` → 409 `PAYMENT_ALREADY_APPROVED`,
`uq_pagos_referencia` → 409 `PAYMENT_REFERENCE_EXISTS`). Un deadlock o
fallo de serialización → 409 `TRANSACTION_CONFLICT`, también con rollback.

### Concurrencia

- **Dos aprobaciones del mismo pedido**: la segunda espera el lock, ve
  `paid` → 409 `ORDER_NOT_PAYABLE` (o `PAYMENT_ALREADY_APPROVED` si es el
  mismo pago). Nunca hay dos aprobados.
- **Pago contra cancelación de Orders**: ambos bloquean la misma fila de
  `pedidos`. Si gana el pago, el pedido queda `paid` y la cancelación de Orders
  (que exige `pending`) no procede. Si gana la cancelación, el pedido queda
  `cancelled` con el stock devuelto una vez, y la aprobación responde 409
  `ORDER_NOT_PAYABLE`.
- **Dos reembolsos**: el segundo ve `refunded` → 409
  `PAYMENT_ALREADY_REFUNDED`; el stock se devuelve una sola vez.

## Ownership

El dueño de un pago es `pedidos.usuario_id`, comparado con `claims.user_id`;
nunca se acepta `usuario_id` del cliente (ni en el body ni en query). Un
USER que pide un pago o pedido ajeno recibe **404**, igual que si no
existiera (misma convención que Orders). ADMIN ve y opera todo.

## Endpoints y permisos

| Método | Ruta | Permiso |
| ------ | ---- | ------- |
| GET | `/health` | público |
| GET | `/payments?limit&offset&pedido_id&estado&metodo_pago&desde&hasta` | ADMIN |
| GET | `/payments/me` (mismos filtros) | autenticado, solo pagos de sus pedidos |
| GET | `/payments/<pago_id>` | dueño o ADMIN |
| GET | `/orders/<pedido_id>/payments` | dueño o ADMIN |
| POST | `/payments` | autenticado, sobre sus pedidos (ADMIN: cualquiera) |
| POST | `/payments/<pago_id>/approve` | ADMIN |
| POST | `/payments/<pago_id>/reject` | ADMIN |
| POST | `/payments/<pago_id>/refund` | ADMIN |

`desde` (incluido) y `hasta` (excluido) filtran `fecha_creacion` (ISO 8601;
una fecha sola en `hasta` cubre todo el día). `limit` 1–200, `offset` ≥ 0.

### Bodies

`POST /payments`:

```json
{"pedido_id": 12, "metodo_pago": "bank_transfer", "referencia": "TRX-2026-0001"}
```

- `pedido_id` (entero), `metodo_pago` (uno de los 4 del CHECK, sin
  distinguir mayúsculas), `referencia` opcional (≤ 100; letras, dígitos y
  `. _ : / -`).
- **400 `FIELDS_NOT_ALLOWED`**: `monto`, `estado`/`status`, `usuario_id`,
  `pago_id`, `fecha_pago`, `fecha_creacion`, `fecha_actualizacion`. Otros
  campos → **400 `UNKNOWN_FIELDS`**.

`approve` / `reject` / `refund`: sin body (o `{}`).

Respuestas: un pago es `{pago_id, pedido_id, usuario_id, monto, metodo_pago,
estado, referencia, fecha_pago, fecha_creacion, fecha_actualizacion}`
(importes como string decimal). Las acciones devuelven
`{"payment": {...}, "order": {"pedido_id", "estado", "total"}}` y el
reembolso, además, `"restocked": [{"isbn", "cantidad"}]`.

## Redis

Payments no tiene caché propia. Redis se usa para:

1. revocación de JWT (vía `library_shared`). **Crítico**: si Redis no
   responde, todos los endpoints protegidos devuelven 503;
2. tras un reembolso (devuelve stock), borrar `books:<isbn>` y
   `books:list:*` de la caché de Books, **después** del commit (mismo
   módulo que Orders). Si Redis falla en ese momento **no se deshace** el
   reembolso confirmado; la entrada obsoleta caduca con el TTL de Books
   (60 s) y se registra un warning.

## Health

`healthy` (200) si PostgreSQL y Redis responden; si no, `unavailable`
(503), porque todos los endpoints necesitan ambos. No muestra credenciales.

## Errores

`{"success": false, "code": "...", "message": "...", "details": {...}?}`

| HTTP | `code` |
| ---- | ------ |
| 400 | `INVALID_INPUT`, `UNKNOWN_FIELDS`, `FIELDS_NOT_ALLOWED` |
| 401 | `MISSING_TOKEN`, `INVALID_AUTHORIZATION_HEADER`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `TOKEN_REVOKED` |
| 403 | `FORBIDDEN`, `USER_INACTIVE` |
| 404 | `PAYMENT_NOT_FOUND`, `ORDER_NOT_FOUND`, `NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` (DELETE/PUT/PATCH) |
| 409 | `ORDER_NOT_PAYABLE`, `PAYMENT_ALREADY_APPROVED`, `PAYMENT_ALREADY_REFUNDED`, `INVALID_PAYMENT_TRANSITION`, `REFUND_NOT_ALLOWED`, `PAYMENT_AMOUNT_MISMATCH`, `PAYMENT_REFERENCE_EXISTS`, `TRANSACTION_CONFLICT` |
| 503 | `AUTH_BACKEND_UNAVAILABLE`, `DATABASE_UNAVAILABLE` |
| 500 | `INTERNAL_ERROR` |

## PostgreSQL y permisos

`library_user` ya tiene `SELECT, INSERT, UPDATE, DELETE` sobre `pagos`,
`pedidos`, `pedido_detalle`, `libros` y `usuarios`, y uso de
`pagos_pago_id_seq` (00 + migración 07). **Sin grants nuevos ni cambios de
esquema.** Payments nunca ejecuta DELETE.

## Variables, instalación y pruebas

Ver `.env.example` (puerto `5005`; `JWT_SECRET_KEY` y `REDIS_URL` iguales
que en el resto de servicios).

```powershell
# Windows, desde apps\services\payments
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env      # completar
python -m pytest
python app.py                    # http://127.0.0.1:5005
```

```bash
# CentOS 10 (despliegue conjunto), desde apps/services/payments
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
python app.py    # 127.0.0.1:5005 detrás del reverse proxy HTTPS
```

Integración real (`tests/test_integration_postgres.py`): solo si existe
`PAYMENTS_IT_DB_NAME`, que **debe terminar en `_test`**, con el esquema
completo (01, 02, 06, 04, 05, `login_microservice.sql`, 07). Incluye
concurrencia con hilos y conexiones reales (dos aprobaciones, aprobación
contra cancelación en ambos órdenes y reembolsos dobles).

```powershell
$env:PAYMENTS_IT_DB_PORT="5432"; $env:PAYMENTS_IT_DB_NAME="library_payments_test"
$env:PAYMENTS_IT_DB_USER="library_user"; $env:PAYMENTS_IT_DB_PASSWORD="<password local>"
python -m pytest
```

## Ejemplos (curl)

`$USER` / `$ADMIN`: access tokens de Login. En PowerShell usar `curl.exe`.

```bash
# 1. El usuario registra el intento de pago de su pedido 12 -> 201 (estado pending, monto = total)
curl -s -X POST http://127.0.0.1:5005/payments -H "Authorization: Bearer $USER" \
  -H "Content-Type: application/json" -d '{"pedido_id":12,"metodo_pago":"bank_transfer","referencia":"TRX-2026-0001"}'

# 2a. ADMIN aprueba -> pago approved, pedido paid
curl -s -X POST -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5005/payments/7/approve

# 2b. ADMIN rechaza -> pago rejected, pedido sigue pending
curl -s -X POST -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5005/payments/8/reject

# 3. ADMIN reembolsa -> pago refunded, pedido cancelled, stock devuelto
curl -s -X POST -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5005/payments/7/refund

# Consultas
curl -s -H "Authorization: Bearer $USER" http://127.0.0.1:5005/payments/me
curl -s -H "Authorization: Bearer $USER" http://127.0.0.1:5005/orders/12/payments
curl -s -H "Authorization: Bearer $ADMIN" "http://127.0.0.1:5005/payments?estado=approved&desde=2026-10-01"

# Errores típicos
curl -s -X POST -H "Authorization: Bearer $USER" http://127.0.0.1:5005/payments/7/approve      # 403
curl -s -X POST -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5005/payments/7/refund      # 409 PAYMENT_ALREADY_REFUNDED
curl -s -X POST http://127.0.0.1:5005/payments -H "Authorization: Bearer $USER" \
  -H "Content-Type: application/json" -d '{"pedido_id":12,"metodo_pago":"cash","monto":"0.01"}'  # 400 FIELDS_NOT_ALLOWED
curl -s -X DELETE -H "Authorization: Bearer $ADMIN" http://127.0.0.1:5005/payments/7          # 405
curl -s http://127.0.0.1:5005/health                                                          # 503 si Redis cae
```
