from fastapi import HTTPException, status

from app.core.config import settings


DOCUMENT_CHECK_DISABLED = "DOCUMENT_CHECK_DISABLED"


def require_document_check_enabled() -> None:
    """Hide the document-check API when its rollout flag is off."""
    if settings.DOCUMENT_CHECK_ENABLED:
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": DOCUMENT_CHECK_DISABLED,
            "message": "Document checking is not enabled for this deployment.",
        },
    )
