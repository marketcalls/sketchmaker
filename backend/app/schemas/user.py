"""User Pydantic schemas."""

from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
USERNAME_ERROR = "Username must be 3-30 characters, alphanumeric and underscores only"


class UserUpdate(BaseModel):
    """Profile changes."""

    username: Optional[str] = None
    selected_provider_id: Optional[int] = None
    selected_model_id: Optional[int] = None

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not USERNAME_PATTERN.match(v):
            raise ValueError(USERNAME_ERROR)
        return v


class UserResponse(BaseModel):
    """The signed-in owner."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class UserProfileResponse(UserResponse):
    """The owner with their prompt-enhancement model choice."""

    selected_provider_id: Optional[int] = None
    selected_model_id: Optional[int] = None
