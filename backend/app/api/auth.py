from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.entities import User
from app.schemas.api import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])
DUMMY_PASSWORD_HASH = hash_password("Dummy-password-for-timing-only-123")


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, session: SessionDep) -> Token:
    if not get_settings().allow_public_registration:
        raise HTTPException(status_code=403, detail="Public registration is disabled")
    email = payload.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token, expires_at = create_access_token(str(user.id), role=user.role.value)
    return Token(access_token=token, expires_at=expires_at, user=UserRead.model_validate(user))


@router.post("/session", response_model=Token)
async def local_session(session: SessionDep) -> Token:
    """Issue a session for the auto-provisioned local operator (LOCAL_MODE only).

    Local mode targets trusted-LAN appliance installs; on shared deployments the
    flag stays off and this endpoint 404s, leaving credential login mandatory.
    """
    settings = get_settings()
    if not settings.local_mode:
        raise HTTPException(status_code=404, detail="Local session mode is disabled")
    user = await session.scalar(
        select(User).where(
            User.email == str(settings.local_operator_email), User.is_active.is_(True)
        )
    )
    if user is None:
        raise HTTPException(status_code=503, detail="Local operator is not provisioned yet")
    token, expires_at = create_access_token(str(user.id), role=user.role.value)
    return Token(access_token=token, expires_at=expires_at, user=UserRead.model_validate(user))


@router.post("/token", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    user = await session.scalar(select(User).where(User.email == form.username.lower()))
    valid_password = verify_password(
        form.password, user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    )
    if user is None or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    token, expires_at = create_access_token(str(user.id), role=user.role.value)
    return Token(access_token=token, expires_at=expires_at, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
