"""ASGI entrypoint: `uvicorn app.asgi:app --port 8001` (kept separate so importing create_app has no side effects)."""
from .main import create_app

app = create_app()
