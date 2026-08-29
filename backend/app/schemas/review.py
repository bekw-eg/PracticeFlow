from pydantic import BaseModel


class RequestRevisionRequest(BaseModel):
    general_comment: str | None = None
