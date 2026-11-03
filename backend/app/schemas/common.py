"""Common Pydantic schemas."""

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
    success: bool = True
