const { crearRouterCatalogo } = require('../../lib/catalogoFactory');
const { configAutores } = require('../../lib/catalogos');

module.exports = crearRouterCatalogo({
  ...configAutores,
  rutaBase: 'autores',
  tituloPlural: 'Autores',
  tituloSingular: 'Autor',
});
