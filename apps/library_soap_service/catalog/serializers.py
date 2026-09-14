from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


def _text(parent: ET.Element, name: str, value: Any) -> None:
    element = ET.SubElement(parent, name)

    if value is None:
        element.text = ""
    elif isinstance(value, bool):
        element.text = "true" if value else "false"
    else:
        element.text = str(value)


def _to_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# --- health -------------------------------------------------------------

def health_to_dict() -> dict[str, Any]:
    return {"status": "ok", "service": "library_soap_service"}


def health_to_xml(status: str = "ok", service: str = "library_soap_service") -> bytes:
    root = ET.Element("health")
    _text(root, "status", status)
    _text(root, "service", service)
    return _to_bytes(root)


# --- books ----------------------------------------------------------------

def _book_fields(parent: ET.Element, book: dict[str, Any]) -> None:
    _text(parent, "isbn", book["isbn"])
    _text(parent, "titulo", book["titulo"])
    _text(parent, "anio_publicacion", book["anio_publicacion"])
    _text(parent, "precio", book["precio"])
    _text(parent, "stock", book["stock"])
    _text(parent, "categoria", book["categoria"])
    _text(parent, "formato", book["formato"])


def book_to_dict(book: dict[str, Any]) -> dict[str, Any]:
    return {
        "isbn": book["isbn"],
        "titulo": book["titulo"],
        "anio_publicacion": book["anio_publicacion"],
        "precio": str(book["precio"]),
        "stock": book["stock"],
        "categoria": book["categoria"],
        "formato": book["formato"],
    }


def book_to_xml(book: dict[str, Any]) -> bytes:
    root = ET.Element("book")
    _book_fields(root, book)
    return _to_bytes(root)


def books_to_dict(books: list[dict[str, Any]]) -> dict[str, Any]:
    return {"books": [book_to_dict(book) for book in books]}


def books_to_xml(books: list[dict[str, Any]]) -> bytes:
    root = ET.Element("books")
    for book in books:
        book_element = ET.SubElement(root, "book")
        _book_fields(book_element, book)
    return _to_bytes(root)


# --- cloud concepts ---------------------------------------------------------

def _cloud_concept_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "conceptId": row["concepto_id"],
        "concept": row["concepto"],
        "definition": row["definicion"],
        "isbn": row["isbn"],
        "bookTitle": row["titulo_libro"],
    }


def cloud_concepts_to_dict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cloudConcepts": [_cloud_concept_to_dict(row) for row in rows]}


def cloud_concepts_to_xml(rows: list[dict[str, Any]]) -> bytes:
    root = ET.Element("cloudConcepts")

    for row in rows:
        element = ET.SubElement(root, "cloudConcept")
        _text(element, "conceptId", row["concepto_id"])
        _text(element, "concept", row["concepto"])
        _text(element, "definition", row["definicion"])
        _text(element, "isbn", row["isbn"])
        _text(element, "bookTitle", row["titulo_libro"])

    return _to_bytes(root)


# --- books with images ----------------------------------------------------

def _book_with_images_to_dict(book: dict[str, Any]) -> dict[str, Any]:
    return {
        "isbn": book["isbn"],
        "title": book["titulo"],
        "images": [
            {
                "url": image["url"],
                "alt": image["texto_alternativo"],
                "order": image["orden"],
                "isCover": bool(image["es_portada"]),
            }
            for image in book["images"]
        ],
    }


def books_with_images_to_dict(books: list[dict[str, Any]]) -> dict[str, Any]:
    return {"books": [_book_with_images_to_dict(book) for book in books]}


def books_with_images_to_xml(books: list[dict[str, Any]]) -> bytes:
    root = ET.Element("books")

    for book in books:
        book_element = ET.SubElement(root, "book")
        _text(book_element, "isbn", book["isbn"])
        _text(book_element, "title", book["titulo"])

        images_element = ET.SubElement(book_element, "images")
        for image in book["images"]:
            image_element = ET.SubElement(images_element, "image")
            _text(image_element, "url", image["url"])
            _text(image_element, "alt", image["texto_alternativo"])
            _text(image_element, "order", image["orden"])
            _text(image_element, "isCover", bool(image["es_portada"]))

    return _to_bytes(root)


# --- errors -----------------------------------------------------------------

def error_to_dict(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def error_to_xml(code: str, message: str) -> bytes:
    root = ET.Element("error")
    _text(root, "code", code)
    _text(root, "message", message)
    return _to_bytes(root)
