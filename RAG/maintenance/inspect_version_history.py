from sqlalchemy import text
from app.db.session import engine

query = text("""
    SELECT
        d.id AS document_id,
        d.title,
        v.id AS version_id,
        v.version_number,
        v.status,
        v.is_active,
        v.created_at AS version_created_at,
        COUNT(c.id) AS chunk_count,
        STRING_AGG(DISTINCT c.product_id, ', ') AS chunk_product_ids,
        STRING_AGG(DISTINCT c.category, ', ') AS chunk_categories
    FROM documents d
    JOIN document_versions v
        ON v.document_id = d.id
    LEFT JOIN document_chunks c
        ON c.version_id = v.id
    GROUP BY
        d.id, d.title, v.id, v.version_number,
        v.status, v.is_active, v.created_at
    ORDER BY d.id, v.version_number
""")

with engine.connect() as connection:
    for row in connection.execute(query).mappings():
        print(dict(row))
