# CONTRACT_AUDIT.md

## Ejercicio 03 — Auditoría inicial del contrato WSDL/XSD

**Proyecto:** Módulo SOAP para clasificación del catálogo de una librería  
**Contrato:** `library-classifier.wsdl` + `library-classifier.xsd`  
**Versión:** v1  
**Enfoque:** Contract-first  
**Alumno:** Pedro Elidio Soria Gonzalez  
**Matrícula:** 596630  

---

## 1. Objetivo

Revisar el contrato SOAP antes de implementar el servicio Flask, verificando:

- Qué operaciones se exponen.
- Qué datos recibe cada operación.
- Qué datos devuelve.
- Qué información del monolito permanece oculta.
- Qué errores deben convertirse en SOAP Fault.
- Qué riesgos de seguridad o acoplamiento introduce el contrato.
- Si el contrato puede mantenerse estable mientras evoluciona la implementación interna.

La regla principal es que el contrato debe exponer capacidades y datos necesarios para el cliente, no la estructura completa de PostgreSQL.

---

## 2. Namespace y versión

Namespace utilizado:

```text
http://udem.edu/iac/library-classifier/v1
```

La inclusión de `/v1` permite distinguir futuras revisiones incompatibles del contrato.

El endpoint inicial de desarrollo es:

```text
http://localhost:5000/soap
```

Este valor deberá cambiarse durante el despliegue final sin alterar las operaciones ni los tipos del contrato.

---

## 3. Estilo SOAP

El contrato utiliza:

- SOAP 1.1.
- WSDL 1.1.
- Estilo `document`.
- Codificación `literal`.
- XSD externo para los tipos.
- HTTP como transporte.

Decisión:

```text
Document/Literal
```

Justificación:

- Mantiene un contrato explícito.
- Facilita interoperabilidad entre lenguajes.
- Reduce dependencia de detalles internos de Python.
- Permite generar clientes desde WSDL posteriormente.

---

## 4. Operaciones expuestas

### 4.1 ObtenerConceptosPendientes

**Objetivo:** devolver conceptos del catálogo que el clasificador todavía no ha clasificado.

#### Entrada

- `clasificador.nombre`
- `clasificador.apellidos`
- `clasificador.correo`
- `cliente.tipoCliente`
- `cliente.identificador`
- `limite` opcional

#### Salida

- `totalPendientes`
- Lista de conceptos:
  - `isbn`
  - `tituloLibro`
  - `categoria`
  - `conceptoId`
  - `concepto`
  - `definicion`

#### Datos deliberadamente no expuestos

- Precio del libro.
- Stock.
- Formato.
- Autores.
- Géneros.
- Imágenes.
- Datos de usuarios del monolito.
- Credenciales de PostgreSQL.
- IDs internos de auditoría del módulo SOAP.

#### Faults esperados

- XML inválido.
- Datos obligatorios faltantes.
- Correo inválido.
- Cliente inválido.
- Error interno de PostgreSQL.

---

### 4.2 RegistrarClasificacion

**Objetivo:** registrar la clasificación Cloud de un concepto.

#### Entrada

- `clasificador.nombre`
- `clasificador.apellidos`
- `clasificador.correo`
- `cliente.tipoCliente`
- `cliente.identificador`
- `isbn`
- `conceptoId`
- `modeloCloud`

#### `modeloCloud`

El XSD restringe los valores a:

```text
IaaS
PaaS
SaaS
FaaS
```

#### Salida

- `registrada`
- `mensaje`
- `fechaClasificacion`

#### Faults esperados

- XML inválido.
- Campos obligatorios faltantes.
- Modelo Cloud inválido.
- Libro/concepto inexistente.
- Relación libro-concepto inexistente.
- Clasificación duplicada.
- Error interno de PostgreSQL.

---

### 4.3 ObtenerProgresoUsuario

**Objetivo:** consultar el avance de clasificación asociado a un clasificador.

#### Entrada

- `correo`
- `cliente.tipoCliente`
- `cliente.identificador`

#### Salida

- `totalCatalogo`
- `totalClasificados`
- `totalPendientes`
- `porcentajeCompletado`

#### Datos deliberadamente no expuestos

- `clasificador_id`.
- Registros internos de `clientes_servidos`.
- Fechas de auditoría internas.
- Información de otros clasificadores.

#### Faults esperados

- XML inválido.
- Correo inválido.
- Cliente inválido.
- Error interno de PostgreSQL.

---

## 5. Matriz dato → operación → exposición → justificación

| Dato | Operación | ¿Se expone? | Justificación |
|---|---|---:|---|
| ISBN | ObtenerConceptosPendientes | Sí | Identifica el libro asociado al concepto |
| ISBN | RegistrarClasificacion | Sí | Permite identificar la relación libro-concepto |
| Título del libro | ObtenerConceptosPendientes | Sí | Da contexto al usuario |
| Categoría | ObtenerConceptosPendientes | Sí | Da contexto de clasificación |
| Concepto ID | ObtenerConceptosPendientes | Sí | Identificador estable para registrar la clasificación |
| Concepto | ObtenerConceptosPendientes | Sí | Es el elemento que el usuario clasifica |
| Definición | ObtenerConceptosPendientes | Sí | Contexto necesario para decidir IaaS/PaaS/SaaS/FaaS |
| Modelo Cloud | RegistrarClasificacion | Sí | Dato de negocio principal |
| Nombre | Operaciones de clasificación | Sí | Identificación mínima del clasificador |
| Apellidos | Operaciones de clasificación | Sí | Identificación mínima del clasificador |
| Correo | Operaciones de clasificación/progreso | Sí | Identidad lógica del clasificador |
| Precio | Ninguna | No | No es necesario para clasificar |
| Stock | Ninguna | No | No es necesario para clasificar |
| Formato | Ninguna | No | No es necesario para clasificar |
| Autores | Ninguna | No | No es necesario para la operación SOAP actual |
| Géneros | Ninguna | No | No es necesario para la operación SOAP actual |
| Imágenes | Ninguna | No | No son necesarias para la clasificación |
| `usuarios` del monolito | Ninguna | No | El módulo SOAP usa clasificadores independientes |
| Password hash | Ninguna | No | Información sensible |
| Credenciales PostgreSQL | Ninguna | No | Información sensible interna |
| SQL ejecutado | Ninguna | No | Detalle interno de implementación |
| Stack trace | SOAP Fault | No | No debe exponerse al cliente |
| Rutas del servidor | SOAP Fault | No | Información interna sensible |
| `clasificador_id` | Ninguna | No | Identificador interno; el cliente usa correo |
| `cliente_id` | Ninguna | No | Identificador interno |
| Contador de peticiones | Ninguna en v1 | No | Auditoría interna del módulo |
| Fecha de clasificación | RegistrarClasificacion | Sí | Confirma cuándo se registró la operación |
| Totales de progreso | ObtenerProgresoUsuario | Sí | Resultado requerido por la operación |

---

## 6. Auditoría de acoplamiento

### Acoplamiento 1 — `isbn`

El contrato utiliza ISBN como identificador público del libro.

**Ventaja:** es comprensible y estable para el dominio.

**Riesgo:** el módulo SOAP depende de que el monolito conserve el ISBN como identificador del libro.

**Mitigación:** encapsular las consultas a PostgreSQL en una capa de acceso a datos. El cliente SOAP no conoce nombres de tablas ni columnas.

---

### Acoplamiento 2 — `conceptoId`

El contrato expone el ID numérico de concepto.

**Ventaja:** evita registrar clasificaciones por nombre ambiguo.

**Riesgo:** el ID proviene del modelo persistente.

**Mitigación:** tratarlo como identificador contractual y no exponer ninguna otra columna interna de `conceptos`.

---

### Acoplamiento 3 — relación libro-concepto

`RegistrarClasificacion` recibe:

```text
isbn + conceptoId
```

Esto permite verificar que el concepto realmente pertenece al libro seleccionado.

**Ventaja:** preserva la semántica del modelo 4FN del Ejercicio 02.

**Riesgo:** existe dependencia conceptual respecto a `libro_concepto`.

**Mitigación:** la relación se valida dentro del servicio; el cliente nunca conoce la tabla `libro_concepto`.

---

## 7. Riesgos identificados y mitigación

### Riesgo 1 — Exposición excesiva de datos

**Problema:** un WSDL puede convertirse en una superficie pública demasiado amplia.

**Mitigación:** sólo se exponen campos necesarios para clasificar y consultar progreso.

**Estado:** Mitigado por diseño.

---

### Riesgo 2 — Enumeraciones incompatibles

**Problema:** aceptar cualquier texto para `modeloCloud` produciría valores inconsistentes.

**Mitigación:** `ModeloCloudType` restringe mediante XSD:

```text
IaaS | PaaS | SaaS | FaaS
```

**Estado:** Mitigado por contrato y posteriormente por CHECK en PostgreSQL.

---

### Riesgo 3 — Filtrar errores internos

**Problema:** un SOAP Fault podría revelar SQL, stack traces o rutas internas.

**Mitigación:** el contrato define un Fault de servicio con:

- `codigo`
- `mensaje`

El detalle técnico deberá almacenarse sólo en logs.

**Estado:** Mitigación diseñada; pendiente de implementación.

---

### Riesgo 4 — Identidad basada únicamente en correo

**Problema:** en la primera versión el correo identifica lógicamente al clasificador, pero un cliente podría enviar el correo de otra persona.

**Mitigación actual:** alcance académico y registro controlado del clasificador.

**Mitigación posterior:** WS-Security se agregará para operaciones sensibles en la Tarea 1.

**Estado:** Riesgo residual conocido.

---

### Riesgo 5 — Contrato acoplado a la base compartida

**Problema:** el módulo SOAP y el monolito utilizan el mismo PostgreSQL.

**Mitigación:**

- Capa `db/` independiente.
- Usuario PostgreSQL exclusivo.
- Acceso de sólo lectura a tablas del monolito.
- Tablas SOAP en schema propio.
- No exponer nombres de tablas en el WSDL.

**Estado:** Reducido, no eliminado.

---

## 8. Auditoría de SOAP Fault

Se propone mantener códigos contractuales estables.

| Código | Caso | Fault |
|---|---|---|
| `INVALID_XML` | XML no parseable | Client |
| `INVALID_REQUEST` | Campo requerido faltante | Client |
| `INVALID_EMAIL` | Correo inválido | Client |
| `INVALID_CLOUD_MODEL` | Modelo fuera de IaaS/PaaS/SaaS/FaaS | Client |
| `CONCEPT_NOT_FOUND` | Concepto inexistente | Client |
| `BOOK_CONCEPT_NOT_FOUND` | Relación ISBN/concepto inexistente | Client |
| `DUPLICATE_CLASSIFICATION` | El clasificador ya registró el concepto | Client / conflicto 409 |
| `INTERNAL_ERROR` | Error inesperado o PostgreSQL | Server |

Regla:

El cliente recibe únicamente el código contractual y un mensaje comprensible.

Los logs internos pueden conservar información técnica adicional.

---

## 9. Revisión de compatibilidad futura

Para mantener compatibilidad con clientes ya generados:

### Cambios compatibles

- Agregar una nueva operación.
- Agregar nuevos tipos no utilizados por operaciones anteriores.
- Agregar elementos opcionales (`minOccurs="0"`) al final de una secuencia cuando la herramienta cliente lo tolere.

### Cambios potencialmente incompatibles

- Renombrar operaciones.
- Renombrar elementos existentes.
- Cambiar tipos.
- Convertir un campo opcional en obligatorio.
- Eliminar valores de una enumeración.
- Cambiar el namespace v1.
- Cambiar la semántica de una operación existente.

La Tarea 1 deberá agregar:

```text
ObtenerEstadisticasPorModelo
```

sin modificar las tres operaciones existentes.

---

## 10. Decisiones aprobadas antes de implementación

### D-01 — Contract-first

**Necesidad:** evitar que el WSDL sea sólo un reflejo accidental del código.

**Decisión:** definir WSDL/XSD antes de Flask.

**Ventaja:** contrato explícito e interoperable.

**Limitación:** requiere mayor diseño inicial.

---

### D-02 — WSDL y XSD separados

**Necesidad:** mantener tipos organizados.

**Decisión:** `library-classifier.wsdl` importa `library-classifier.xsd`.

**Ventaja:** facilita mantenimiento y reutilización.

**Limitación:** ambos archivos deben publicarse juntos.

---

### D-03 — SOAP 1.1 Document/Literal

**Necesidad:** maximizar interoperabilidad académica.

**Decisión:** utilizar binding document/literal.

**Ventaja:** adecuado para clientes generados desde WSDL.

**Limitación:** mayor cantidad de XML que formatos ligeros.

---

### D-04 — Datos mínimos

**Necesidad:** reducir exposición.

**Decisión:** no reflejar automáticamente todas las columnas PostgreSQL.

**Ventaja:** menor acoplamiento y superficie de ataque.

**Limitación:** nuevas necesidades pueden requerir evolución contractual.

---

### D-05 — Fault contractual

**Necesidad:** permitir que clientes distingan errores.

**Decisión:** definir `ServiceFault` con código y mensaje.

**Ventaja:** errores consistentes entre clientes.

**Limitación:** requiere mapear explícitamente excepciones internas.

---

## 11. Observación pendiente sobre duplicados

Actualmente la persistencia propuesta cumple literalmente la regla:

```text
UNIQUE(clasificador_id, concepto_id)
```

Esto significa que un clasificador no puede volver a clasificar el mismo concepto aunque dicho concepto aparezca en más de un libro.

El contrato, sin embargo, conserva:

```text
isbn + conceptoId
```

porque permite identificar la relación real que se está mostrando al cliente.

Si posteriormente se determina que debe clasificarse cada aparición libro-concepto de manera independiente, la restricción debería evolucionar a:

```text
UNIQUE(clasificador_id, isbn, concepto_id)
```

No se realizará este cambio hasta confirmar la interpretación del requerimiento.

---

## 12. Resultado de la auditoría

El contrato inicial es adecuado para comenzar la implementación del módulo SOAP porque:

- Mantiene separadas las responsabilidades del cliente y del servidor.
- Expone únicamente datos necesarios.
- Define tipos XSD explícitos.
- Restringe el modelo Cloud.
- Incluye SOAP Fault contractual.
- Mantiene ocultos detalles sensibles de PostgreSQL.
- Permite agregar posteriormente `ObtenerEstadisticasPorModelo`.
- Está preparado para interoperabilidad mediante clientes generados.

### Estado

**APROBADO PARA IMPLEMENTACIÓN INICIAL**, manteniendo como punto de seguimiento la interpretación exacta de clasificación duplicada cuando un mismo concepto aparece en varios libros.

---

**Pedro Elidio Soria Gonzalez**  
**Matrícula 596630**  
**Integración de Aplicaciones Computacionales — 2026**
