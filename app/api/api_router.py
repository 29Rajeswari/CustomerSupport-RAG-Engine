from fastapi import APIRouter

from app.api.routes.auth_routes import router as auth_router
from app.api.routes.admin_routes import router as admin_router
from app.api.routes.document_routes import router as documents_router
from app.api.routes.document_history_routes import router as document_history_router
from app.api.routes.chat_routes import router as chat_router
from app.api.routes.customer_routes import router as customer_router
from app.api.routes.product_routes import router as products_router

# Registration order matters: /documents/history must be registered
# after the document upload routes, exactly as before.
api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(documents_router)
api_router.include_router(document_history_router)
api_router.include_router(chat_router)
api_router.include_router(customer_router)
api_router.include_router(products_router)
