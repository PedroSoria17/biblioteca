# MACRO_ARCHITECTURE_SOAP.md

## Ejercicio 03 — Macroarquitectura

### Componentes

1. **Aplicación de escritorio / Cliente SOAP**
   - Captura datos del clasificador.
   - Construye o genera el SOAP Envelope.
   - Envía HTTP POST/XML.
   - Procesa respuestas SOAP y SOAP Fault.
   - No conoce detalles de PostgreSQL.

2. **Módulo SOAP Flask**
   - Proyecto independiente del monolito.
   - Publica el contrato WSDL/XSD.
   - Recibe y procesa SOAP 1.1.
   - Construye XML manualmente con `xml.etree.ElementTree`.
   - Valida entradas.
   - Traduce errores de negocio a SOAP Fault.
   - Accede a PostgreSQL mediante `psycopg2`.

3. **Monolito Node.js**
   - Continúa funcionando sin modificaciones.
   - Mantiene su acceso normal a `library_db`.
   - No consume el servicio SOAP.

4. **PostgreSQL**
   - `public`: tablas existentes del Ejercicio 02.
   - `soap_module`: tablas exclusivas del Ejercicio 03.
   - El módulo SOAP usa una cuenta propia de mínimo privilegio.

### Flujo principal

```text
Desktop
   ↓ SOAP 1.1 / HTTP POST / XML
Flask SOAP Service
   ↓ validación
Service Layer
   ↓ psycopg2
PostgreSQL
```

En paralelo:

```text
Node.js Monolith
   ↓ pg
PostgreSQL
```

### Responsabilidades del contrato

El contrato expone únicamente lo necesario para clasificar:

- ISBN.
- Título.
- Categoría.
- Concepto ID.
- Concepto.
- Definición.
- Modelo Cloud.
- Progreso del clasificador.

No expone:

- Credenciales PostgreSQL.
- Password hashes.
- Tabla `usuarios`.
- Precio.
- Stock.
- Datos internos de auditoría.
- Consultas SQL.
- Rutas internas del servidor.
