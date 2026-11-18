"""Save conversation turns and fetch per-user history."""

import aiosql
from psycopg.rows import dict_row

from .connection import PROJECT_ROOT, get_connection

queries = aiosql.from_path(PROJECT_ROOT / "sql" / "queries" / "chats.sql", "psycopg")


def get_chat_history(user_id, limit=3):
    with get_connection() as connection:
        connection.row_factory = dict_row
        return list(queries.recent_turns(connection, user_id=user_id, limit=limit))


def save_chat_turn(user_id, question, answer):
    with get_connection() as connection:
        queries.save_turn(connection, user_id=user_id, question=question, answer=answer)
