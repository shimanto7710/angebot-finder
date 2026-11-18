"""Registration, login and account profile endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation

from ..schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from ..dependencies import get_current_user
from ...database.users import create_user, get_user_by_email
from ...security import (
    ACCESS_TOKEN_MINUTES, DUMMY_PASSWORD_HASH, create_access_token,
    hash_password, verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(request: RegisterRequest):
    email = str(request.email).lower()
    password_hash = hash_password(request.password)

    try:
        return create_user(email=email, name=request.name, password_hash=password_hash)
    except UniqueViolation as error:
        if error.diag.constraint_name != "users_email_unique":
            raise

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        ) from error


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    user = get_user_by_email(str(request.email).lower())
    password_hash = user["password_hash"] if user else DUMMY_PASSWORD_HASH
    valid_password = verify_password(request.password, password_hash)
    if not user or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "access_token": create_access_token(user["id"]),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    }


@router.get("/me", response_model=UserResponse)
def current_user(user=Depends(get_current_user)):
    return user
