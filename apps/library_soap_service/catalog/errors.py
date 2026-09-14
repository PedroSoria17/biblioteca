from dataclasses import dataclass


@dataclass
class CatalogError(Exception):
    """
    Controlled, bilingual-serializable error for the REST catalog endpoints
    (/books, /books/<isbn>, /cloud-concepts, /books-with-images, /health).

    Kept separate from soap.faults.SoapServiceError: the REST catalog and
    the SOAP module use different wire formats (plain XML/JSON vs SOAP
    Fault) and must not be coupled.
    """

    code: str
    message: str
    http_status: int = 400

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def invalid_format() -> CatalogError:
    return CatalogError(
        "INVALID_FORMAT",
        "Supported formats are xml and json",
        400,
    )


def book_not_found() -> CatalogError:
    return CatalogError("BOOK_NOT_FOUND", "Book not found", 404)


def internal_error() -> CatalogError:
    return CatalogError(
        "INTERNAL_ERROR",
        "An internal error occurred while processing the request.",
        500,
    )
