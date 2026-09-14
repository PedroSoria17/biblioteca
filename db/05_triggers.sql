-- ============================================================================
-- 05_triggers.sql
-- Triggers para library_db.
--
-- Ejecutar DESPUES de db/01_schema.sql. Puede ejecutarse en cualquier momento
-- relativo a db/06_views.sql y db/04_stored_procedures.sql: ninguno de estos
-- triggers depende de vistas ni de funciones/procedimientos (ver orden final
-- documentado en el encabezado de db/01_schema.sql, donde este archivo va
-- despues de 04 por convencion, no por una dependencia real).
--
-- Criterio del ejercicio: un trigger solo se justifica cuando la regla NO se
-- resuelve mejor con PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK o un indice
-- unico parcial. Por eso este archivo es deliberadamente corto:
--
--   - Administrador unico      -> indice unico parcial (db/01_schema.sql)
--   - Portada unica por libro  -> indice unico parcial (db/01_schema.sql)
--   - Precio / stock negativos -> CHECK (db/01_schema.sql)
--   - ISBN duplicado           -> PRIMARY KEY (db/01_schema.sql)
--   - Relaciones N:M duplicadas-> PRIMARY KEY compuesta (db/01_schema.sql)
--
-- Ninguna de esas reglas se reimplementa aqui con un trigger: serian
-- redundantes con el mecanismo declarativo que ya las garantiza.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- trg_libros_set_fecha_actualizacion
--
-- Necesidad real: dejar constancia automatica de cuando cambio por ultima vez
-- un libro (columna libros.fecha_actualizacion), sin depender de que cada
-- sentencia UPDATE del modelo Node recuerde asignarla manualmente. Esto no es
-- expresable con PK/FK/UNIQUE/CHECK porque el valor depende del momento de
-- ejecucion (now()), no de una condicion estatica sobre los datos: es
-- exactamente el tipo de regla para la que un trigger es la herramienta
-- correcta.
--
-- Ya existia en sql/schema.sql (mezclado junto a las tablas); aqui se separa
-- en su propio archivo, tal como pide el ejercicio, sin cambiar su
-- comportamiento.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_set_fecha_actualizacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_libros_set_fecha_actualizacion ON libros;

CREATE TRIGGER trg_libros_set_fecha_actualizacion
    BEFORE UPDATE ON libros
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_fecha_actualizacion();

-- No se agregan mas triggers: no se identifico ninguna otra regla del
-- dominio (RF/RNF de docs/REQUIREMENTS.md) que no este ya cubierta por una
-- restriccion declarativa en db/01_schema.sql. Agregar triggers adicionales
-- solo para aumentar la cantidad iria en contra de la instruccion explicita
-- del ejercicio.
