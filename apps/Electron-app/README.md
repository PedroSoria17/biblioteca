# Catálogo de Libros — Aplicación de escritorio Electron

Aplicación de escritorio construida con [Electron](https://www.electronjs.org/) que consume, **exclusivamente en XML**, el microservicio Flask real del catálogo de libros:

```text
http://34.51.73.237:5001/books-with-images
```

La implementación equivalente de ese microservicio Flask se encuentra en
`apps/library_soap_service/app.py` (ver su propio README para el detalle
del backend: consultas SQL, endpoint de imágenes, permisos de PostgreSQL,
etc.). Esta app Electron es solo el cliente de escritorio.

## Características

- Consume `GET /books-with-images` del microservicio Flask y parsea la respuesta **XML** (nunca JSON, aunque el microservicio también lo ofrezca vía `?format=json` para otros clientes).
- Muestra cada libro en una card con: **portada**, **título**, **autor(es)**, **año de publicación**, **ISBN** y **precio**.
- Interfaz con estética Material Design (barra superior, cards con elevación, colores primarios, tipografía consistente) y diseño responsivo (se adapta a ventanas grandes, medianas y pequeñas).
- Muestra 6 libros por página al arrancar, con controles de paginación (Anterior / Siguiente).
- Botón de configuración (⚙) que abre un popup para indicar la **IP/host** y el **endpoint** del microservicio. La configuración se guarda en `localStorage` y se reutiliza en los siguientes arranques (persiste incluso al cerrar y volver a abrir la aplicación).
- Botón de actualizar (⟳) para volver a consultar el servicio sin reiniciar la app.
- Manejo de errores de conexión (IP/puerto incorrectos, servicio caído, XML inválido) mostrando un mensaje claro en la interfaz.
- Resuelve automáticamente las URLs relativas de imagen que devuelve el microservicio (por ejemplo `/uploads/libros/archivo.jpg`) contra el mismo host/puerto configurado, para que la portada se muestre realmente en vez de intentar cargarse contra `file://`.

## Requisitos previos

- **Node.js** (incluye npm). Versión recomendada: 18 LTS o superior.
  - Descarga: https://nodejs.org/
  - Verifica la instalación:
    ```bash
    node -v
    npm -v
    ```

No se necesita instalar Electron de forma global: el proyecto lo instala como dependencia local.

## Instalación de Electron y del proyecto en tu máquina local

1. Abre una terminal (PowerShell, CMD o Git Bash) y navega hasta la carpeta de la aplicación:

   ```bash
   cd apps/Electron-app
   ```

2. Instala las dependencias del proyecto (esto descarga e instala Electron localmente, dentro de `node_modules`):

   ```bash
   npm install
   ```

   > La primera vez, `npm install` descargará el binario de Electron correspondiente a tu sistema operativo (puede tardar unos minutos según tu conexión).

3. (Opcional) Si la descarga del binario de Electron se interrumpe o falla, puedes forzarla manualmente con:

   ```bash
   node node_modules/electron/install.js
   ```

## Ejecutar la aplicación

Con las dependencias instaladas, inicia la aplicación con:

```bash
npm start
```

Esto abrirá la ventana de escritorio de Electron con el catálogo de libros.

## Configurar la IP y el endpoint del microservicio

1. En la parte superior de la aplicación, pulsa el ícono de engranaje (⚙) "Configuración".
2. Indica:
   - **IP / Host del microservicio**: por ejemplo `34.51.73.237:5001` (también admite un host con esquema, por ejemplo `http://34.51.73.237:5001`, si lo prefieres explícito).
   - **Endpoint**: por ejemplo `/books-with-images`.
3. Pulsa **Guardar**. La configuración se persiste en `localStorage` y la aplicación recargará automáticamente el catálogo usando la nueva URL (`http://IP/endpoint`).
4. Usa el ícono de refrescar (⟳) en cualquier momento para volver a consultar el servicio con la configuración actual.
5. La configuración persiste aunque cierres y vuelvas a abrir la aplicación (verificado: se guarda un host/endpoint personalizado, se cierra la app por completo y, al reabrirla, el popup de Configuración sigue mostrando esos mismos valores).

Valores por defecto (usados la primera vez que se abre la app, antes de guardar cualquier configuración propia):

- IP / Host: `34.51.73.237:5001`
- Endpoint: `/books-with-images`

URL final por defecto:

```text
http://34.51.73.237:5001/books-with-images
```

## Estructura del proyecto

```
apps/Electron-app/
├── main.js         # Proceso principal de Electron: crea la ventana y hace la petición HTTP al microservicio
├── preload.js       # Puente seguro (contextBridge) entre el proceso principal y el renderer
├── index.html        # Estructura de la interfaz (barra superior, grid de cards, modal de configuración)
├── styles.css        # Estilos Material Design y diseño responsivo
├── renderer.js       # Lógica de la interfaz: parseo de XML, render de cards, paginación y configuración (localStorage)
├── package.json
└── README.md
```

## Notas técnicas

### Arquitectura (proceso principal vs. renderer)

- La petición HTTP al microservicio se realiza desde el **proceso principal** de Electron (`main.js`, Node.js), evitando problemas de CORS que ocurrirían si se hiciera directamente desde el renderer. El renderer nunca hace `fetch` directo al microservicio: le pide el XML al proceso principal vía `window.booksApi.fetchBooksXml(config)` (expuesto de forma segura en `preload.js` con `contextBridge`).
- Seguridad de Electron: `contextIsolation: true`, `nodeIntegration: false` y `sandbox: true` en el `BrowserWindow` (`main.js`). El renderer no tiene acceso directo a Node.js; solo al puente explícito de `preload.js`.
- El renderer consume **exclusivamente XML**: `catalog/format.py` en el microservicio ya responde XML por defecto, así que Electron nunca añade `?format=json`.

### Parser XML (`renderer.js`)

El parser reconoce primero los nombres de etiqueta **reales** del microservicio Flask (`apps/library_soap_service`), y conserva alternativas en inglés por compatibilidad con otros microservicios de libros:

| Campo mostrado | Etiquetas reales (Flask) | Alternativas soportadas |
|---|---|---|
| Título | `titulo` | `title`, `name` |
| Autor(es) | `autores` > `autor` (varios) | `authors` > `author`/`writer` |
| Año de publicación | `anio_publicacion` | `year` |
| ISBN | `isbn` | `isbn13`, `isbn10` |
| Precio | `precio` | `price`, `cost` |
| Imagen | `images` > `image` > `url` (con `isCover`/`order` para elegir portada) | etiqueta suelta `image`/`photo`/`cover`/`thumbnail` |

Dentro de `<images>` puede haber varias `<image>`; el parser elige la que tenga `<isCover>true</isCover>` y, si ninguna la tiene, la de menor `<order>`.

### Resolución de URLs de imagen (`resolveImageUrl` en `renderer.js`)

`imagenes_libro.url` en el microservicio puede ser una ruta relativa, por ejemplo `/uploads/libros/archivo.jpg` (servida por el propio Flask en `GET /uploads/libros/archivo.jpg`, ver README de `apps/library_soap_service`). Un helper reutilizable (`resolveImageUrl(url, baseUrl)`) decide qué URL final usar:

- si `url` ya es absoluta (`http://` o `https://`), se usa tal cual;
- si es relativa, se reconstruye como `${origin del microservicio configurado}${url}` — por ejemplo, con host configurado `34.51.73.237:5001` y `url = "/uploads/libros/archivo.jpg"`, la URL final es `http://34.51.73.237:5001/uploads/libros/archivo.jpg`.

El "origin del microservicio configurado" se calcula a partir de la URL que realmente respondió la petición (`new URL(result.url).origin`), no reconstruyendo el host a mano por segunda vez, así que **nunca** intenta resolver la imagen contra `file://` (el origen del renderer de Electron).

- Si una portada no está disponible o la URL de la imagen falla (por ejemplo, el microservicio responde `404` porque el archivo físico no existe), se muestra un ícono de libro como marcador de posición (`onerror` del `<img>`).
- Si el microservicio no responde (por ejemplo, IP/puerto incorrectos o servicio caído), la aplicación muestra un aviso indicando que se revise la configuración.

## Validar contra el microservicio real (GCP)

Esta app **no** debe validarse de forma final contra un servidor XML simulado. Para confirmar que todo funciona contra el servicio real:

1. Antes de abrir Electron, confirma en el navegador o con `curl` que el microservicio responde XML con los campos esperados:

   ```bash
   curl http://34.51.73.237:5001/books-with-images
   ```

   Debe devolver `<books>` con, por cada `<book>`: `isbn`, `titulo`, `autores > autor`, `anio_publicacion`, `precio` e `images > image > url/alt/order/isCover`.

2. Ejecuta la app:

   ```bash
   cd apps/Electron-app
   npm start
   ```

3. Sin tocar Configuración (usa los valores por defecto), confirma que aparecen libros reales con título, autor(es), año, ISBN y precio reales, y que las portadas cargan (o muestran el placeholder si el archivo de imagen no existe físicamente en el servidor).
4. Prueba la paginación (Anterior/Siguiente) y el botón de refrescar (⟳).
5. Abre Configuración, cambia host/endpoint a un valor de prueba, guarda, cierra la app por completo y vuelve a abrirla: Configuración debe seguir mostrando ese valor (confirma la persistencia real en `localStorage`, no solo en memoria). Vuelve a dejar los valores apuntando al servicio real al terminar.

## Empaquetar la aplicación (opcional)

Este proyecto no incluye un empaquetador por defecto. Si deseas generar un instalador o ejecutable distribuible, puedes añadir herramientas como [electron-builder](https://www.electron.build/) o [electron-packager](https://github.com/electron/electron-packager) como dependencia de desarrollo adicional.
