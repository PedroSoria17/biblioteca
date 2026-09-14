const { crearRouterCatalogo } = require('../../lib/catalogoFactory');
const { configFormatos } = require('../../lib/catalogos');

module.exports = crearRouterCatalogo({
  ...configFormatos,
  rutaBase: 'formatos',
  tituloPlural: 'Formatos',
  tituloSingular: 'Formato',
});
