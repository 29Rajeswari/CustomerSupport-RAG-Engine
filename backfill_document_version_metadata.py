
from pathlib import Path

from sqlalchemy import text

from app.db.session import engine


def backfill_version_metadata():
    update_sql = text("""
        UPDATE document_versions AS v
        SET
            file_path = d.file_path,
            file_type = LOWER(
                COALESCE(
                    NULLIF(v.file_type, ''),
                    NULLIF(d.file_type, ''),
                    NULLIF(
                        SUBSTRING(d.file_path FROM '\\.([^.]+)$'),
                        ''
                    )
                )
            ),
            product_id = d.product_id,
            category = d.category
        FROM documents AS d
        WHERE
            v.document_id = d.id
            AND (
                v.file_path IS NULL
                OR v.product_id IS NULL
                OR v.category IS NULL
                OR v.file_type IS NULL
            )
            AND EXISTS (
                SELECT 1
                FROM document_chunks AS c
                WHERE c.version_id = v.id
                GROUP BY c.version_id
                HAVING
                    COUNT(DISTINCT c.product_id) = 1
                    AND COUNT(DISTINCT c.category) = 1
                    AND MIN(c.product_id) = d.product_id
                    AND MIN(c.category) = d.category
            )
    """)

    verify_sql = text("""
        SELECT
            COUNT(*) AS total_versions,
            COUNT(file_path) AS versions_with_file_path,
            COUNT(file_type) AS versions_with_file_type,
            COUNT(product_id) AS versions_with_product_id,
            COUNT(category) AS versions_with_category
        FROM document_versions
    """)

    with engine.begin() as connection:
        result = connection.execute(update_sql)
        print("Versions updated:", result.rowcount)

        verification = connection.execute(verify_sql).one()

        print("\nMetadata verification:")
        print("Total versions:", verification.total_versions)
        print("File paths populated:", verification.versions_with_file_path)
        print("File types populated:", verification.versions_with_file_type)
        print("Product IDs populated:", verification.versions_with_product_id)
        print("Categories populated:", verification.versions_with_category)


if __name__ == "__main__":
    backfill_version_metadata()

