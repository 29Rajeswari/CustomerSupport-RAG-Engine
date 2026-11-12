from sqlalchemy import text
from app.db.session import SessionLocal

query = text("""
    SELECT
        d.product_id,
        d.title,
        d.category,
        d.status AS document_status,
        v.id AS version_id,
        v.version_number,
        v.status AS version_status,
        v.is_active,
        c.id AS chunk_id
    FROM documents d
    JOIN document_versions v ON v.document_id = d.id
    JOIN document_chunks c ON c.version_id = v.id
    WHERE d.product_id IN ('001', '002')
      AND d.status = 'active'
      AND v.status = 'active'
      AND v.is_active = TRUE
      AND c.embedding IS NOT NULL
    ORDER BY d.product_id, d.title, v.version_number DESC
""")

with SessionLocal() as db:
    for row in db.execute(query).mappings():
        print(dict(row))
