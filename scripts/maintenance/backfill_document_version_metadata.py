
from sqlalchemy import text

from app.db.session import engine


def backfill_version_metadata():
    update_sql = text("""
        UPDATE document_versions AS v
        SET
            file_path = d.file_path,
            file_type = LOWER(d.file_type),
            product_id = d.product_id,
            category = d.category
        FROM documents AS d
        WHERE
            v.document_id = d.id
            AND v.file_path IS NULL
            AND v.file_type IS NULL
            AND v.product_id IS NULL
            AND v.category IS NULL
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
            COUNT(*) AS total,
            COUNT(file_path) AS paths,
            COUNT(file_type) AS types,
            COUNT(product_id) AS products,
            COUNT(category) AS categories
        FROM document_versions
    """)

    with engine.begin() as connection:
        result = connection.execute(update_sql)

        print("Versions updated:", result.rowcount)

        verification = connection.execute(verify_sql).one()

        print("\nVerification:")
        print("Total versions:", verification.total)
        print("File paths:", verification.paths)
        print("File types:", verification.types)
        print("Product IDs:", verification.products)
        print("Categories:", verification.categories)


if __name__ == "__main__":
    backfill_version_metadata()
