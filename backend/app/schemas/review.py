from pydantic import BaseModel, Field, field_validator


class RequestRevisionRequest(BaseModel):
    general_comment: str = Field(min_length=1, max_length=2000)

    @field_validator("general_comment")
    @classmethod
    def require_non_blank_comment(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A revision comment is required.")
        return value
