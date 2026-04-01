"""Constraints, indexes, and immutability triggers

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-31

What this migration adds on top of the baseline DDL (0001):

CHECK CONSTRAINTS  (via batch_alter_table — SQLite requires full table recreation)
  users               ck_users_role
  commission_rules    ck_commission_rate_bounds, ck_commission_cycle
  settlement_runs     ck_settlement_status, ck_settlement_period
  settlement_disputes ck_dispute_status, ck_dispute_amount
  inventory_lots      ck_lot_costing_method, ck_lot_qty_nonneg
  inventory_transactions  ck_inv_txn_type, ck_inv_txn_adjustment_reason
  cost_layers         ck_cost_layer_qty, ck_cost_layer_cost
  avg_cost_snapshots  ck_avg_cost_nonneg, ck_avg_cost_qty
  cycle_count_lines   ck_cycle_count_variance_reason
  messages            ck_message_type, ck_message_single_target
  message_receipts    ck_receipt_status
  content_items       ck_content_type, ck_content_status
  content_versions    ck_cv_status, ck_cv_version_positive
  attachments         ck_attachment_mime, ck_attachment_size, ck_attachment_single_owner
  capture_templates   ck_template_status
  template_versions   ck_tv_status, ck_tv_version_positive
  template_migrations ck_tmig_from_positive, ck_tmig_forward_only
  admin_tickets       ck_ticket_type, ck_ticket_status
  audit_log           ck_audit_action_type

UNIQUE CONSTRAINTS
  avg_cost_snapshots  uix_avg_cost_sku_wh   (sku_id, warehouse_id)
  message_receipts    uix_receipt_msg_recipient  (message_id, recipient_id)

NEW INDEXES
  sessions            ix_sessions_user_id           (user_id)
  products            ix_products_price_usd         (price_usd)
  product_attributes  ix_product_attributes_product_id (product_id)
  product_tags        ix_product_tags_product_id    (product_id)
  cost_layers         ix_cost_layers_fifo           (sku_id, warehouse_id, received_at)
  cycle_counts        ix_cycle_counts_warehouse     (warehouse_id)
  cycle_count_lines   ix_ccl_cycle_count            (cycle_count_id)
  content_versions    ix_cv_content_id              (content_id)
  template_versions   ix_tv_template_id             (template_id)
  template_migrations ix_tmig_template_id           (template_id)
  settlement_runs     ix_settlement_community       (community_id)
  settlement_disputes ix_dispute_settlement         (settlement_id)
  commission_rules    ix_commission_community       (community_id)
  messages            ix_messages_expires_at        (expires_at)

EXPRESSION INDEX (NULL-safe lot uniqueness)
  inventory_lots      uix_lot_location
      ON inventory_lots(sku_id, warehouse_id, COALESCE(bin_id,''), COALESCE(lot_number,''))

SQLITE TRIGGERS
  trg_lot_costing_immutable     — prevents costing_method change after first transaction
  products_fts_ai / _au / _ad   — keeps products_fts FTS5 table in sync with products rows

DOWNGRADE
  Drops all triggers, indexes, and expression index.
  Uses batch_alter_table to recreate affected tables without the check/unique constraints.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_BATCH_NAMING = {"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s"}


def _batch(table: str):
    """Return a context manager for batch_alter_table (SQLite constraint recreation)."""
    return op.batch_alter_table(table, schema=None)


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade():
    # ---- new plain indexes (always safe; no data movement needed) ----------

    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_products_price_usd", "products", ["price_usd"])
    op.create_index("ix_product_attributes_product_id", "product_attributes", ["product_id"])
    op.create_index("ix_product_tags_product_id", "product_tags", ["product_id"])
    op.create_index("ix_cost_layers_fifo", "cost_layers", ["sku_id", "warehouse_id", "received_at"])
    op.create_index("ix_cycle_counts_warehouse", "cycle_counts", ["warehouse_id"])
    op.create_index("ix_ccl_cycle_count", "cycle_count_lines", ["cycle_count_id"])
    op.create_index("ix_cv_content_id", "content_versions", ["content_id"])
    op.create_index("ix_tv_template_id", "template_versions", ["template_id"])
    op.create_index("ix_tmig_template_id", "template_migrations", ["template_id"])
    op.create_index("ix_settlement_community", "settlement_runs", ["community_id"])
    op.create_index("ix_dispute_settlement", "settlement_disputes", ["settlement_id"])
    op.create_index("ix_commission_community", "commission_rules", ["community_id"])
    op.create_index("ix_messages_expires_at", "messages", ["expires_at"])

    # ---- expression index: NULL-safe lot uniqueness -----------------------
    # COALESCE turns NULL bin_id / lot_number into '' so that two rows with the
    # same sku+warehouse+no-bin+no-lot-number are correctly treated as duplicates.
    op.execute(
        "CREATE UNIQUE INDEX uix_lot_location "
        "ON inventory_lots(sku_id, warehouse_id, COALESCE(bin_id,''), COALESCE(lot_number,''))"
    )

    # ---- CHECK constraints via batch_alter_table --------------------------
    # SQLite does not support ADD CONSTRAINT via ALTER TABLE; Alembic's
    # batch_alter_table handles this by recreating the table transparently.

    with _batch("users") as b:
        b.create_check_constraint(
            "ck_users_role",
            "role IN ('Administrator','Operations Manager','Moderator',"
            "'Group Leader','Staff','Member')",
        )

    with _batch("commission_rules") as b:
        b.create_check_constraint(
            "ck_commission_rate_bounds",
            "floor >= 0 AND ceiling <= 15 AND floor <= rate AND rate <= ceiling",
        )
        b.create_check_constraint(
            "ck_commission_cycle",
            "settlement_cycle IN ('weekly','biweekly')",
        )

    with _batch("settlement_runs") as b:
        b.create_check_constraint(
            "ck_settlement_status",
            "status IN ('pending','processing','completed','disputed','cancelled')",
        )
        b.create_check_constraint(
            "ck_settlement_period",
            "period_end >= period_start",
        )

    with _batch("settlement_disputes") as b:
        b.create_check_constraint(
            "ck_dispute_status",
            "status IN ('open','resolved','rejected')",
        )
        b.create_check_constraint("ck_dispute_amount", "disputed_amount >= 0")

    with _batch("inventory_lots") as b:
        b.create_check_constraint(
            "ck_lot_costing_method",
            "costing_method IN ('fifo','moving_average')",
        )
        b.create_check_constraint("ck_lot_qty_nonneg", "on_hand_qty >= 0")

    with _batch("inventory_transactions") as b:
        b.create_check_constraint(
            "ck_inv_txn_type",
            "type IN ('receipt','issue','transfer','adjustment')",
        )
        b.create_check_constraint(
            "ck_inv_txn_adjustment_reason",
            "type != 'adjustment' OR (reason IS NOT NULL AND reason != '')",
        )

    with _batch("cost_layers") as b:
        b.create_check_constraint("ck_cost_layer_qty", "quantity_remaining >= 0")
        b.create_check_constraint("ck_cost_layer_cost", "unit_cost_usd >= 0")

    with _batch("avg_cost_snapshots") as b:
        b.create_unique_constraint("uix_avg_cost_sku_wh", ["sku_id", "warehouse_id"])
        b.create_check_constraint("ck_avg_cost_nonneg", "avg_cost_usd >= 0")
        b.create_check_constraint("ck_avg_cost_qty", "on_hand_qty >= 0")

    with _batch("cycle_count_lines") as b:
        b.create_check_constraint(
            "ck_cycle_count_variance_reason",
            "variance = 0 OR (variance_reason IS NOT NULL AND variance_reason != '')",
        )

    with _batch("messages") as b:
        b.create_check_constraint(
            "ck_message_type",
            "type IN ('text','image_meta','file_meta','emoji','system')",
        )
        b.create_check_constraint(
            "ck_message_single_target",
            "NOT (recipient_id IS NOT NULL AND group_id IS NOT NULL)",
        )

    with _batch("message_receipts") as b:
        b.create_unique_constraint(
            "uix_receipt_msg_recipient", ["message_id", "recipient_id"]
        )
        b.create_check_constraint(
            "ck_receipt_status",
            "status IN ('sent','delivered','read')",
        )

    with _batch("content_items") as b:
        b.create_check_constraint(
            "ck_content_type",
            "type IN ('article','book','chapter')",
        )
        b.create_check_constraint(
            "ck_content_status",
            "status IN ('draft','published')",
        )

    with _batch("content_versions") as b:
        b.create_check_constraint(
            "ck_cv_status",
            "status IN ('draft','published')",
        )
        b.create_check_constraint("ck_cv_version_positive", "version >= 1")

    with _batch("attachments") as b:
        b.create_check_constraint(
            "ck_attachment_mime",
            "mime_type IN ('image/png','image/jpeg','application/pdf','text/plain','text/markdown')",
        )
        b.create_check_constraint(
            "ck_attachment_size",
            "size_bytes > 0 AND size_bytes <= 26214400",
        )
        b.create_check_constraint(
            "ck_attachment_single_owner",
            "(content_id IS NOT NULL) != (template_id IS NOT NULL)",
        )

    with _batch("capture_templates") as b:
        b.create_check_constraint(
            "ck_template_status",
            "status IN ('draft','published')",
        )

    with _batch("template_versions") as b:
        b.create_check_constraint(
            "ck_tv_status",
            "status IN ('draft','published')",
        )
        b.create_check_constraint("ck_tv_version_positive", "version >= 1")

    with _batch("template_migrations") as b:
        b.create_check_constraint("ck_tmig_from_positive", "from_version >= 1")
        b.create_check_constraint("ck_tmig_forward_only", "to_version > from_version")

    with _batch("admin_tickets") as b:
        b.create_check_constraint(
            "ck_ticket_type",
            "type IN ('moderation','report','other')",
        )
        b.create_check_constraint(
            "ck_ticket_status",
            "status IN ('open','in_progress','closed')",
        )

    with _batch("audit_log") as b:
        b.create_check_constraint(
            "ck_audit_action_type",
            "action_type IN ('settlement','moderation','inventory','auth','content','template')",
        )

    # ---- SQLite triggers ---------------------------------------------------

    # Costing method immutability (design.md §3.5, questions.md Q8):
    # Fires BEFORE UPDATE OF costing_method and aborts if any transaction already
    # references this lot.
    op.execute("""
        CREATE TRIGGER trg_lot_costing_immutable
        BEFORE UPDATE OF costing_method ON inventory_lots
        WHEN EXISTS (
            SELECT 1 FROM inventory_transactions WHERE lot_id = OLD.lot_id LIMIT 1
        )
        BEGIN
            SELECT RAISE(ABORT,
                'costing_method_locked: cannot change after transactions exist');
        END
    """)

    # FTS5 content-table sync triggers (design.md §3.4):
    # The products_fts virtual table uses content=products, so SQLite does NOT
    # automatically keep it in sync — these triggers are required.
    op.execute("""
        CREATE TRIGGER products_fts_ai
        AFTER INSERT ON products BEGIN
            INSERT INTO products_fts(rowid, name, brand, description)
            VALUES (new.rowid, new.name, new.brand, new.description);
        END
    """)

    op.execute("""
        CREATE TRIGGER products_fts_au
        AFTER UPDATE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name, brand, description)
            VALUES ('delete', old.rowid, old.name, old.brand, old.description);
            INSERT INTO products_fts(rowid, name, brand, description)
            VALUES (new.rowid, new.name, new.brand, new.description);
        END
    """)

    op.execute("""
        CREATE TRIGGER products_fts_ad
        AFTER DELETE ON products BEGIN
            INSERT INTO products_fts(products_fts, rowid, name, brand, description)
            VALUES ('delete', old.rowid, old.name, old.brand, old.description);
        END
    """)


# ---------------------------------------------------------------------------
# downgrade — reverses everything added above
# ---------------------------------------------------------------------------

def downgrade():
    # Drop triggers first (no dependencies)
    op.execute("DROP TRIGGER IF EXISTS trg_lot_costing_immutable")
    op.execute("DROP TRIGGER IF EXISTS products_fts_ai")
    op.execute("DROP TRIGGER IF EXISTS products_fts_au")
    op.execute("DROP TRIGGER IF EXISTS products_fts_ad")

    # Drop expression index
    op.execute("DROP INDEX IF EXISTS uix_lot_location")

    # Drop plain indexes
    for ix in (
        "ix_sessions_user_id",
        "ix_products_price_usd",
        "ix_product_attributes_product_id",
        "ix_product_tags_product_id",
        "ix_cost_layers_fifo",
        "ix_cycle_counts_warehouse",
        "ix_ccl_cycle_count",
        "ix_cv_content_id",
        "ix_tv_template_id",
        "ix_tmig_template_id",
        "ix_settlement_community",
        "ix_dispute_settlement",
        "ix_commission_community",
        "ix_messages_expires_at",
    ):
        op.execute(f"DROP INDEX IF EXISTS {ix}")

    # Remove check constraints and unique constraints via batch (table recreation)

    with _batch("audit_log") as b:
        b.drop_constraint("ck_audit_action_type", type_="check")

    with _batch("admin_tickets") as b:
        b.drop_constraint("ck_ticket_type", type_="check")
        b.drop_constraint("ck_ticket_status", type_="check")

    with _batch("template_migrations") as b:
        b.drop_constraint("ck_tmig_from_positive", type_="check")
        b.drop_constraint("ck_tmig_forward_only", type_="check")

    with _batch("template_versions") as b:
        b.drop_constraint("ck_tv_status", type_="check")
        b.drop_constraint("ck_tv_version_positive", type_="check")

    with _batch("capture_templates") as b:
        b.drop_constraint("ck_template_status", type_="check")

    with _batch("attachments") as b:
        b.drop_constraint("ck_attachment_mime", type_="check")
        b.drop_constraint("ck_attachment_size", type_="check")
        b.drop_constraint("ck_attachment_single_owner", type_="check")

    with _batch("content_versions") as b:
        b.drop_constraint("ck_cv_status", type_="check")
        b.drop_constraint("ck_cv_version_positive", type_="check")

    with _batch("content_items") as b:
        b.drop_constraint("ck_content_type", type_="check")
        b.drop_constraint("ck_content_status", type_="check")

    with _batch("message_receipts") as b:
        b.drop_constraint("uix_receipt_msg_recipient", type_="unique")
        b.drop_constraint("ck_receipt_status", type_="check")

    with _batch("messages") as b:
        b.drop_constraint("ck_message_type", type_="check")
        b.drop_constraint("ck_message_single_target", type_="check")

    with _batch("cycle_count_lines") as b:
        b.drop_constraint("ck_cycle_count_variance_reason", type_="check")

    with _batch("avg_cost_snapshots") as b:
        b.drop_constraint("uix_avg_cost_sku_wh", type_="unique")
        b.drop_constraint("ck_avg_cost_nonneg", type_="check")
        b.drop_constraint("ck_avg_cost_qty", type_="check")

    with _batch("cost_layers") as b:
        b.drop_constraint("ck_cost_layer_qty", type_="check")
        b.drop_constraint("ck_cost_layer_cost", type_="check")

    with _batch("inventory_transactions") as b:
        b.drop_constraint("ck_inv_txn_type", type_="check")
        b.drop_constraint("ck_inv_txn_adjustment_reason", type_="check")

    with _batch("inventory_lots") as b:
        b.drop_constraint("ck_lot_costing_method", type_="check")
        b.drop_constraint("ck_lot_qty_nonneg", type_="check")

    with _batch("settlement_disputes") as b:
        b.drop_constraint("ck_dispute_status", type_="check")
        b.drop_constraint("ck_dispute_amount", type_="check")

    with _batch("settlement_runs") as b:
        b.drop_constraint("ck_settlement_status", type_="check")
        b.drop_constraint("ck_settlement_period", type_="check")

    with _batch("commission_rules") as b:
        b.drop_constraint("ck_commission_rate_bounds", type_="check")
        b.drop_constraint("ck_commission_cycle", type_="check")

    with _batch("users") as b:
        b.drop_constraint("ck_users_role", type_="check")
