"""
Real, DB-free unit tests for the /books-with-images serialization: given an
in-memory book (the shape produced by
catalog.repository.list_books_with_images()), do the XML and JSON
serializers actually emit isbn, titulo, autores/autor (in order),
anio_publicacion, precio and images/image with url/alt/order/isCover?

This does not touch PostgreSQL: it only feeds a hand-built dict (the same
shape the repository returns) directly into the serializers.
"""

import unittest
import xml.etree.ElementTree as ET

from catalog.serializers import books_with_images_to_dict, books_with_images_to_xml


SAMPLE_BOOKS = [
    {
        "isbn": "9781000000032",
        "titulo": "Fundamentos de Cloud Computing",
        "anio_publicacion": 2026,
        "precio": "350.00",
        "autores": ["Ana Torres", "Luis Mena"],
        "images": [
            {
                "url": "/uploads/libros/archivo.jpg",
                "texto_alternativo": "Portada de Fundamentos de Cloud Computing",
                "orden": 1,
                "es_portada": True,
            }
        ],
    },
    {
        "isbn": "9781000000000",
        "titulo": "Libro sin imagenes ni autores",
        "anio_publicacion": 2020,
        "precio": "10.00",
        "autores": [],
        "images": [],
    },
]


class BooksWithImagesXmlTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring(books_with_images_to_xml(SAMPLE_BOOKS))

    def test_root_and_book_count(self):
        self.assertEqual(self.root.tag, "books")
        self.assertEqual(len(self.root.findall("book")), 2)

    def test_first_book_scalar_fields(self):
        book = self.root.findall("book")[0]
        self.assertEqual(book.find("isbn").text, "9781000000032")
        self.assertEqual(book.find("titulo").text, "Fundamentos de Cloud Computing")
        self.assertEqual(book.find("anio_publicacion").text, "2026")
        self.assertEqual(book.find("precio").text, "350.00")

    def test_authors_are_present_in_order(self):
        book = self.root.findall("book")[0]
        autores = book.find("autores").findall("autor")
        self.assertEqual([a.text for a in autores], ["Ana Torres", "Luis Mena"])

    def test_book_with_no_authors_has_empty_autores_element(self):
        book = self.root.findall("book")[1]
        self.assertIsNotNone(book.find("autores"))
        self.assertEqual(book.find("autores").findall("autor"), [])

    def test_image_fields(self):
        book = self.root.findall("book")[0]
        image = book.find("images").find("image")
        self.assertEqual(image.find("url").text, "/uploads/libros/archivo.jpg")
        self.assertEqual(
            image.find("alt").text, "Portada de Fundamentos de Cloud Computing"
        )
        self.assertEqual(image.find("order").text, "1")
        self.assertEqual(image.find("isCover").text, "true")

    def test_book_with_no_images_has_empty_images_element(self):
        book = self.root.findall("book")[1]
        self.assertIsNotNone(book.find("images"))
        self.assertEqual(book.find("images").findall("image"), [])


class BooksWithImagesJsonTests(unittest.TestCase):
    def test_dict_shape(self):
        payload = books_with_images_to_dict(SAMPLE_BOOKS)
        book = payload["books"][0]

        self.assertEqual(book["isbn"], "9781000000032")
        self.assertEqual(book["titulo"], "Fundamentos de Cloud Computing")
        self.assertEqual(book["autores"], ["Ana Torres", "Luis Mena"])
        self.assertEqual(book["anio_publicacion"], 2026)
        self.assertEqual(book["precio"], "350.00")
        self.assertEqual(book["images"][0]["url"], "/uploads/libros/archivo.jpg")
        self.assertTrue(book["images"][0]["isCover"])


if __name__ == "__main__":
    unittest.main()
