from typing import Annotated
from io import BytesIO
from PIL import Image
import logging


from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.config import get_jwt_auth_manager, get_s3_storage_client
from src.database import get_db, UserModel, UserProfileModel, UserGroupEnum
from src.database.models.accounts import GenderEnum
from src.exceptions import InvalidTokenError, TokenExpiredError
from src.schemas.profiles import (
    ProfileCreateSchema,
    ProfileResponseSchema,
    get_profile_create_schema
)
from src.security.http import get_token
from src.security.interfaces import JWTAuthManagerInterface
from src.storages.interfaces import S3StorageInterface

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user profile",
)
async def create_user_profile(
    user_id: int,
    token: Annotated[str, Depends(get_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
    jwt_manager: Annotated[
        JWTAuthManagerInterface,
        Depends(get_jwt_auth_manager),
    ],
    s3_client: Annotated[
        S3StorageInterface,
        Depends(get_s3_storage_client),
    ],
    profile_data: Annotated[
        ProfileCreateSchema,
        Depends(get_profile_create_schema),
    ],
) -> ProfileResponseSchema:
    """Create a profile for the authenticated user, or for another user by an admin."""
    try:
        payload = jwt_manager.decode_access_token(token)
    except TokenExpiredError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        ) from error
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        ) from error

    token_user_id = payload.get("user_id")
    if token_user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token.")

    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.group))
        .where(UserModel.id == token_user_id)
    )
    authenticated_user = result.scalars().first()
    if authenticated_user is None:
        raise HTTPException(status_code=401, detail="Invalid token.")

    if authenticated_user.id != user_id and not authenticated_user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile.",
        )

    result = await db.execute(
        select(UserModel)
        .options(joinedload(UserModel.group), joinedload(UserModel.profile))
        .where(UserModel.id == user_id)
    )
    user = result.scalars().first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    if user.profile is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile.",
        )

    avatar = profile_data.avatar
    contents = await avatar.read()

    image_format = Image.open(BytesIO(contents)).format
    suffix = ".png" if image_format == "PNG" else ".jpg"
    avatar_key = f"avatars/{user_id}_avatar{suffix}"

    try:
        await s3_client.upload_file(avatar_key, contents)
        avatar_url = await s3_client.get_file_url(avatar_key)
    except Exception as error:
        logger.exception(
            f"Avatar upload error: {type(error).__name__}: {error}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later.",
        ) from error

    profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=GenderEnum(profile_data.gender),
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_key,
    )
    try:
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    except SQLAlchemyError as error:
        logger.exception(
            f"Profile database error: {type(error).__name__}: {error}"
        )
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the profile.",
        ) from error

    return ProfileResponseSchema(
        id=profile.id,
        user_id=profile.user_id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        gender=profile.gender,
        date_of_birth=profile.date_of_birth,
        info=profile.info,
        avatar=avatar_url,
    )
