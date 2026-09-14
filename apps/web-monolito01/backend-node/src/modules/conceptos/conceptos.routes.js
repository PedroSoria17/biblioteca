const { crearRouterCatalogo } = require('../../lib/catalogoFactory');
const { configConceptos } = require('../../lib/catalogos');

module.exports = crearRouterCatalogo({
  ...configConceptos,
  rutaBase: 'conceptos',
  tituloPlural: 'Conceptos',
  tituloSingular: 'Concepto',
});
