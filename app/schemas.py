
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    message: str = Field(
        min_length=1,
        max_length=8000,
        description="The user's message.",
        examples=["Explain how electricity tariffs work."],
    )


class TokenUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    thought_tokens: int = Field(default=0, ge=0)
    tool_use_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)


class SourceCitation(BaseModel):
    document: str = Field(min_length=1)
    page: int = Field(ge=1)
    title: str | None = None


class ChatResponse(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    answer: str = Field(min_length=1)
    model: str = Field(min_length=1)
    usage: TokenUsage

    fallback_used: bool = False
    grounded: bool = False
    sources: list[SourceCitation] = Field(default_factory=list)
