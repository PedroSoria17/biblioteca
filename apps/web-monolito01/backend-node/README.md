# Librería en línea — backend-node

Aplicación web **monolítica**, con renderizado HTML del lado del servidor y patrón **MVC**,
organizada **por módulos**. Usa acceso directo a PostgreSQL (`pg`) sobre el esquema definido en
[`/sql/schema.sql`](../../../sql/schema.sql). No expone APIs REST/GraphQL/SOAP ni intercambia
datos en JSON/XML: toda interacción ocurre mediante formularios HTML (`urlencoded` /
`multipart/form-data`) y respuestas HTML renderizadas con EJS. `package.json` existe únicamente
porque npm lo requiere para administrar las dependencias del proyecto.

## Requisitos

- Node.js 18+ (probado con Node 26)
- PostgreSQL con la base de datos creada a partir de `sql/schema.sql`

## Puesta en marcha

```powershell
cd apps/web-monolito01/backend-node
npm install
Copy-Item .env.example .env   # y edita los valores de conexión
```

1. Crea la base de datos y aplica el esquema:
   ```powershell
   psql -U postgres -c "CREATE DATABASE libreria;"
   psql -U postgres -d libreria -f ..\..\..\sql\schema.sql
   ```
2. Crea el administrador inicial (respeta la regla de "máximo un administrador"):
   ```powershell
   npm run seed:admin
   ```
3. Arranca el servidor:
   ```powershell
   npm start        # o: npm run dev  (reinicia automáticamente con node --watch)
   ```
4. Abre `http://localhost:3000`.

## Arquitectura

- **Macroarquitectura**: monolítica — un único proceso Node.js sirve todas las vistas y la
  lógica de negocio; no hay servicios independientes.
- **Patrón MVC**:
  - **Modelo** (`src/modules/*/​*.model.js`, `src/lib/catalogoFactory.js`): acceso directo a
    PostgreSQL vía consultas SQL parametrizadas con `pg`.
  - **Vista** (`src/views/**/*.ejs`): plantillas EJS renderizadas en el servidor.
  - **Controlador** (`src/modules/*/​*.controller.js`): recibe la petición, invoca el modelo y
    decide qué vista renderizar o a dónde redirigir (patrón Post/Redirect/Get).
- **Organización por módulos**: cada entidad del dominio vive en su propia carpeta bajo
  `src/modules/` con su modelo, controlador y rutas (`auth`, `usuarios`, `libros`, `autores`,
  `generos`, `categorias`, `formatos`, `conceptos`). Los cinco catálogos simples (formatos,
  categorías, géneros, conceptos, autores) comparten la misma forma CRUD y se generan con una
  fábrica común (`src/lib/catalogoFactory.js`) en vez de duplicar el mismo código cinco veces.

## Cobertura de CRUD sobre el modelo normalizado

Las 11 tablas de `sql/schema.sql` tienen CRUD accesible desde la UI:

| Tabla            | Dónde se gestiona                                                   |
|-------------------|----------------------------------------------------------------------|
| `usuarios`         | `/usuarios` (admin) y `/usuarios/perfil` (autoservicio)             |
| `formatos`          | `/formatos`                                                          |
| `categorias`        | `/categorias`                                                        |
| `generos`           | `/generos`                                                           |
| `autores`           | `/autores`                                                           |
| `conceptos`         | `/conceptos`                                                         |
| `libros`            | `/libros`                                                            |
| `libro_autor`       | Sección "Autores" en `/libros/:isbn/editar`                          |
| `libro_genero`      | Sección "Géneros" en `/libros/:isbn/editar`                          |
| `libro_concepto`    | Sección "Conceptos y definiciones" en `/libros/:isbn/editar`         |
| `imagenes_libro`    | Sección "Imágenes" en `/libros/:isbn/editar`                         |

Las tablas de asociación se administran dentro de la página de edición del libro (no como menús
propios de nivel superior) porque su ciclo de vida depende siempre de un libro concreto —
mismo criterio de diseño que llevó a separarlas en `data/db_design_solution.md`.

## Usuarios y permisos

- Registro público (`/registro`) crea usuarios no administradores.
- El catálogo (`/libros`, `/libros/:isbn`) es de lectura pública.
- Crear/editar/eliminar libros, catálogos e imágenes requiere sesión de administrador.
- La regla "como máximo un administrador" vive en la base de datos (índice único parcial en
  `usuarios`); la aplicación la respeta con una **transferencia** atómica de rol
  (`usuario.model.js#transferirAdministracion`) en vez de permitir crear un segundo admin.

## Manejo de imágenes

Las imágenes se suben con `multer` (formularios `multipart/form-data`) a
`src/public/uploads/libros/` y se sirven como archivos estáticos; solo la ruta se guarda en
`imagenes_libro.url`. No se usa ningún formato de intercambio de datos estructurado (JSON/XML)
en ningún punto del flujo.

## Notas

- Las sesiones usan el almacén en memoria de `express-session` (adecuado para este proyecto
  académico). En un entorno real conviene un almacén persistente.
- Las contraseñas se protegen con `bcryptjs`.
