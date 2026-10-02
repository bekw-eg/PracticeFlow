"""Bound multipart spooling before the DOCX endpoint receives an UploadFile."""
import re

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings


class DocumentSubmissionBodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        prefix = re.escape(settings.API_V1_PREFIX)
        upload_path = re.fullmatch(
            prefix + r"/document-checks/(?:teacher/submissions|student/assignments/[^/]+/submissions)/?",
            path,
        )
        if scope["type"] != "http" or scope.get("method") != "POST" or not upload_path:
            await self.app(scope, receive, send)
            return

        # Allow multipart framing while keeping all files/fields combined bounded.
        # The domain service independently enforces the exact original byte limit.
        limit = settings.DOCX_MAX_UPLOAD_BYTES + 64 * 1024
        rejection = JSONResponse(status_code=413, content={"detail": {
            "code": "DOCX_UPLOAD_TOO_LARGE", "message": "The DOCX exceeds the upload size limit.",
        }})
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    if int(value) > limit:
                        await rejection(scope, receive, send)
                        return
                except ValueError:
                    pass

        consumed = 0
        exceeded = False

        async def bounded_receive() -> Message:
            nonlocal consumed, exceeded
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    exceeded = True
                    # Starlette closes every partially spooled file for this
                    # exception. A generic HTTPException bypasses that cleanup.
                    raise MultiPartException("DOCX upload size limit exceeded")
            return message

        async def bounded_send(message: Message) -> None:
            if not exceeded:
                await send(message)

        await self.app(scope, bounded_receive, bounded_send)
        if exceeded:
            await rejection(scope, receive, send)
