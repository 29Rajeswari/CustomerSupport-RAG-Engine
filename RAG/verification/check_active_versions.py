from sqlalchemy import text
from app.db.session import SessionLocal

query = text("""
    SELECT
        d.id AS document_id,
        d.title,
        d.product_id,
        d.category,
        d.status AS document_status,
        v.id AS version_id,
        v.version_number,
        v.status AS version_status,
        v.is_active,
        COUNT(c.id) AS chunk_count,
        COUNT(c.embedding) AS embedded_chunk_count
    FROM documents d
    JOIN document_versions v
        ON v.document_id = d.id
    LEFT JOIN document_chunks c
        ON c.version_id = v.id
    WHERE d.product_id IN ('001', '002')
    GROUP BY
        d.id, d.title, d.product_id, d.category,
        d.status, v.id, v.version_number,
        v.status, v.is_active
    ORDER BY d.product_id, d.id, v.version_number DESC
""")

with SessionLocal() as db:
    rows = db.execute(query).mappings().all()

    for row in rows:
        print(dict(row))
