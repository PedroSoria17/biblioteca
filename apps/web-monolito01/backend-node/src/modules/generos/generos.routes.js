const { crearRouterCatalogo } = require('../../lib/catalogoFactory');
const { configGeneros } = require('../../lib/catalogos');

module.exports = crearRouterCatalogo({
  ...configGeneros,
  rutaBase: 'generos',
  tituloPlural: 'Géneros',
  tituloSingular: 'Género',
});
