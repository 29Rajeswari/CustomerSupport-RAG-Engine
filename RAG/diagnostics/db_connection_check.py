
from app.db.session import check_database_connection


if __name__ == "__main__":
    try:
        check_database_connection()
        print("SUCCESS: Python connected to PostgreSQL!")
    except Exception as exc:
        print("DATABASE CONNECTION FAILED")
        print(f"Error: {exc}")
        raise
