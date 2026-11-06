"""
Device registration schemas
"""

from typing import List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceRegisterRequest(BaseModel):
    """Register or refresh a push token"""
    model_config = ConfigDict(populate_by_name=True)

    token: str = Field(..., min_length=8, max_length=255)
    platform: Literal["ios"] = "ios"
    language: str = "TR"
    participant_tokens: List[str] = Field(default_factory=list, alias="participantTokens", max_length=100)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v.upper() not in ["TR", "EN"]:
            raise ValueError("language must be either 'TR' or 'EN'")
        return v.upper()


class DeviceRegisterResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_linked: bool = Field(..., alias="userLinked")
    participant_count: int = Field(..., alias="participantCount")
