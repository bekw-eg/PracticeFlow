from fastapi import APIRouter
from app.api.v1 import disciplines

from app.api.v1 import audit, auth, comments, document_checks, export, files, groups, internships, management, notifications, placeholders, profile, reports, review, templates, variables

api_router = APIRouter()
api_router.include_router(disciplines.router)
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(groups.router)
api_router.include_router(templates.router, deprecated=True)
api_router.include_router(document_checks.router)
api_router.include_router(internships.router, deprecated=True)
api_router.include_router(reports.router, deprecated=True)
api_router.include_router(review.router, deprecated=True)
api_router.include_router(comments.router, deprecated=True)
api_router.include_router(export.router, deprecated=True)
api_router.include_router(files.router, deprecated=True)
api_router.include_router(variables.router, deprecated=True)
api_router.include_router(profile.router)
api_router.include_router(management.router)
api_router.include_router(notifications.router)
api_router.include_router(placeholders.router)
