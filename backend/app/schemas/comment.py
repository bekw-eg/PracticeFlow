import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateInlineCommentRequest(BaseModel):
    node_id: str
    start_offset: int = Field(ge=0)
    end_offset: int
    text_snapshot: str
    body: str


class CreateGeneralCommentRequest(BaseModel):
    body: str


class ReplyRequest(BaseModel):
    body: str


class CommentAuthorOut(BaseModel):
    id: uuid.UUID
    full_name: str

    model_config = {"from_attributes": True}


class CommentReplyOut(BaseModel):
    id: uuid.UUID
    author: CommentAuthorOut
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentOut(BaseModel):
    id: uuid.UUID
    report_version_id: uuid.UUID
    author: CommentAuthorOut
    is_general: bool
    node_id: str | None
    start_offset: int | None
    end_offset: int | None
    text_snapshot: str | None
    body: str
    status: Literal["OPEN", "RESOLVED"]
    anchor_status: Literal["valid", "invalid"] | None
    current_node_text: str | None
    created_at: datetime
    resolved_at: datetime | None
    replies: list[CommentReplyOut]

    model_config = {"from_attributes": True}
