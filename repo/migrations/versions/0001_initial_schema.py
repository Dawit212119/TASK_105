"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-31

Notes:
- Creates all tables defined in app/models/.
- Adds partial unique index on group_leader_bindings (community_id) WHERE active=1.
- Adds FTS5 virtual table products_fts for keyword search.
- Adds append-only trigger on audit_log.
- Enables SQLite WAL mode via PRAGMA (also done at connection time in extensions.py).
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --- Users & Sessions ---
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="Member"),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # --- Communities ---
    op.create_table(
        "communities",
        sa.Column("community_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("address_line1", sa.String(256), nullable=False),
        sa.Column("address_line2", sa.String(256), nullable=True),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("zip", sa.String(10), nullable=False),
        sa.Column("service_hours", sa.Text, nullable=False, server_default="{}"),
        sa.Column("fulfillment_scope", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "service_areas",
        sa.Column("service_area_id", sa.String(36), primary_key=True),
        sa.Column("community_id", sa.String(36), sa.ForeignKey("communities.community_id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("address_line1", sa.String(256), nullable=False),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("zip", sa.String(10), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "group_leader_bindings",
        sa.Column("binding_id", sa.String(36), primary_key=True),
        sa.Column("community_id", sa.String(36), sa.ForeignKey("communities.community_id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("bound_at", sa.DateTime, nullable=False),
        sa.Column("unbound_at", sa.DateTime, nullable=True),
    )
    # Partial unique index: only one active binding per community
    op.execute("CREATE UNIQUE INDEX uix_glb_active ON group_leader_bindings (community_id) WHERE active = 1")

    # --- Commission & Settlements ---
    op.create_table(
        "commission_rules",
        sa.Column("rule_id", sa.String(36), primary_key=True),
        sa.Column("community_id", sa.String(36), sa.ForeignKey("communities.community_id"), nullable=False),
        sa.Column("product_category", sa.String(128), nullable=True),
        sa.Column("rate", sa.Float, nullable=False, server_default="6.0"),
        sa.Column("floor", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("ceiling", sa.Float, nullable=False, server_default="15.0"),
        sa.Column("settlement_cycle", sa.String(16), nullable=False, server_default="weekly"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "settlement_runs",
        sa.Column("settlement_id", sa.String(36), primary_key=True),
        sa.Column("community_id", sa.String(36), sa.ForeignKey("communities.community_id"), nullable=False),
        sa.Column("idempotency_key", sa.String(256), unique=True, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("total_order_value", sa.Float, nullable=False, server_default="0"),
        sa.Column("commission_amount", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("finalized_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "settlement_disputes",
        sa.Column("dispute_id", sa.String(36), primary_key=True),
        sa.Column("settlement_id", sa.String(36), sa.ForeignKey("settlement_runs.settlement_id"), nullable=False),
        sa.Column("filed_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("disputed_amount", sa.Float, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
    )

    # --- Catalog ---
    op.create_table(
        "products",
        sa.Column("product_id", sa.String(36), primary_key=True),
        sa.Column("sku", sa.String(128), unique=True, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("brand", sa.String(128), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("price_usd", sa.Float, nullable=False),
        sa.Column("sales_volume", sa.Integer, nullable=False, server_default="0"),
        sa.Column("safety_stock_threshold", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_products_brand", "products", ["brand"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_sales_volume", "products", ["sales_volume"])
    op.create_index("ix_products_created_at", "products", ["created_at"])

    # FTS5 virtual table for full-text search
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS products_fts
        USING fts5(name, brand, description, content=products, content_rowid=rowid)
    """)

    op.create_table(
        "product_attributes",
        sa.Column("attribute_id", sa.String(36), primary_key=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.String(512), nullable=False),
    )
    op.create_table(
        "product_tags",
        sa.Column("tag_id", sa.String(36), primary_key=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("tag", sa.String(128), nullable=False),
    )
    op.create_index("ix_product_tags_tag", "product_tags", ["tag"])

    op.create_table(
        "search_logs",
        sa.Column("log_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("searched_at", sa.DateTime, nullable=False),
        sa.Column("result_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_search_logs_user_id", "search_logs", ["user_id"])
    op.create_index("ix_search_logs_searched_at", "search_logs", ["searched_at"])

    op.create_table(
        "trending_cache",
        sa.Column("term", sa.Text, primary_key=True),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("computed_at", sa.DateTime, nullable=False),
    )

    # --- Inventory ---
    op.create_table(
        "warehouses",
        sa.Column("warehouse_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("location", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "bins",
        sa.Column("bin_id", sa.String(36), primary_key=True),
        sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("bin_code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.UniqueConstraint("warehouse_id", "bin_code", name="uix_bin_code"),
    )
    op.create_table(
        "inventory_lots",
        sa.Column("lot_id", sa.String(36), primary_key=True),
        sa.Column("sku_id", sa.String(36), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("bin_id", sa.String(36), sa.ForeignKey("bins.bin_id"), nullable=True),
        sa.Column("lot_number", sa.String(128), nullable=True),
        sa.Column("serial_number", sa.String(128), nullable=True),
        sa.Column("on_hand_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("costing_method", sa.String(16), nullable=False),
        sa.Column("safety_stock_threshold", sa.Integer, nullable=False, server_default="0"),
        sa.Column("slow_moving", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("last_issue_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_inventory_lots_sku_id", "inventory_lots", ["sku_id"])
    op.create_index("ix_inventory_lots_warehouse_id", "inventory_lots", ["warehouse_id"])

    op.create_table(
        "inventory_transactions",
        sa.Column("transaction_id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("sku_id", sa.String(36), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("bin_id", sa.String(36), sa.ForeignKey("bins.bin_id"), nullable=True),
        sa.Column("lot_id", sa.String(36), sa.ForeignKey("inventory_lots.lot_id"), nullable=True),
        sa.Column("quantity_delta", sa.Integer, nullable=False),
        sa.Column("reference", sa.String(256), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
    )
    op.create_index("ix_inv_txn_sku_id", "inventory_transactions", ["sku_id"])
    op.create_index("ix_inv_txn_warehouse_id", "inventory_transactions", ["warehouse_id"])
    op.create_index("ix_inv_txn_occurred_at", "inventory_transactions", ["occurred_at"])

    op.create_table(
        "cost_layers",
        sa.Column("layer_id", sa.String(36), primary_key=True),
        sa.Column("sku_id", sa.String(36), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("quantity_remaining", sa.Integer, nullable=False),
        sa.Column("unit_cost_usd", sa.Float, nullable=False),
        sa.Column("received_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "avg_cost_snapshots",
        sa.Column("snapshot_id", sa.String(36), primary_key=True),
        sa.Column("sku_id", sa.String(36), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("avg_cost_usd", sa.Float, nullable=False),
        sa.Column("on_hand_qty", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "cycle_counts",
        sa.Column("cycle_count_id", sa.String(36), primary_key=True),
        sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("counted_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "cycle_count_lines",
        sa.Column("line_id", sa.String(36), primary_key=True),
        sa.Column("cycle_count_id", sa.String(36), sa.ForeignKey("cycle_counts.cycle_count_id"), nullable=False),
        sa.Column("sku_id", sa.String(36), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("bin_id", sa.String(36), sa.ForeignKey("bins.bin_id"), nullable=True),
        sa.Column("system_qty", sa.Integer, nullable=False),
        sa.Column("counted_qty", sa.Integer, nullable=False),
        sa.Column("variance", sa.Integer, nullable=False),
        sa.Column("variance_reason", sa.Text, nullable=True),
    )

    # --- Messaging ---
    op.create_table(
        "messages",
        sa.Column("message_id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("sender_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("communities.community_id"), nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("file_metadata", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
    )
    op.create_table(
        "message_receipts",
        sa.Column("receipt_id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.message_id"), nullable=False),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="sent"),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_message_receipts_message_id", "message_receipts", ["message_id"])

    # --- Content ---
    op.create_table(
        "content_items",
        sa.Column("content_id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("content_items.content_id"), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "content_versions",
        sa.Column("version_id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), sa.ForeignKey("content_items.content_id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
        sa.Column("categories", sa.Text, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("content_id", "version", name="uix_cv"),
    )
    op.create_table(
        "capture_templates",
        sa.Column("template_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "template_versions",
        sa.Column("tv_id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("capture_templates.template_id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("fields", sa.Text, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("template_id", "version", name="uix_tv"),
    )
    op.create_table(
        "template_migrations",
        sa.Column("migration_id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("capture_templates.template_id"), nullable=False),
        sa.Column("from_version", sa.Integer, nullable=False),
        sa.Column("to_version", sa.Integer, nullable=False),
        sa.Column("field_mappings", sa.Text, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("template_id", "from_version", "to_version", name="uix_tmig"),
    )
    op.create_table(
        "attachments",
        sa.Column("attachment_id", sa.String(36), primary_key=True),
        sa.Column("content_id", sa.String(36), sa.ForeignKey("content_items.content_id"), nullable=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("capture_templates.template_id"), nullable=True),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("local_path", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )

    # --- Audit ---
    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.String(36), primary_key=True),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("before_state", sa.Text, nullable=True),
        sa.Column("after_state", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
    )
    op.create_index("ix_audit_log_action_type", "audit_log", ["action_type"])
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])

    # Append-only trigger — prevents UPDATE and DELETE on audit_log
    op.execute("""
        CREATE TRIGGER audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only');
        END
    """)
    op.execute("""
        CREATE TRIGGER audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only');
        END
    """)

    # --- Admin Tickets ---
    op.create_table(
        "admin_tickets",
        sa.Column("ticket_id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
    )

    # --- Job Locks ---
    op.create_table(
        "job_locks",
        sa.Column("job_name", sa.String(64), primary_key=True),
        sa.Column("locked_at", sa.DateTime, nullable=False),
        sa.Column("locked_by", sa.String(64), nullable=False, server_default="scheduler"),
    )


def downgrade():
    # Drop in reverse dependency order
    # products_fts is a virtual table referencing products; must be dropped first
    op.execute("DROP TABLE IF EXISTS products_fts")
    for table in [
        "job_locks", "admin_tickets", "audit_log",
        "attachments", "template_migrations", "template_versions",
        "capture_templates", "content_versions", "content_items",
        "message_receipts", "messages",
        "cycle_count_lines", "cycle_counts",
        "avg_cost_snapshots", "cost_layers", "inventory_transactions",
        "inventory_lots", "bins", "warehouses",
        "trending_cache", "search_logs", "product_tags",
        "product_attributes", "products",
        "settlement_disputes", "settlement_runs", "commission_rules",
        "group_leader_bindings", "service_areas", "communities",
        "sessions", "users",
    ]:
        op.drop_table(table)
