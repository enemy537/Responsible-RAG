"""FastAPI application entry point.

Run locally:  uvicorn app:app --reload --port 8000
Run via Docker:  docker compose up
"""

from dotenv import load_dotenv

load_dotenv()  # Must run before importing anything that reads env vars

from src.api import create_app  # noqa: E402

app = create_app()
