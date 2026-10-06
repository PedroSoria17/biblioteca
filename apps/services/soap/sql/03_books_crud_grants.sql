-- ============================================================================
-- 03_books_crud_grants.sql
-- Privilegios adicionales para el CRUD REST de Books (POST/PUT/PATCH/DELETE
-- /books) cuando el servicio se conecta como library_soap_user.
--
-- Hasta ahora library_soap_user solo podia LEER public.libros (ver la seccion
-- de GRANT de soap_module.sql). El CRUD necesita escribir esa tabla.
--
-- - Solo agrega privilegios; no crea, altera ni borra objetos ni datos.
-- - Idempotente: repetir un GRANT existente no tiene efecto.
-- - Si el rol no existe (p. ej. el servicio usa library_user, que ya tiene
--   DML por 00_create_database.sql), el bloque se omite sin error.
--
-- Notas sobre DELETE:
-- - Las cascadas de libros (libro_autor, libro_genero, imagenes_libro,
--   libro_concepto y, desde libro_concepto,
--   soap_module.clasificaciones_cloud) y la verificacion de
--   pedido_detalle (RESTRICT, migracion 07) las ejecuta PostgreSQL como
--   dueno de las tablas: no requieren privilegios extra para este rol.
--
-- Ejecutar con un usuario administrativo:
--   psql -U <admin> -d <base> -v ON_ERROR_STOP=1 -f sql/03_books_crud_grants.sql
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'library_soap_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.libros TO library_soap_user;
        -- Lectura de los catalogos que validan formato_id/categoria_id y
        -- que el GET ya usaba (JOIN de /books).
        GRANT SELECT ON public.formatos, public.categorias TO library_soap_user;
    END IF;
END $$;
