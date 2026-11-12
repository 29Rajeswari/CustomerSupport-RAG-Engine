
from sqlalchemy import text
from app.db.session import engine

migration = """
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN
        NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS email_verifications (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES customers(id) ON DELETE CASCADE,
    otp_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_email_verifications_customer_id
    ON email_verifications(customer_id);

CREATE INDEX IF NOT EXISTS ix_email_verifications_expires_at
    ON email_verifications(expires_at);
"""

with engine.begin() as connection:
    connection.execute(text(migration))

print("Email verification migration completed successfully.")
