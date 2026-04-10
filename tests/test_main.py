# tests/test_main.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_hello_returns_200():
    response = client.get("/hello")
    assert response.status_code == 200


def test_hello_returns_message():
    response = client.get("/hello")
    assert response.json() == {"message": "Hello, World!"}


def test_goodbye_returns_200():
    response = client.get("/goodbye")
    assert response.status_code == 200


def test_goodbye_returns_message():
    response = client.get("/goodbye")
    assert response.json() == {"message": "Goodbye, World!"}


def test_test_returns_200():
    response = client.get("/test")
    assert response.status_code == 200


def test_test_returns_message():
    response = client.get("/test")
    assert response.json() == {"message": "Test endpoint OK", "status": "healthy"}
