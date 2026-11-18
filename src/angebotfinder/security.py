"""Password hashing and signed, expiring access tokens."""

import os
from datetime import datetime, timedelta, timezone

import jwt

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
ACCESS_TOKEN_MINUTES = 30
DUMMY_PASSWORD_HASH = password_hasher.hash("dummy-password-for-missing-account")


def hash_password(password):
    return password_hasher.hash(password)


def verify_password(password, password_hash):
    return password_hasher.verify(password, password_hash)


def get_token_secret():
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("Set JWT_SECRET_KEY in .env to a random secret of at least 32 characters.")
    return secret


def create_access_token(user_id):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now,
         "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES)},
        get_token_secret(),
        algorithm="HS256",
    )


def decode_access_token(token):
    return jwt.decode(
        token, get_token_secret(), algorithms=["HS256"],
        options={"require": ["sub", "iat", "exp"]},
    )
