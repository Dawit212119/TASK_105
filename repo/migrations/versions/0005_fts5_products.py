"""Add FTS5 virtual table and triggers for full-text product search

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-02
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create FTS5 content table backed by products
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS products_fts
        USING fts5(
            name,
            brand,
            description,
            content='products',
            content_rowid='rowid'
        )
        """
    )

    # 2. Populate from existing rows
    op.execute(
        """
        INSERT INTO products_fts(rowid, name, brand, description)
        SELECT rowid, name, COALESCE(brand, ''), COALESCE(description, '')
        FROM products
        """
    )

    # 3. AFTER INSERT trigger — keep FTS index in sync
    op.execute(
        """
        CREATE TRIGGER products_ai AFTER INSERT ON products BEGIN
            INSERT INTO products_fts(rowid, name, brand, description)
            VALUES (new.rowid, new.name, COALESCE(new.brand, ''), COALESCE(new.description, ''));
        END
        """
    )

    # 4. AFTER DELETE trigger — remove deleted row from FTS index
    op.execute(
        """
        CREATE TRIGGER products_ad AFTER DELETE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name, brand, description)
            VALUES ('delete', old.rowid, old.name, COALESCE(old.brand, ''), COALESCE(old.description, ''));
        END
        """
    )

    # 5. AFTER UPDATE trigger — delete old entry then insert updated entry
    op.execute(
        """
        CREATE TRIGGER products_au AFTER UPDATE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name, brand, description)
            VALUES ('delete', old.rowid, old.name, COALESCE(old.brand, ''), COALESCE(old.description, ''));
            INSERT INTO products_fts(rowid, name, brand, description)
            VALUES (new.rowid, new.name, COALESCE(new.brand, ''), COALESCE(new.description, ''));
        END
        """
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS products_au")
    op.execute("DROP TRIGGER IF EXISTS products_ad")
    op.execute("DROP TRIGGER IF EXISTS products_ai")
    op.execute("DROP TABLE IF EXISTS products_fts")
