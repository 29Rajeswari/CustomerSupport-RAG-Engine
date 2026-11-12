from sqlalchemy import text
from app.db.session import engine

# The current parent file belongs to these identifiable versions.
CURRENT_FILE_VERSION_IDS = [
    1, 2, 3, 12, 5, 6, 7, 8, 9, 10, 17, 21
]

# Only populate metadata when it is currently missing.
update_metadata = text("""
    UPDATE document_versions v
    SET
        product_id = COALESCE(v.product_id, chunks.product_id),
        category = COALESCE(v.category, chunks.category)
    FROM (
        SELECT
            version_id,
            MIN(product_id) AS product_id,
            MIN(category) AS category,
            COUNT(DISTINCT product_id) AS product_count,
            COUNT(DISTINCT category) AS category_count
        FROM document_chunks
        GROUP BY version_id
        HAVING COUNT(DISTINCT product_id) = 1
           AND COUNT(DISTINCT category) = 1
    ) chunks
    WHERE v.id = chunks.version_id
      AND (v.product_id IS NULL OR v.category IS NULL)
""")

update_current_files = text("""
    UPDATE document_versions v
    SET
        file_path = COALESCE(v.file_path, d.file_path),
        file_type = COALESCE(v.file_type, d.file_type)
    FROM documents d
    WHERE v.document_id = d.id
      AND v.id = ANY(:version_ids)
      AND (v.file_path IS NULL OR v.file_type IS NULL)
""")

with engine.begin() as connection:
    metadata_result = connection.execute(update_metadata)

    file_result = connection.execute(
        update_current_files,
        {"version_ids": CURRENT_FILE_VERSION_IDS},
    )

    print("Version metadata rows updated:", metadata_result.rowcount)
    print("Current file metadata rows updated:", file_result.rowcount)

print("Backfill completed.")
