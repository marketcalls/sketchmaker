"""Authentication Pydantic schemas."""

from pydantic import BaseModel, field_validator

from app.schemas.user import USERNAME_ERROR, USERNAME_PATTERN, UserResponse
from app.utils.security import password_problem


def _checked_password(value: str) -> str:
    problem = password_problem(value)
    if problem:
        raise ValueError(problem)
    return value


class AuthSettingsResponse(BaseModel):
    """What the login page needs to know before anyone is signed in."""

    setup_required: bool
    # False on a public site, where the account is created in the terminal.
    web_setup: bool


class SetupRequest(BaseModel):
    """First run: create the owner."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not USERNAME_PATTERN.match(v):
            raise ValueError(USERNAME_ERROR)
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        return _checked_password(v)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    user: UserResponse
    message: str = "Login successful"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        return _checked_password(v)
