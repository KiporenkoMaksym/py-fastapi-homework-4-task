from datetime import date
from typing import Annotated

from fastapi import Depends, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, field_validator, ValidationError

from src.database.models.accounts import GenderEnum
from src.validation import validate_name, validate_image, validate_gender, validate_birth_date


class ProfileCreateSchema(BaseModel):
    """Multipart form schema used to create a user profile."""

    first_name: Annotated[str, Form(...)]
    last_name: Annotated[str, Form(...)]
    gender: Annotated[str, Form(...)]
    date_of_birth: Annotated[date, Form(...)]
    info: Annotated[str, Form(...)]
    avatar: Annotated[UploadFile, File(...)]

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_profile_name(cls, value: str) -> str:
        validate_name(value)
        return value.lower()

    @field_validator("gender")
    @classmethod
    def validate_profile_gender(cls, value: str) -> str:
        validate_gender(value)
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_profile_birth_date(cls, value: date) -> date:
        validate_birth_date(value)
        return value

    @field_validator("info")
    @classmethod
    def validate_profile_info(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Info field cannot be empty or contain only spaces.")
        return value.strip()

    @field_validator("avatar")
    @classmethod
    def validate_profile_avatar(cls, value: UploadFile) -> UploadFile:
        validate_image(value)
        return value


async def get_profile_create_schema(
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()],
    gender: Annotated[str, Form()],
    date_of_birth: Annotated[date, Form()],
    info: Annotated[str, Form()],
    avatar: Annotated[UploadFile, File()],
) -> ProfileCreateSchema:
    try:
        return ProfileCreateSchema(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=date_of_birth,
            info=info,
            avatar=avatar,
        )
    except ValidationError as error:
        errors = error.errors(
            include_context=False,
            include_input=False,
            include_url=False,
        )
        errors = [
            {**item, "loc": ("body", *item["loc"])}
            for item in errors
        ]
        raise RequestValidationError(errors) from error


class ProfileResponseSchema(BaseModel):
    """Public representation of a saved user profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: GenderEnum
    date_of_birth: date
    info: str
    avatar: str
