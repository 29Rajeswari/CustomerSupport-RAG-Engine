import sys
from pathlib import Path

# Add the project root to Python's import path
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.db.session import engine


def migrate():
    print("Starting authentication schema migration...")

    with engine.begin() as connection:

        # -------------------------------------------------
        # 1. ADD USERNAME TO EXISTING CUSTOMERS
        # -------------------------------------------------

        connection.execute(text("""
            ALTER TABLE customers
            ADD COLUMN IF NOT EXISTS username VARCHAR(50);
        """))

        # Assign deterministic usernames to existing customers.
        connection.execute(text("""
            UPDATE customers
            SET username = 'customer_' || id::text
            WHERE username IS NULL OR BTRIM(username) = '';
        """))

        # Enforce required username.
        connection.execute(text("""
            ALTER TABLE customers
            ALTER COLUMN username SET NOT NULL;
        """))

        # Enforce unique usernames.
        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            ix_customers_username
            ON customers (username);
        """))

        print("Customers username migration completed.")

        # -------------------------------------------------
        # 2. ADD CUSTOMER ID TO CHAT LOGS
        # -------------------------------------------------

        connection.execute(text("""
            ALTER TABLE chat_logs
            ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        """))

        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS
            ix_chat_logs_customer_id
            ON chat_logs (customer_id);
        """))

        connection.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_chat_logs_customer_id'
                      AND conrelid = 'chat_logs'::regclass
                ) THEN
                    ALTER TABLE chat_logs
                    ADD CONSTRAINT fk_chat_logs_customer_id
                    FOREIGN KEY (customer_id)
                    REFERENCES customers(id)
                    ON DELETE SET NULL;
                END IF;
            END
            $$;
        """))

        print("Chat logs migration completed.")

        # -------------------------------------------------
        # 3. CREATE PENDING REGISTRATIONS
        # -------------------------------------------------

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS pending_registrations (
                id SERIAL PRIMARY KEY,
                email VARCHAR(254) NOT NULL,
                otp_hash VARCHAR(255) NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                verified_at TIMESTAMPTZ NULL,
                last_sent_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """))

        connection.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            ix_pending_registrations_email
            ON pending_registrations (email);
        """))

        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS
            ix_pending_registrations_expires_at
            ON pending_registrations (expires_at);
        """))

        print("Pending registrations table created.")

        # -------------------------------------------------
        # 4. CREATE ACTIVITY LOGS
        # -------------------------------------------------

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NULL,
                action VARCHAR(100) NOT NULL,
                details TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                CONSTRAINT fk_activity_logs_customer_id
                FOREIGN KEY (customer_id)
                REFERENCES customers(id)
                ON DELETE SET NULL
            );
        """))

        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS
            ix_activity_logs_customer_id
            ON activity_logs (customer_id);
        """))

        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS
            ix_activity_logs_action
            ON activity_logs (action);
        """))

        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS
            ix_activity_logs_created_at
            ON activity_logs (created_at);
        """))

        print("Activity logs table created.")

        # -------------------------------------------------
        # 5. VERIFY IMPORTANT RECORD COUNTS
        # -------------------------------------------------

        tables = [
            "customers",
            "chat_logs",
            "orders",
            "order_items",
            "shipments",
            "documents",
            "email_verifications",
            "pending_registrations",
            "activity_logs",
        ]

        print("\nDatabase record counts:")

        for table_name in tables:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one()

            print(f"{table_name}: {count}")

        print("\nExisting customer usernames:")

        customers = connection.execute(text("""
            SELECT id, username, email, is_email_verified
            FROM customers
            ORDER BY id;
        """)).mappings().all()

        for customer in customers:
            print(dict(customer))

    print("\nMigration completed successfully.")


if __name__ == "__main__":
    try:
        migrate()
    except Exception:
        print("\nMigration failed. Transaction rolled back.")
        raise

