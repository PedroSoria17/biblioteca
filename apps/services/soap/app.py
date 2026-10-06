import logging
import os
from pathlib import Path

from flask import Flask, Response, request, send_from_directory
from library_shared.cors import init_cors
from library_shared.flask_auth import init_auth, require_roles
from library_shared.redis_client import RedisGateway
from library_shared.roles import ROLE_ADMIN

from catalog import repository as catalog_repository
from catalog import serializers as catalog_serializers
from catalog import validation as catalog_validation
from catalog.cache import BooksCache
from catalog.errors import book_not_found
from catalog.http import auth_error_response, catalog_route
from config.settings import ConfigurationError, get_security_settings, get_settings
from db.connection import open_connection
from soap.envelope import parse_request
from soap.faults import SoapServiceError, build_fault, internal_error
from soap.service import dispatch


BASE_DIR = Path(__file__).resolve().parent
WSDL_DIR = BASE_DIR / "wsdl"
DEFAULT_UPLOADS_LIBROS_DIR = BASE_DIR / "uploads" / "libros"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("library_soap_service")


def xml_response(payload: bytes, status: int = 200) -> Response:
    return Response(
        payload,
        status=status,
        content_type="text/xml; charset=utf-8",
    )


# After a failed cache read/write, skip the cache for this long and go
# straight to PostgreSQL instead of paying Redis' connect timeout on every
# public GET (library_shared RedisGateway cooldown; never applies to the
# JWT revocation check nor to invalidations).
CACHE_COOLDOWN_SECONDS = 5.0


def _database_status() -> str:
    try:
        conn = open_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        finally:
            conn.close()
        return "connected"
    except Exception:
        # Never leak host/port/credentials from the driver error.
        return "unavailable"


def _write_response(response: Response, cache_invalidated: bool) -> Response:
    # The write is committed either way; this only flags a possibly stale
    # cache window (bounded by BOOKS_CACHE_TTL_SECONDS).
    if not cache_invalidated:
        response.headers["X-Cache-Invalidation"] = "failed"
    return response


def create_app(redis_gateway: RedisGateway | None = None) -> Flask:
    """
    `redis_gateway` is only injected by tests; normally it is built from
    REDIS_URL. Building it does not connect, so the service starts (and
    serves public reads from PostgreSQL) even while Redis is down.
    """
    # Fail fast when required environment variables are missing.
    settings = get_settings()
    security = get_security_settings()

    uploads_libros_dir = (
        Path(settings.uploads_libros_dir).resolve()
        if settings.uploads_libros_dir
        else DEFAULT_UPLOADS_LIBROS_DIR
    )

    app = Flask(__name__)

    gateway = redis_gateway or RedisGateway.from_settings(
        security.redis, cache_cooldown_seconds=CACHE_COOLDOWN_SECONDS
    )
    books_cache = BooksCache(gateway, security.books_cache_ttl_seconds)
    init_auth(app, security.jwt, gateway, error_renderer=auth_error_response)
    init_cors(app, security.cors)

    @app.get("/health")
    def health():
        # Bilingual per 01_prompt_bilingue.md section 16: XML by default,
        # ?format=json for JSON. Does not affect POST /soap or the WSDL/XSD
        # routes, which keep their original SOAP/XML behavior.
        #
        # Without ?details=true the response is exactly the historical
        # liveness payload (clients and tests compare it literally). With
        # it, PostgreSQL and Redis are checked: Redis down -> "degraded"
        # (200, public reads still served from PostgreSQL, writes refused);
        # PostgreSQL down -> "unavailable" (503).
        def build(response_format):
            if request.args.get("details", "").strip().lower() not in {"1", "true", "yes"}:
                return (
                    200,
                    catalog_serializers.health_to_dict(),
                    catalog_serializers.health_to_xml(),
                )

            database = _database_status()
            redis_up = gateway.ping()
            if database != "connected":
                status, http_status = "unavailable", 503
            elif not redis_up:
                status, http_status = "degraded", 200
            else:
                status, http_status = "ok", 200

            details = {
                "status": status,
                "service": "library_soap_service",
                "database": database,
                "redis": "connected" if redis_up else "unavailable",
                "cache": "enabled" if redis_up else "bypassed",
                "metrics": gateway.metrics.snapshot(),
            }
            return (
                http_status,
                catalog_serializers.health_details_to_dict(details),
                catalog_serializers.health_details_to_xml(details),
            )

        return catalog_route(build)

    @app.get("/wsdl/library-classifier.wsdl")
    def wsdl():
        return send_from_directory(
            WSDL_DIR,
            "library-classifier.wsdl",
            mimetype="text/xml",
        )

    @app.get("/wsdl/library-classifier.xsd")
    def xsd():
        return send_from_directory(
            WSDL_DIR,
            "library-classifier.xsd",
            mimetype="application/xml",
        )

    @app.get("/uploads/libros/<path:filename>")
    def uploads_libros(filename: str):
        # imagenes_libro.url stores paths like "/uploads/libros/foo.jpg".
        # os.path.basename() strips any directory component (including
        # "../") before it ever reaches the filesystem, and
        # send_from_directory() independently refuses (404) to resolve
        # outside uploads_libros_dir even if that were bypassed. Together
        # this mirrors the same safe-join pattern already used by the
        # Node.js monolith (apps/web-monolito01/.../lib/uploadsFs.js).
        safe_filename = os.path.basename(filename)
        return send_from_directory(uploads_libros_dir, safe_filename)

    # ------------------------------------------------------------------
    # REST catalog endpoints (01_prompt_bilingue.md): bilingual XML/JSON,
    # format selected via ?format=json|xml (XML by default). Independent
    # of the SOAP contract below; see catalog/ for parsing-free data
    # access, business rules and serialization.
    # ------------------------------------------------------------------

    # Public reads (no JWT), cache-aside on Redis (catalog/cache.py).
    # Optional filter: ?q=<fragment of title or ISBN>, case-insensitive.

    @app.get("/books")
    def list_books():
        def build(response_format):
            books = books_cache.list_books(request.args.get("q"))
            return (
                200,
                catalog_serializers.books_to_dict(books),
                catalog_serializers.books_to_xml(books),
            )

        return catalog_route(build)

    @app.get("/books/<isbn>")
    def get_book(isbn: str):
        def build(response_format):
            normalized = catalog_validation.normalize_isbn(isbn)
            # The CHECK on libros.isbn guarantees no row can match a
            # malformed ISBN, so neither PostgreSQL nor Redis is asked.
            book = books_cache.get_book(normalized) if catalog_validation.is_valid_isbn(normalized) else None

            if book is None:
                raise book_not_found()

            return (
                200,
                catalog_serializers.book_to_dict(book),
                catalog_serializers.book_to_xml(book),
            )

        return catalog_route(build)

    # ------------------------------------------------------------------
    # Protected writes: Bearer access token + role ADMIN, checked by
    # library_shared (signature, HS256, exp, type=access, claims, Redis
    # revocation). 401 = not authenticated, 403 = not ADMIN, 503 = Redis
    # unavailable for the revocation check (fail closed).
    # Order: validate -> PostgreSQL commit -> invalidate cache.
    # ------------------------------------------------------------------

    def _book_body():
        return request.get_json(silent=True)

    def _write(operation) -> Response:
        """
        `operation()` validates and commits in PostgreSQL, then returns
        (status, isbn, json_payload, xml_bytes). Only if it returns (i.e.
        the commit happened) is the cache invalidated; any exception means
        rollback and no invalidation.
        """
        state = {"cache_invalidated": True}

        def build(response_format):
            status, isbn, json_payload, xml_bytes = operation()
            state["cache_invalidated"] = books_cache.invalidate(isbn)
            return status, json_payload, xml_bytes

        response = catalog_route(build)
        return _write_response(response, state["cache_invalidated"])

    @app.post("/books")
    @require_roles(ROLE_ADMIN)
    def create_book():
        def operation():
            isbn, values = catalog_validation.validate_create(_book_body())
            book = catalog_repository.create_book(isbn, values)
            return 201, isbn, catalog_serializers.book_to_dict(book), catalog_serializers.book_to_xml(book)

        return _write(operation)

    def _update(isbn: str, validate) -> Response:
        def operation():
            normalized = catalog_validation.normalize_isbn(isbn)
            values = validate(_book_body(), normalized)
            book = catalog_repository.update_book(normalized, values)
            if book is None:
                raise book_not_found()
            return 200, normalized, catalog_serializers.book_to_dict(book), catalog_serializers.book_to_xml(book)

        return _write(operation)

    @app.put("/books/<isbn>")
    @require_roles(ROLE_ADMIN)
    def replace_book(isbn: str):
        return _update(isbn, catalog_validation.validate_replace)

    @app.patch("/books/<isbn>")
    @require_roles(ROLE_ADMIN)
    def patch_book(isbn: str):
        return _update(isbn, catalog_validation.validate_patch)

    @app.delete("/books/<isbn>")
    @require_roles(ROLE_ADMIN)
    def delete_book(isbn: str):
        def operation():
            normalized = catalog_validation.normalize_isbn(isbn)
            if not catalog_repository.delete_book(normalized):
                raise book_not_found()
            return (
                200,
                normalized,
                catalog_serializers.book_deleted_to_dict(normalized),
                catalog_serializers.book_deleted_to_xml(normalized),
            )

        return _write(operation)

    @app.get("/cloud-concepts")
    def list_cloud_concepts():
        def build(response_format):
            rows = catalog_repository.list_cloud_concepts()
            return (
                200,
                catalog_serializers.cloud_concepts_to_dict(rows),
                catalog_serializers.cloud_concepts_to_xml(rows),
            )

        return catalog_route(build)

    @app.get("/books-with-images")
    def list_books_with_images():
        def build(response_format):
            books = catalog_repository.list_books_with_images()
            return (
                200,
                catalog_serializers.books_with_images_to_dict(books),
                catalog_serializers.books_with_images_to_xml(books),
            )

        return catalog_route(build)

    @app.post("/soap")
    def soap_endpoint():
        content_type = request.content_type or ""

        if not (
            content_type.startswith("text/xml")
            or content_type.startswith("application/xml")
        ):
            error = SoapServiceError(
                "INVALID_CONTENT_TYPE",
                "El servicio SOAP requiere XML.",
                415,
                "soap:Client",
            )
            return xml_response(
                build_fault(error),
                error.http_status,
            )

        try:
            operation, payload = parse_request(request.data)
            response_xml = dispatch(operation, payload)
            return xml_response(response_xml, 200)

        except SoapServiceError as exc:
            logger.warning(
                "SOAP Fault code=%s status=%s",
                exc.code,
                exc.http_status,
            )
            return xml_response(
                build_fault(exc),
                exc.http_status,
            )

        except Exception:
            # Detailed traceback belongs only to the server log.
            logger.exception("Unexpected SOAP service error")
            error = internal_error()
            return xml_response(
                build_fault(error),
                error.http_status,
            )

    return app


if __name__ == "__main__":
    try:
        settings = get_settings()
        application = create_app()
        application.run(
            host=settings.flask_host,
            port=settings.flask_port,
            debug=settings.flask_debug,
        )
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
