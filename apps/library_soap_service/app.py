import logging
from pathlib import Path

from flask import Flask, Response, request, send_from_directory

from catalog import repository as catalog_repository
from catalog import serializers as catalog_serializers
from catalog.errors import book_not_found
from catalog.http import catalog_route
from config.settings import ConfigurationError, get_settings
from soap.envelope import parse_request
from soap.faults import SoapServiceError, build_fault, internal_error
from soap.service import dispatch


BASE_DIR = Path(__file__).resolve().parent
WSDL_DIR = BASE_DIR / "wsdl"

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


def create_app() -> Flask:
    # Fail fast when required environment variables are missing.
    get_settings()

    app = Flask(__name__)

    @app.get("/health")
    def health():
        # Bilingual per 01_prompt_bilingue.md section 16: XML by default,
        # ?format=json for JSON. Does not affect POST /soap or the WSDL/XSD
        # routes, which keep their original SOAP/XML behavior.
        def build(response_format):
            return (
                200,
                catalog_serializers.health_to_dict(),
                catalog_serializers.health_to_xml(),
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

    # ------------------------------------------------------------------
    # REST catalog endpoints (01_prompt_bilingue.md): bilingual XML/JSON,
    # format selected via ?format=json|xml (XML by default). Independent
    # of the SOAP contract below; see catalog/ for parsing-free data
    # access, business rules and serialization.
    # ------------------------------------------------------------------

    @app.get("/books")
    def list_books():
        def build(response_format):
            books = catalog_repository.list_books()
            return (
                200,
                catalog_serializers.books_to_dict(books),
                catalog_serializers.books_to_xml(books),
            )

        return catalog_route(build)

    @app.get("/books/<isbn>")
    def get_book(isbn: str):
        def build(response_format):
            book = catalog_repository.get_book(isbn)

            if book is None:
                raise book_not_found()

            return (
                200,
                catalog_serializers.book_to_dict(book),
                catalog_serializers.book_to_xml(book),
            )

        return catalog_route(build)

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
