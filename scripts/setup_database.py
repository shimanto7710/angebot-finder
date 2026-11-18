import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from angebotfinder.database.connection import get_connection


def run_sql(sql_path):
    sql = sql_path.read_text(encoding="utf-8")

    if not sql.strip():
        raise ValueError("The SQL file is empty.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)

    print(f"Successfully executed: {sql_path.name}")


def setup_database():
    sql_path = PROJECT_ROOT / "sql" / "schema.sql"
    run_sql(sql_path)


def main():
    setup_database()


if __name__ == "__main__":
    main()
