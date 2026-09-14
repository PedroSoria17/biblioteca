const { crearModeloCatalogo } = require('./catalogoFactory');

const configFormatos = {
  tabla: 'formatos',
  idColumna: 'formato_id',
  campos: [{ nombre: 'nombre', etiqueta: 'Nombre', requerido: true }],
};

const configCategorias = {
  tabla: 'categorias',
  idColumna: 'categoria_id',
  campos: [{ nombre: 'nombre', etiqueta: 'Nombre', requerido: true }],
};

const configGeneros = {
  tabla: 'generos',
  idColumna: 'genero_id',
  campos: [{ nombre: 'nombre', etiqueta: 'Nombre', requerido: true }],
};

const configConceptos = {
  tabla: 'conceptos',
  idColumna: 'concepto_id',
  campos: [{ nombre: 'nombre', etiqueta: 'Nombre', requerido: true }],
};

const configAutores = {
  tabla: 'autores',
  idColumna: 'autor_id',
  campos: [
    { nombre: 'nombre', etiqueta: 'Nombre', requerido: true },
    { nombre: 'apellido', etiqueta: 'Apellido', requerido: true },
    { nombre: 'pais', etiqueta: 'País', requerido: false },
  ],
};

module.exports = {
  configFormatos,
  configCategorias,
  configGeneros,
  configConceptos,
  configAutores,
  formatoModelo: crearModeloCatalogo(configFormatos),
  categoriaModelo: crearModeloCatalogo(configCategorias),
  generoModelo: crearModeloCatalogo(configGeneros),
  conceptoModelo: crearModeloCatalogo(configConceptos),
  autorModelo: crearModeloCatalogo(configAutores),
};
