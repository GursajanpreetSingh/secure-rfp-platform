import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Classification, Role


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=255)
    # No length rules on purpose: validation errors echo the input back, and authenticate()
    # already rejects empty or oversized passwords without leaking anything.
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    """What the API may reveal about a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    department: str | None
    clearance: Classification
