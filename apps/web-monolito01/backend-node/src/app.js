const path = require('path');
const express = require('express');
const session = require('express-session');

const flash = require('./middleware/flash');
const errorHandler = require('./middleware/errorHandler');

const authRoutes = require('./modules/auth/auth.routes');
const usuarioRoutes = require('./modules/usuarios/usuario.routes');
const formatoRoutes = require('./modules/formatos/formatos.routes');
const categoriaRoutes = require('./modules/categorias/categorias.routes');
const generoRoutes = require('./modules/generos/generos.routes');
const conceptoRoutes = require('./modules/conceptos/conceptos.routes');
const autorRoutes = require('./modules/autores/autores.routes');
const libroRoutes = require('./modules/libros/libro.routes');

const app = express();

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// Solo formularios HTML tradicionales (urlencoded / multipart). Deliberadamente
// no se registra express.json(): la aplicacion no intercambia datos en JSON/XML.
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// Sin un valor por defecto: un secreto de sesion predecible permitiria
// falsificar cookies de sesion firmadas por la aplicacion.
if (!process.env.SESSION_SECRET) {
  throw new Error(
    'Falta la variable de entorno SESSION_SECRET. Configura un valor secreto y largo antes de iniciar la aplicación.'
  );
}

app.use(
  session({
    secret: process.env.SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
    cookie: { maxAge: 1000 * 60 * 60 * 4 },
  })
);

app.use(flash);
app.use((req, res, next) => {
  res.locals.usuarioActual = req.session.usuario || null;
  next();
});

app.get('/', (req, res) => res.redirect('/libros'));

app.use(authRoutes);
app.use('/usuarios', usuarioRoutes);
app.use('/formatos', formatoRoutes);
app.use('/categorias', categoriaRoutes);
app.use('/generos', generoRoutes);
app.use('/conceptos', conceptoRoutes);
app.use('/autores', autorRoutes);
app.use('/libros', libroRoutes);

app.use((req, res) => {
  res.status(404).render('errores/mensaje', { status: 404, mensaje: 'Página no encontrada.' });
});

app.use(errorHandler);

module.exports = app;
