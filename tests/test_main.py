# tests/test_main.py
import os
import importlib
import pytest
from fastapi.testclient import TestClient


def make_client(service_name: str) -> TestClient:
    os.environ["SERVICE_NAME"] = service_name
    import app.main
    importlib.reload(app.main)
    from app.main import app
    return TestClient(app)


def test_hello_returns_200() -> None:
    client = make_client("api1")
    response = client.get("/hello")
    assert response.status_code == 200


def test_hello_includes_service_name() -> None:
    client = make_client("api1")
    response = client.get("/hello")
    assert response.json() == {"service": "api1", "message": "Hello, World!"}


def test_goodbye_returns_200() -> None:
    client = make_client("api2")
    response = client.get("/goodbye")
    assert response.status_code == 200


def test_goodbye_includes_service_name() -> None:
    client = make_client("api2")
    response = client.get("/goodbye")
    assert response.json() == {"service": "api2", "message": "Goodbye, World!"}


def test_test_returns_200() -> None:
    client = make_client("api3")
    response = client.get("/test")
    assert response.status_code == 200


def test_test_includes_service_name() -> None:
    client = make_client("api3")
    response = client.get("/test")
    assert response.json() == {"service": "api3", "message": "Test endpoint OK", "status": "healthy"}


def test_default_service_name() -> None:
    os.environ.pop("SERVICE_NAME", None)
    import app.main
    importlib.reload(app.main)
    from app.main import app
    client = TestClient(app)
    response = client.get("/hello")
    assert response.json()["service"] == "unknown"
