
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings

from app.api.customer import router as customer_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.documents import router as documents_router
from app.api.chat import router as chat_router
from app.api.document_history import router as document_history_router

from app.api.products import router as products_router



app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Backend API for an Indian e-commerce support chatbot "
        "using local Ollama models and document-based retrieval."
    ),
    version="0.1.0",
)


# API routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(documents_router)
app.include_router(document_history_router)
app.include_router(chat_router)
app.include_router(customer_router)
app.include_router(products_router)

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
