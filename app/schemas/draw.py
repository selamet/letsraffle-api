from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from app.utils.draw_date import normalize_and_validate_draw_date


# Manual Draw Schemas

class ManualDrawParticipant(BaseModel):
    """Schema for manual draw participant with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(..., min_length=1, max_length=100, alias="firstName")
    last_name: str = Field(..., min_length=1, max_length=100, alias="lastName")
    email: EmailStr
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=50)


class ManualDrawCreate(BaseModel):
    """Schema for creating a manual draw with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    address_required: bool = Field(False, alias="addressRequired")
    phone_number_required: bool = Field(False, alias="phoneNumberRequired")
    language: str = Field("TR", alias="language", description="Language code (TR or EN)")
    participants: List[ManualDrawParticipant] = Field(
        ...,
        min_length=3,
        description="List of participants (minimum 3 required)"
    )

    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate that language is either TR or EN"""
        if v.upper() not in ['TR', 'EN']:
            raise ValueError("language must be either 'TR' or 'EN'")
        return v.upper()
    
    @model_validator(mode='after')
    def validate_required_fields(self):
        """Validate that required fields are present in all participants"""
        if self.address_required:
            for idx, participant in enumerate(self.participants):
                if not participant.address or not participant.address.strip():
                    raise ValueError(
                        f"address is required for all participants when addressRequired is true. "
                        f"Participant at index {idx} ({participant.first_name} {participant.last_name}) is missing address."
                    )
        
        if self.phone_number_required:
            for idx, participant in enumerate(self.participants):
                if not participant.phone or not participant.phone.strip():
                    raise ValueError(
                        f"phone is required for all participants when phoneNumberRequired is true. "
                        f"Participant at index {idx} ({participant.first_name} {participant.last_name}) is missing phone."
                    )
        
        return self


class ManualDrawResponse(BaseModel):
    """Schema for manual draw response with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    message: str
    draw_id: int = Field(..., alias="drawId")


# Dynamic Draw Schemas

class DynamicDrawParticipant(BaseModel):
    """Schema for dynamic draw participant (organizer) with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(..., min_length=1, max_length=100, alias="firstName")
    last_name: str = Field(..., min_length=1, max_length=100, alias="lastName")
    email: EmailStr
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=50)


class DynamicDrawCreate(BaseModel):
    """Schema for creating a dynamic draw with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    address_required: bool = Field(False, alias="addressRequired")
    phone_number_required: bool = Field(False, alias="phoneNumberRequired")
    language: str = Field("TR", alias="language", description="Language code (TR or EN)")
    draw_date: Optional[datetime] = Field(None, alias="drawDate")
    participants: List[DynamicDrawParticipant] = Field(
        ...,
        min_length=1,
        max_length=1,
        description="List with exactly 1 participant (the organizer)"
    )

    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate that language is either TR or EN"""
        if v.upper() not in ['TR', 'EN']:
            raise ValueError("language must be either 'TR' or 'EN'")
        return v.upper()

    @model_validator(mode='after')
    def validate_draw_date_and_organizer_required_fields(self):
        """
        Validate draw_date timezone handling and organizer required fields.
        
        Uses utility function to normalize timezone based on language.
        """
        if self.draw_date is not None:
            self.draw_date = normalize_and_validate_draw_date(self.draw_date, self.language)
        
        organizer = self.participants[0]
        
        if self.address_required:
            if not organizer.address or not organizer.address.strip():
                raise ValueError(
                    f"address is required when addressRequired is true. "
                    f"Organizer ({organizer.first_name} {organizer.last_name}) is missing address."
                )
        
        if self.phone_number_required:
            if not organizer.phone or not organizer.phone.strip():
                raise ValueError(
                    f"phone is required when phoneNumberRequired is true. "
                    f"Organizer ({organizer.first_name} {organizer.last_name}) is missing phone."
                )
        
        return self


class DynamicDrawResponse(BaseModel):
    """Schema for dynamic draw response with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    message: str
    draw_id: int = Field(..., alias="drawId")
    invite_code: str = Field(..., alias="inviteCode")


class ParticipantJoinRequest(BaseModel):
    """Schema for joining a draw via share link with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(..., min_length=1, max_length=100, alias="firstName")
    last_name: str = Field(..., min_length=1, max_length=100, alias="lastName")
    email: EmailStr
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=50)


class DrawPublicInfo(BaseModel):
    """Schema for public draw information with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    id: int
    require_address: bool = Field(..., alias="requireAddress")
    require_phone: bool = Field(..., alias="requirePhone")
    draw_date: Optional[datetime] = Field(None, alias="drawDate")
    status: str
    participant_count: int = Field(..., alias="participantCount")
    language: str = Field(..., alias="language")


# Organizer Draw Management Schemas

class ParticipantDetail(BaseModel):
    """Schema for participant detail with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    id: int
    first_name: str = Field(..., alias="firstName")
    last_name: str = Field(..., alias="lastName")
    email: EmailStr
    address: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime = Field(..., alias="createdAt")


class DrawListItem(BaseModel):
    """Schema for draw list item with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    id: int
    draw_type: str = Field(..., alias="drawType")
    status: str
    invite_code: Optional[str] = Field(None, alias="inviteCode")
    participant_count: int = Field(..., alias="participantCount")
    created_at: datetime = Field(..., alias="createdAt")
    draw_date: Optional[datetime] = Field(None, alias="drawDate")
    language: str = Field(..., alias="language")


class DrawDetailResponse(BaseModel):
    """Schema for draw detail (organizer only) with camelCase support"""
    model_config = ConfigDict(populate_by_name=True)

    id: int
    draw_type: str = Field(..., alias="drawType")
    status: str
    invite_code: Optional[str] = Field(None, alias="inviteCode")
    require_address: bool = Field(..., alias="requireAddress")
    require_phone: bool = Field(..., alias="requirePhone")
    draw_date: Optional[datetime] = Field(None, alias="drawDate")
    created_at: datetime = Field(..., alias="createdAt")
    language: str = Field(..., alias="language")
    participants: List[ParticipantDetail]


class UpdateDrawSchedule(BaseModel):
    """
    Schema for updating draw schedule with camelCase support.
    
    Note: Timezone normalization is handled in the API endpoint
    because this schema doesn't have access to the draw's language.
    """
    model_config = ConfigDict(populate_by_name=True)

    draw_date: Optional[datetime] = Field(None, alias="drawDate")
