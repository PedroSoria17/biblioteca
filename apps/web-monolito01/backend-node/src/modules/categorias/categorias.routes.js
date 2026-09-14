const { crearRouterCatalogo } = require('../../lib/catalogoFactory');
const { configCategorias } = require('../../lib/catalogos');

module.exports = crearRouterCatalogo({
  ...configCategorias,
  rutaBase: 'categorias',
  tituloPlural: 'Categorías',
  tituloSingular: 'Categoría',
});
