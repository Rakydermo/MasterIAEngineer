from pydantic import BaseModel, Field, field_validator


class EstimationRequest(BaseModel):
    """Incoming request containing a meeting transcription to estimate."""

    transcription: str = Field(
        ...,
        min_length=50,
        max_length=50_000,
        description="Meeting transcription text",
    )

    @field_validator("transcription")
    @classmethod
    def reject_blank_transcription(cls, value: str) -> str:
        """Reject transcriptions made only of whitespace."""
        if not value.strip():
            raise ValueError("transcription must contain non-whitespace characters")
        return value


class TokenUsage(BaseModel):
    """Token consumption details from the LLM call."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class EstimationResponse(BaseModel):
    """Response containing the generated estimation and metadata."""

    estimation: str = Field(..., description="Generated software estimation in markdown")
    model: str = Field(..., description="LLM model used")
    provider: str = Field(..., description="LLM provider used")
    usage: TokenUsage
