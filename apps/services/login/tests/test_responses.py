import json

import pytest
from flask import Flask

from utils.errors import ServiceError
from utils.responses import (
    error_response,
    get_response_format,
    respond,
    to_xml_bytes,
)


@pytest.fixture
def app():
    return Flask(__name__)


def test_default_format_is_xml_when_missing(app):
    with app.test_request_context("/login"):
        assert get_response_format() == "xml"


def test_default_format_is_xml_when_empty(app):
    with app.test_request_context("/login?format="):
        assert get_response_format() == "xml"


def test_format_query_param_selects_json(app):
    with app.test_request_context("/login?format=json"):
        assert get_response_format() == "json"


def test_format_query_param_selects_xml_explicitly(app):
    with app.test_request_context("/login?format=xml"):
        assert get_response_format() == "xml"


def test_format_query_param_is_case_insensitive(app):
    with app.test_request_context("/login?format=JSON"):
        assert get_response_format() == "json"


def test_unsupported_format_raises_service_error(app):
    with app.test_request_context("/login?format=csv"):
        with pytest.raises(ServiceError) as exc_info:
            get_response_format()
        assert exc_info.value.http_status == 400


def test_to_xml_bytes_serializes_nested_and_scalar_values():
    xml_bytes = to_xml_bytes(
        "response",
        {
            "success": True,
            "message": "Login successful",
            "user": {"id": 1, "email": "usuario@example.com"},
        },
    )
    xml_text = xml_bytes.decode("utf-8")

    assert "<response>" in xml_text
    assert "<success>true</success>" in xml_text
    assert "<message>Login successful</message>" in xml_text
    assert "<user><id>1</id><email>usuario@example.com</email></user>" in xml_text


def test_respond_json_sets_json_mimetype_and_body(app):
    with app.test_request_context("/"):
        response = respond("json", 200, {"success": True})
        assert response.mimetype == "application/json"
        assert json.loads(response.get_data(as_text=True)) == {"success": True}


def test_respond_xml_sets_xml_mimetype(app):
    with app.test_request_context("/"):
        response = respond("xml", 200, {"success": True})
        assert response.mimetype == "application/xml"
        assert b"<success>true</success>" in response.get_data()


def test_error_response_uses_error_http_status_and_message(app):
    error = ServiceError("INVALID_CREDENTIALS", "Invalid credentials", 401)

    with app.test_request_context("/"):
        response = error_response(error, "json")
        assert response.status_code == 401
        body = json.loads(response.get_data(as_text=True))
        assert body == {"success": False, "message": "Invalid credentials"}
