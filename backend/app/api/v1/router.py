from fastapi import APIRouter

from app.api.v1 import audit, auth, comments, export, files, groups, internships, management, notifications, placeholders, profile, reports, review, templates, variables

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(groups.router)
api_router.include_router(templates.router)
api_router.include_router(internships.router)
api_router.include_router(reports.router)
api_router.include_router(review.router)
api_router.include_router(comments.router)
api_router.include_router(export.router)
api_router.include_router(files.router)
api_router.include_router(variables.router)
api_router.include_router(profile.router)
api_router.include_router(management.router)
api_router.include_router(notifications.router)
api_router.include_router(placeholders.router)
