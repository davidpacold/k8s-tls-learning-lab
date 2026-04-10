# app/main.py
import os
from fastapi import FastAPI

SERVICE_NAME: str = os.getenv("SERVICE_NAME", "unknown")

app = FastAPI(title="Test App", version="1.0.0")


@app.get("/hello")
def hello() -> dict:
    return {"service": SERVICE_NAME, "message": "Hello, World!"}


@app.get("/goodbye")
def goodbye() -> dict:
    return {"service": SERVICE_NAME, "message": "Goodbye, World!"}


@app.get("/test")
def test_endpoint() -> dict:
    return {"service": SERVICE_NAME, "message": "Test endpoint OK", "status": "healthy"}
