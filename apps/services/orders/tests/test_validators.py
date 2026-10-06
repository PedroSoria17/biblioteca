from __future__ import annotations

import pytest

from utils.errors import ServiceError
from utils.validators import parse_create_order, parse_status


def test_lines_are_consolidated_normalized_and_sorted():
    body = {
        "items": [
            {"isbn": "9780000000002", "cantidad": 1},
            {"isbn": " 123456789x ", "cantidad": 2},
            {"isbn": "9780000000002", "cantidad": 4},
        ]
    }

    assert parse_create_order(body) == {"123456789X": 2, "9780000000002": 5}
    assert list(parse_create_order(body)) == ["123456789X", "9780000000002"]


@pytest.mark.parametrize("isbn", ["978-0-13-468599-1", "0134685997", "013468599X"])
def test_valid_isbn_formats(isbn):
    assert parse_create_order({"items": [{"isbn": isbn, "cantidad": 1}]}) == {isbn: 1}


def test_status_values_come_from_the_schema():
    assert parse_status({"estado": "Completed"}) == "completed"
    with pytest.raises(ServiceError):
        parse_status({"estado": "shipped"})
