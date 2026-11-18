"""Create users and return their public account information."""

from uuid import uuid4

import aiosql
from psycopg.rows import dict_row

from .connection import PROJECT_ROOT, get_connection

queries = aiosql.from_path(
    PROJECT_ROOT / "sql" / "queries" / "users.sql",
    "psycopg",
)


def create_user(email, name, password_hash):
    user_id = uuid4()

    with get_connection() as connection:
        connection.row_factory = dict_row
        queries.create_user(
            connection,
            user_id=user_id,
            email=email,
            name=name,
            password_hash=password_hash,
        )
        user = next(queries.user_by_id(connection, user_id=user_id))

    return user


def get_user_by_email(email):
    with get_connection() as connection:
        connection.row_factory = dict_row
        return next(queries.user_credentials_by_email(connection, email=email), None)


def get_user_by_id(user_id):
    with get_connection() as connection:
        connection.row_factory = dict_row
        return next(queries.user_by_id(connection, user_id=user_id), None)
