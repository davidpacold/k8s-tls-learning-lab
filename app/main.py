# app/main.py
from fastapi import FastAPI

app = FastAPI(title="Test App", version="1.0.0")


@app.get("/hello")
def hello():
    return {"message": "Hello, World!"}


@app.get("/goodbye")
def goodbye():
    return {"message": "Goodbye, World!"}


@app.get("/test")
def test_endpoint():
    return {"message": "Test endpoint OK", "status": "healthy"}
