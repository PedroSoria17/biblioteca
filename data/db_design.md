1.- Diseña una base de datos en Postgres Para una aplicacion web que gestione una libreria en linea

2.- El diseño debe contemplar administrador de usuarios registrados, manejar imagenes y conservar definiciones de conceptos asociados a cada libro.

3.- Un libro debe tener ISBN, titulo, autor, año de publicacion, genero, precio, stock, formato, imagenes y conceptos definidos por libro, identifica dependencias funcionales y multivaluadas.

- Un libro puede tener varios autores
- Un libro puede pertenecer a varios generos
- Un libro puede definir muchos conceptos y un mismo concepto puede aparecer en distintos libros con definiciones diferentes
- Un libro puede tener varias imagenes
- Formato y categoria son catalogos independientes
- Debe existir como maximo un administrador