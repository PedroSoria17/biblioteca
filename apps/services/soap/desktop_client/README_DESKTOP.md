# Cliente de escritorio Library (Tkinter)

Cliente de escritorio de los seis microservicios. Solo usa la biblioteca
estándar de Python (`tkinter`, `urllib`, `json`, `threading`): **no requiere
paquetes adicionales** y **nunca** se conecta a PostgreSQL ni a Redis; todo
pasa por HTTP.

```text
Tkinter ──► Books/SOAP :5000 · Login :5001 · Users :5002 · Authors :5003 · Orders :5004 · Payments :5005
```

Dos modos de ejecución, desde esta carpeta:

```powershell
python main.py          # cliente completo: login, roles, catálogo, pedidos, pagos...
python desktop_app.py   # clasificador SOAP original (Ejercicio 03), igual que antes
```

El clasificador SOAP también es una pestaña ("Clasificador SOAP") del
cliente completo. Sigue usando únicamente `POST /soap`
(`soap_client.py`, sin cambios).

## Configuración

Las URLs están **solo** en `client_config.py`. Valores por defecto para
desarrollo local: `http://127.0.0.1:5000` … `:5005`. Para apuntar a otra
máquina (p. ej. la VM) basta con variables de entorno o un archivo `.env` en
esta carpeta (ignorado por Git; ver `.env.example`):

| Variable | Default |
| -------- | ------- |
| `BOOKS_BASE_URL` | `http://127.0.0.1:5000` (SOAP = `<BOOKS_BASE_URL>/soap`) |
| `LOGIN_BASE_URL` | `http://127.0.0.1:5001` |
| `USERS_BASE_URL` | `http://127.0.0.1:5002` |
| `AUTHORS_BASE_URL` | `http://127.0.0.1:5003` |
| `ORDERS_BASE_URL` | `http://127.0.0.1:5004` |
| `PAYMENTS_BASE_URL` | `http://127.0.0.1:5005` |
| `HTTP_TIMEOUT_SECONDS` | `10` |
| `HEALTH_TIMEOUT_SECONDS` | `3` |
| `HEALTH_REFRESH_SECONDS` | `60` |

```powershell
$env:ORDERS_BASE_URL="https://library.example.com:5004"; python main.py
```

## Estructura

```text
desktop_client/
├── main.py              arranque del cliente completo
├── client_config.py     URLs y timeouts (env / .env / defaults)
├── permissions.py       pestañas y acciones por rol (USER / ADMIN)
├── cart.py              carrito local (solo isbn + cantidad)
├── api/                 capa HTTP, sin Tkinter
│   ├── http.py          ApiClient: JSON, Bearer, timeouts, errores, refresh automático
│   ├── session.py       sesión en memoria (tokens, user_id, role_id, email)
│   ├── errors.py        traducción de códigos del backend a mensajes
│   ├── services.py      AuthApi, BooksApi, UsersApi, AuthorsApi, OrdersApi, PaymentsApi
│   └── health.py        semáforos (GET /health)
├── ui/                  pantallas Tkinter
│   ├── app.py           ventana principal, login ↔ dashboard por rol
│   ├── common.py        UiDispatcher (hilos → Tk), AppContext, Table, FormDialog
│   ├── login.py · books.py · authors.py · users.py · orders.py · payments.py
│   └── service_status.py
├── desktop_app.py       clasificador SOAP (frame reutilizable + ventana standalone)
├── soap_client.py       cliente SOAP (sin cambios)
└── tests/               unittest, sin servicios reales (HTTP simulado)
```

## Sesión, tokens y refresh

- `POST :5001/login` → access token (20 min) + refresh token, `user_id`,
  `role_id`, `email`. Se guardan **solo en memoria** (`api/session.py`):
  nunca en archivos, nunca en logs, nunca en pantalla (`repr` los oculta). La
  contraseña se borra del formulario al enviarla.
- Una petición protegida que recibe **401** dispara **un** `POST /refresh`
  (con el refresh token; el backend rota ambos) y **un** reintento. Si el
  reintento vuelve a dar 401, o el refresh es rechazado, se borra la sesión y
  se vuelve al login con el mensaje "Tu sesión expiró". No hay bucles.
- El refresh está serializado: si varias peticiones reciben 401 a la vez,
  solo una llama a `/refresh` (el refresh token es de un solo uso) y las demás
  reintentan con el token nuevo.
- Si Login no responde durante un refresh, la sesión **no** se borra (el
  refresh token puede seguir siendo válido): se muestra "Login no disponible".
- **Logout**: `POST /logout` (revoca la sesión en el backend). La sesión
  local se borra **siempre**, aunque falle la red.

## Roles

| Pestaña | USER | ADMIN |
| ------- | ---- | ----- |
| Catálogo (Books) | consultar, buscar, agregar al carrito | + crear / editar / eliminar libros |
| Autores (Authors) | consultar, buscar, ver libros | + crear / editar / eliminar, asociar / quitar libros |
| Mis pedidos (Orders) | carrito → pedido, ver líneas, pagar, ver pagos del pedido | igual (compra para sí mismo) |
| Mis pagos (Payments) | sus pagos y estado | igual |
| Usuarios (Users) | — | listar, crear, editar, activar/desactivar, contraseña, eliminar |
| Pedidos (admin) | — | todos, filtros, `pending → cancelled`, `paid → completed` |
| Pagos (admin) | — | todos, aprobar / rechazar / reembolsar |
| Clasificador SOAP | sí | sí |

La UI solo oculta lo que no corresponde; el backend sigue validando todo
(403 si un USER lo intentara).

## Flujo de demostración

1. Login USER → **Catálogo**: ver stock (semáforo: Disponible / Pocas
   unidades / Agotado), elegir libro y cantidad → *Agregar al carrito*.
2. **Mis pedidos** → *Confirmar pedido*: se envía solo
   `{"items": [{"isbn", "cantidad"}]}`; el total lo calcula el backend. El
   stock baja (visible al volver al Catálogo).
3. Seleccionar el pedido → *Pagar pedido*: método (`credit_card`,
   `debit_card`, `bank_transfer`, `cash`) y referencia opcional. **No se pide
   monto**. Resultado: "Pago pendiente de aprobación".
4. *Cerrar sesión* → Login ADMIN → **Pagos (admin)** (filtro `pending`) →
   *Aprobar*: pago `approved`, pedido `paid`.
5. Opcional: *Reembolsar*: pago `refunded`, pedido `cancelled`, stock devuelto.
6. *Cerrar sesión*.

## Semáforos de servicios

Barra superior con los seis servicios (`GET /health`):

- verde **disponible** (`ok` / `healthy`);
- ámbar **degradado** (Books y Authors con Redis caído: las lecturas públicas
  siguen funcionando, las escrituras no);
- rojo **no disponible** (`unhealthy` / `unavailable`, sin respuesta o
  timeout).

Se consultan en un hilo aparte (las seis en paralelo, timeout de 3 s) al
abrir la app, cada 60 s y con el botón **Refresh Services**. Pasando el
mouse por un servicio se ve el detalle (database/redis).

## Hilos y timeouts

- Toda petición HTTP corre en un `threading.Thread`; la UI nunca se congela.
- Los hilos **no tocan widgets**: entregan el resultado a `UiDispatcher`
  (una cola que el hilo principal de Tk vacía cada 40 ms con `after`).
- Toda petición tiene timeout (`HTTP_TIMEOUT_SECONDS`, que en `urllib` limita
  la conexión y cada lectura); los health checks usan `HEALTH_TIMEOUT_SECONDS`.

## Errores

`api/errors.py` traduce todos los errores a mensajes en español:

- servicio caído / timeout → "El servicio Orders no está disponible en
  este momento." (la app nunca se cierra);
- 401 → sesión expirada; 403 → sin permisos; 404 → no existe; 409 →
  conflicto; 503 → servicio no disponible temporalmente;
- códigos de negocio: `INSUFFICIENT_STOCK` (con el detalle por libro),
  `AUTHOR_HAS_BOOKS`, `LAST_ADMIN_REQUIRED`, `ADMIN_ALREADY_EXISTS`,
  `EMAIL_ALREADY_EXISTS`, `USER_HAS_ORDER_HISTORY`, `ORDER_ALREADY_CANCELLED`,
  `ORDER_NOT_PAYABLE`, `PAYMENT_ALREADY_APPROVED`, `PAYMENT_ALREADY_REFUNDED`,
  `REFUND_NOT_ALLOWED`, etc.

Nunca se muestran trazas, SQL, hosts, contraseñas ni tokens.

## Pruebas

```powershell
cd apps\services\soap\desktop_client
python -m unittest discover -s tests -v
```

No necesitan servicios: el HTTP se simula (`tests/fakes.py`). Cubren
sesión, cliente HTTP (Bearer, JSON, timeouts, errores de conexión,
401/403/409/503), refresh (éxito, rechazo, sin bucles, concurrencia),
logout, roles, cada servicio, health, carrito, configuración y la UI
(ventana Tk real con el transporte simulado: pestañas por rol, flujo
compra/pago, stock insuficiente, sesión expirada, la UI no se congela,
clasificador SOAP standalone). Las pruebas de UI se omiten si no hay pantalla.

## Limitaciones conocidas

- Books no expone catálogos de formatos/categorías: al crear un libro se
  indican `formato_id` y `categoria_id` numéricos.
- Las listas piden hasta 200 elementos (sin paginación en la UI).
- El refresh se intenta ante cualquier 401 de una petición protegida (no
  solo `TOKEN_EXPIRED`); si el token fue revocado, el refresh también falla
  y se vuelve al login.
