
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.api_router import api_router
from app.config import settings


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Backend API for an Indian e-commerce support chatbot "
        "using local Ollama models and document-based retrieval."
    ),
    version="0.1.0",
)


# API routes
app.include_router(api_router)

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "application": settings.APP_NAME,
    }


# Keep the admin frontend mount after the API routers.
app.mount(
    "/admin",
    StaticFiles(
        directory=Path(__file__).parent / "static",
        html=True,
    ),
    name="admin",
)
