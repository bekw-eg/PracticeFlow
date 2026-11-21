from fastapi import APIRouter

from app.api.v1 import audit, auth, disciplines, document_checks, groups, management, notifications, placeholders

api_router = APIRouter()
api_router.include_router(disciplines.router)
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(groups.router)
api_router.include_router(document_checks.router)
api_router.include_router(management.router)
api_router.include_router(notifications.router)
api_router.include_router(placeholders.router)
