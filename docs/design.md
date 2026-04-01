# System Design

**System:** Neighborhood Commerce & Content Operations Management System
**Deployment:** Single-machine, offline, Docker-friendly
**Stack:** Python · Flask · SQLAlchemy · SQLite

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        Docker Container                       │
│                                                              │
│  ┌─────────────┐    ┌──────────────────┐   ┌─────────────┐  │
│  │  Flask App  │    │  Background Jobs │   │  SQLite DB  │  │
│  │  (REST API) │◄──►│  (APScheduler /  │◄─►│  (single    │  │
│  │  + STOMP WS │    │   Celery-lite)   │   │   file)     │  │
│  └─────────────┘    └──────────────────┘   └─────────────┘  │
│         ▲                                        ▲           │
│         │ HTTP/WS                                │           │
└─────────┼────────────────────────────────────────┼──────────┘
          │                                        │
     Clients                              Local FS (attachments,
                                           encryption key,
                                           structured logs)
```

**Key design decisions:**
- Single SQLite file satisfies ACID requirements for inventory movements and settlements via explicit transactions.
- Flask-SocketIO with STOMP protocol handles WebSocket messaging alongside the REST API in the same process.
- Background jobs run in-process (APScheduler) to avoid an external broker dependency; they handle message redelivery, slow-moving flagging, and attachment cleanup.
- All sensitive fields (password hashes, payout identifiers) are encrypted at rest using Fernet symmetric encryption with a locally stored key file.

---

## 2. Deployment

```
project/
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── models/              # SQLAlchemy ORM models
│   ├── routes/              # Blueprint-per-domain route handlers
│   ├── services/            # Business logic layer
│   ├── jobs/                # Background job definitions
│   ├── middleware/          # Auth, audit, correlation ID, RBAC
│   └── migrations/          # Alembic migration scripts
├── data/
│   ├── db.sqlite3
│   ├── attachments/         # Local file storage
│   ├── keys/                # Fernet key (gitignored, volume-mounted)
│   └── logs/                # Structured JSON logs
└── tests/
```

**Docker volume mounts:**
- `./data/db.sqlite3` — persists database
- `./data/keys/` — encryption key (never baked into image)
- `./data/attachments/` — uploaded files
- `./data/logs/` — structured log output

**Migration & rollback:** Alembic manages schema versions. Each deploy tags the application build version (`APP_VERSION` env var). Rollback = re-deploy prior image + `alembic downgrade` to matching revision. Inventory costing data and template versions are never destructively migrated.

---

## 3. Data Model

### 3.1 Users & Auth

```
Users
  user_id          UUID PK
  username         TEXT UNIQUE NOT NULL
  password_hash    TEXT NOT NULL          -- Fernet-encrypted bcrypt hash
  role             TEXT NOT NULL          -- enum: Administrator | Operations Manager |
                                          --   Moderator | Group Leader | Staff | Member
  failed_attempts  INTEGER DEFAULT 0
  locked_until     DATETIME NULL
  created_at       DATETIME NOT NULL
  deleted_at       DATETIME NULL

Sessions
  token_hash       TEXT PK
  user_id          UUID FK → Users
  expires_at       DATETIME NOT NULL
  created_at       DATETIME NOT NULL
```

**Auth rules:**
- Password: min 12 chars, bcrypt + salt, stored Fernet-encrypted.
- Lockout: 5 consecutive failures → `locked_until = now + 15 min`. Counter resets on success or expiry.
- Tokens: random 32-byte token, stored as SHA-256 hash in `Sessions`. No JWT (offline, no need for stateless tokens).

---

### 3.2 Communities & Service Areas

```
Communities
  community_id     UUID PK
  name             TEXT NOT NULL
  address_line1    TEXT NOT NULL
  address_line2    TEXT NULL
  city             TEXT NOT NULL
  state            CHAR(2) NOT NULL
  zip              TEXT NOT NULL          -- validated: 5 or 9 digit US ZIP
  service_hours    TEXT NOT NULL          -- JSON blob {day: "HH:MM-HH:MM"}
  fulfillment_scope TEXT NOT NULL
  created_at       DATETIME NOT NULL
  deleted_at       DATETIME NULL

ServiceAreas
  service_area_id  UUID PK
  community_id     UUID FK → Communities
  name             TEXT NOT NULL
  address_line1    TEXT NOT NULL
  city             TEXT NOT NULL
  state            CHAR(2) NOT NULL
  zip              TEXT NOT NULL
  notes            TEXT NULL
  created_at       DATETIME NOT NULL
  deleted_at       DATETIME NULL

GroupLeaderBindings
  binding_id       UUID PK
  community_id     UUID FK → Communities
  user_id          UUID FK → Users
  active           BOOLEAN NOT NULL DEFAULT TRUE
  bound_at         DATETIME NOT NULL
  unbound_at       DATETIME NULL

  -- Partial unique index: UNIQUE (community_id) WHERE active = TRUE
```

**Invariant:** Only one `active=TRUE` binding per `community_id` enforced via partial index. Replacement is atomic (single transaction: UPDATE old → INSERT new).

---

### 3.3 Commission Rules & Settlements

```
CommissionRules
  rule_id            UUID PK
  community_id       UUID FK → Communities
  product_category   TEXT NULL            -- NULL = community default
  rate               REAL NOT NULL        -- percent, 0–15
  floor              REAL NOT NULL        -- 0 ≤ floor ≤ rate
  ceiling            REAL NOT NULL        -- rate ≤ ceiling ≤ 15
  settlement_cycle   TEXT NOT NULL        -- weekly | biweekly
  created_at         DATETIME NOT NULL
  deleted_at         DATETIME NULL

  -- Resolution priority: category_rule > community_default (NULL category) > system default (6.0%)

SettlementRuns
  settlement_id      UUID PK
  community_id       UUID FK → Communities
  idempotency_key    TEXT UNIQUE NOT NULL
  status             TEXT NOT NULL        -- pending | processing | completed | disputed | cancelled
  period_start       DATE NOT NULL
  period_end         DATE NOT NULL
  total_order_value  REAL NOT NULL DEFAULT 0
  commission_amount  REAL NOT NULL DEFAULT 0
  created_at         DATETIME NOT NULL
  finalized_at       DATETIME NULL

SettlementDisputes
  dispute_id         UUID PK
  settlement_id      UUID FK → SettlementRuns
  filed_by           UUID FK → Users
  reason             TEXT NOT NULL
  disputed_amount    REAL NOT NULL
  status             TEXT NOT NULL        -- open | resolved | rejected
  resolution_notes   TEXT NULL
  created_at         DATETIME NOT NULL
  resolved_at        DATETIME NULL

  -- Disputes block settlement finalization while status = 'open'
  -- Filing window: created_at ≤ settlement.finalized_at + 2 days
```

---

### 3.4 Catalog

```
Products
  product_id       UUID PK
  sku              TEXT UNIQUE NOT NULL
  name             TEXT NOT NULL
  brand            TEXT NOT NULL
  category         TEXT NOT NULL
  description      TEXT NOT NULL          -- Markdown
  price_usd        REAL NOT NULL
  sales_volume     INTEGER NOT NULL DEFAULT 0
  created_at       DATETIME NOT NULL
  deleted_at       DATETIME NULL

ProductAttributes
  attribute_id     UUID PK
  product_id       UUID FK → Products
  key              TEXT NOT NULL
  value            TEXT NOT NULL

ProductTags
  tag_id           UUID PK
  product_id       UUID FK → Products
  tag              TEXT NOT NULL

SearchLogs
  log_id           UUID PK
  user_id          UUID FK → Users
  query            TEXT NOT NULL
  searched_at      DATETIME NOT NULL
  result_count     INTEGER NOT NULL

  -- Per-user cap: 50 entries. Oldest evicted when exceeded (DELETE WHERE rowid = MIN).
  -- Trending: aggregate SearchLogs WHERE searched_at >= NOW - 7 days,
  --   score = COUNT(*) / (1 + HOURS_SINCE_FIRST_IN_WINDOW / 168.0)
  -- Zero-result guidance: trigram similarity against Products.brand and ProductTags.tag
```

**Search performance:** FTS5 virtual table on `Products(name, brand, description)`. Indexed: `brand`, `category`, `price_usd`, `sales_volume`, `created_at`. Trending precomputed every 15 minutes by background job.

---

### 3.5 Inventory & Warehouse

```
Warehouses
  warehouse_id     UUID PK
  name             TEXT NOT NULL
  location         TEXT NOT NULL
  notes            TEXT NULL
  created_at       DATETIME NOT NULL

Bins
  bin_id           UUID PK
  warehouse_id     UUID FK → Warehouses
  bin_code         TEXT NOT NULL
  description      TEXT NULL
  UNIQUE (warehouse_id, bin_code)

InventoryLots
  lot_id           UUID PK
  sku_id           UUID FK → Products
  warehouse_id     UUID FK → Warehouses
  bin_id           UUID FK → Bins NULL
  lot_number       TEXT NULL
  serial_number    TEXT NULL
  on_hand_qty      INTEGER NOT NULL DEFAULT 0
  costing_method   TEXT NOT NULL          -- fifo | moving_average (immutable after first txn)
  safety_stock_threshold  INTEGER NOT NULL DEFAULT 0
  last_issue_at    DATETIME NULL          -- used for slow-moving flag (60-day no-issue)
  created_at       DATETIME NOT NULL

InventoryTransactions
  transaction_id   UUID PK
  type             TEXT NOT NULL          -- receipt | issue | transfer | adjustment
  sku_id           UUID FK → Products     -- indexed
  warehouse_id     UUID FK → Warehouses   -- indexed
  bin_id           UUID NULL
  lot_id           UUID FK → InventoryLots NULL
  quantity_delta   INTEGER NOT NULL       -- positive=in, negative=out
  reference        TEXT NULL
  reason           TEXT NULL              -- required for adjustments
  actor_id         UUID FK → Users
  occurred_at      DATETIME NOT NULL      -- indexed
  correlation_id   TEXT NOT NULL

CostLayers                               -- FIFO costing
  layer_id         UUID PK
  sku_id           UUID FK → Products
  warehouse_id     UUID FK → Warehouses
  quantity_remaining INTEGER NOT NULL
  unit_cost_usd    REAL NOT NULL
  received_at      DATETIME NOT NULL

AvgCostSnapshots                         -- Moving-average costing
  snapshot_id      UUID PK
  sku_id           UUID FK → Products
  warehouse_id     UUID FK → Warehouses
  avg_cost_usd     REAL NOT NULL
  on_hand_qty      INTEGER NOT NULL
  updated_at       DATETIME NOT NULL
```

**Costing immutability:** `costing_method` on `InventoryLots` is set on first receipt transaction. Subsequent UPDATE attempts raise `422 costing_method_locked`.

**Safety-stock alert:** Background job queries `InventoryLots WHERE on_hand_qty < safety_stock_threshold` every 10 minutes, writes to structured log and optionally creates an `AdminTicket` of type `report`.

**Slow-moving flag:** Background job flags SKUs where `last_issue_at < NOW - 60 days OR last_issue_at IS NULL AND created_at < NOW - 60 days`.

---

### 3.6 Messaging

```
Messages
  message_id       UUID PK
  type             TEXT NOT NULL          -- text | image_meta | file_meta | emoji | system
  sender_id        UUID FK → Users
  recipient_id     UUID FK → Users NULL   -- direct message
  group_id         UUID FK → Communities NULL  -- group message
  body             TEXT NULL              -- null for file/image types
  file_metadata    TEXT NULL              -- JSON: {filename, mime_type, size_bytes}
  sent_at          DATETIME NOT NULL
  expires_at       DATETIME NOT NULL      -- sent_at + 7 days for offline queue purge
  correlation_id   TEXT NOT NULL

MessageReceipts
  receipt_id       UUID PK
  message_id       UUID FK → Messages
  recipient_id     UUID FK → Users
  status           TEXT NOT NULL          -- sent | delivered | read
  updated_at       DATETIME NOT NULL
```

**Offline queue redelivery:** Background job polls `MessageReceipts WHERE status='sent' AND messages.expires_at > NOW` on exponential schedule: 1 min → 2 min → 4 min → ... → capped at 6 hours between retries. Purges messages past `expires_at`.

**Log policy:** Message `body` is excluded from all log output by default. Only `message_id`, `sender_id`, `type`, and `correlation_id` appear in logs.

---

### 3.7 Content & Templates

```
ContentItems
  content_id       UUID PK
  type             TEXT NOT NULL          -- article | book | chapter
  parent_id        UUID FK → ContentItems NULL  -- chapter → book
  title            TEXT NOT NULL
  current_version  INTEGER NOT NULL DEFAULT 1
  status           TEXT NOT NULL          -- draft | published
  created_by       UUID FK → Users
  created_at       DATETIME NOT NULL
  deleted_at       DATETIME NULL

ContentVersions
  version_id       UUID PK
  content_id       UUID FK → ContentItems
  version          INTEGER NOT NULL
  body             TEXT NOT NULL          -- sanitized Markdown/rich-text
  tags             TEXT NOT NULL          -- JSON array
  categories       TEXT NOT NULL          -- JSON array
  status           TEXT NOT NULL          -- draft | published
  published_at     DATETIME NULL
  created_by       UUID FK → Users
  created_at       DATETIME NOT NULL
  UNIQUE (content_id, version)

Attachments
  attachment_id    UUID PK
  content_id       UUID FK → ContentItems NULL
  template_id      UUID FK → CaptureTemplates NULL
  filename         TEXT NOT NULL
  mime_type        TEXT NOT NULL          -- png | jpg | pdf | txt | md
  size_bytes       INTEGER NOT NULL       -- max 26214400 (25 MB)
  sha256           TEXT NOT NULL
  local_path       TEXT NOT NULL
  created_by       UUID FK → Users
  created_at       DATETIME NOT NULL
  deleted_at       DATETIME NULL

CaptureTemplates
  template_id      UUID PK
  name             TEXT NOT NULL
  current_version  INTEGER NOT NULL DEFAULT 1
  status           TEXT NOT NULL          -- draft | published
  created_by       UUID FK → Users
  created_at       DATETIME NOT NULL
  deleted_at       DATETIME NULL

TemplateVersions
  tv_id            UUID PK
  template_id      UUID FK → CaptureTemplates
  version          INTEGER NOT NULL
  fields           TEXT NOT NULL          -- JSON array of field definitions
  status           TEXT NOT NULL          -- draft | published
  published_at     DATETIME NULL
  created_at       DATETIME NOT NULL
  UNIQUE (template_id, version)

TemplateMigrations
  migration_id     UUID PK
  template_id      UUID FK → CaptureTemplates
  from_version     INTEGER NOT NULL
  to_version       INTEGER NOT NULL
  field_mappings   TEXT NOT NULL          -- JSON: [{from_field, to_field, transform}]
  created_at       DATETIME NOT NULL
  UNIQUE (template_id, from_version, to_version)
```

**Content sanitization:** All `body` fields pass through a server-side Markdown/HTML sanitizer (allowlist of tags) before persistence.

**Attachment cleanup:** Background job runs daily, deletes files on disk where `deleted_at IS NOT NULL` and removes orphaned files in `attachments/` not referenced by any row.

**Template evolution rules** (enforced in `services/template_service.py`):
- Adding new fields with `required=false`: allowed without migration.
- All other structural changes require a `TemplateMigrations` record before publishing.
- On rollback, captures authored against newer versions remain parseable via the inverse migration mapping.

---

### 3.8 Audit Log

```
AuditLog
  log_id           UUID PK
  action_type      TEXT NOT NULL          -- settlement | moderation | inventory | auth | content
  actor_id         UUID FK → Users
  target_type      TEXT NOT NULL
  target_id        TEXT NOT NULL
  before_state     TEXT NULL              -- JSON snapshot (sensitive fields redacted)
  after_state      TEXT NULL              -- JSON snapshot
  occurred_at      DATETIME NOT NULL
  correlation_id   TEXT NOT NULL
```

- Append-only. No UPDATE or DELETE is permitted on this table (enforced by SQLite trigger).
- Covers: all settlement state changes, moderation ticket actions, inventory adjustments, auth lockout events, content publish/rollback operations.

---

### 3.9 Admin Tickets

```
AdminTickets
  ticket_id        UUID PK
  type             TEXT NOT NULL          -- moderation | report | other
  status           TEXT NOT NULL          -- open | in_progress | closed
  subject          TEXT NOT NULL
  body             TEXT NOT NULL
  target_type      TEXT NULL
  target_id        TEXT NULL
  created_by       UUID FK → Users
  created_at       DATETIME NOT NULL
  resolved_at      DATETIME NULL
  resolution_notes TEXT NULL
```

---

## 4. Access Control

### 4.1 Role Hierarchy

| Role | Scope |
|------|-------|
| Administrator | Full access to all resources |
| Operations Manager | Full access except user role changes and audit-log deletion |
| Moderator | Content moderation, ticket management; read-only on commerce data |
| Group Leader | Read/write own community performance; read catalog and inventory |
| Staff | Inventory receipts/issues/transfers/cycle counts; read catalog |
| Member | Search, content read, direct messaging |

### 4.2 Row-Level Scoping

Enforced in the service layer (not just route decorators):

- **Group Leader:** All commerce queries (`/settlements`, `/reports/group-leader-performance`, `/communities/:id/commission-rules`) are filtered to communities where an active binding exists for `current_user.user_id`.
- **Member:** Cannot access other users' search history, message threads, or community management endpoints.
- **Staff:** Inventory write access is not scoped by community; read access covers all warehouses.

### 4.3 Middleware Stack (per request)

```
Request
  → CorrelationIDMiddleware      # inject/propagate X-Correlation-ID
  → AuthMiddleware               # validate Bearer token, load user+role
  → RBACMiddleware               # check role against endpoint permission map
  → RowScopeFilter               # applied inside service methods
  → AuditMiddleware              # log critical mutations post-response
  → StructuredLogMiddleware      # emit JSON log (no message bodies)
Response
```

---

## 5. Security

### 5.1 Password Storage
- bcrypt with cost factor ≥ 12.
- Hash stored as Fernet-encrypted ciphertext in `Users.password_hash`.
- Fernet key read from `data/keys/secret.key` at startup; never logged.

### 5.2 Sensitive Field Encryption
- Fields encrypted at rest: `password_hash`, any payout identifier columns.
- Encryption/decryption handled transparently by SQLAlchemy `TypeDecorator` (`EncryptedText` type).
- Key rotation requires a one-time migration script (re-encrypt all rows with new key).

### 5.3 Input Validation
- All incoming JSON validated via Marshmallow schemas before hitting service layer.
- US ZIP: regex `^\d{5}(-\d{4})?$`.
- Barcode/RFID: format-validated (configurable pattern per type) but not verified against external registries.
- Attachment MIME: validated from magic bytes, not filename extension.

### 5.4 Log Sanitization
- `StructuredLogMiddleware` strips `body`, `password`, `password_hash`, `payout_*` keys from all log records.
- Message content (`Messages.body`) never appears in logs; only `message_id` and `type` are emitted.

---

## 6. Background Jobs

All jobs run via APScheduler in-process. Each job acquires a SQLite advisory lock (row in a `JobLocks` table) to prevent concurrent execution if multiple workers are ever introduced.

| Job | Schedule | Function |
|-----|----------|----------|
| Message redelivery | Every 1 min | Retry `sent` messages with exponential backoff; purge expired (>7 days) |
| Trending precompute | Every 15 min | Aggregate `SearchLogs` last 7 days, write scores to `TrendingCache` table |
| Safety-stock alert | Every 10 min | Query lots below threshold; write `AdminTicket` if not already open |
| Slow-moving flag | Daily 02:00 | Flag SKUs with no issue for 60+ days; update `InventoryLots.slow_moving` |
| Attachment cleanup | Daily 03:00 | Delete soft-deleted attachments from disk; remove orphaned files |

---

## 7. Observability

### 7.1 Structured Logs
JSON log lines emitted to `data/logs/app.jsonl`:
```json
{
  "timestamp": "2026-03-31T14:00:00Z",
  "level": "INFO",
  "correlation_id": "uuid",
  "span_id": "uuid",
  "user_id": "uuid|null",
  "method": "GET",
  "path": "/api/v1/search/products",
  "status_code": 200,
  "duration_ms": 47,
  "domain": "search"
}
```

### 7.2 Traceable Spans
A lightweight span context (no external tracing backend required) propagates `correlation_id` and `span_id` through:
- Incoming HTTP request headers → Flask `g` context
- SQLAlchemy `before_cursor_execute` event → query log
- Background job invocations (passed as argument)
- WebSocket STOMP frames (`correlation-id` header)

### 7.3 Performance Targets
- **Search P99 < 300 ms** on 50,000 products: achieved via FTS5 + covering indexes on filter columns + precomputed trending scores. Measured with structured log `duration_ms`.
- Slow queries (> 100 ms) are logged at `WARN` level with full query plan.

### 7.4 Health Endpoints
- `GET /health` — liveness (always fast, no DB query).
- `GET /health/ready` — readiness (checks DB write round-trip + job scheduler heartbeat).

---

## 8. Transactional Boundaries

SQLite WAL mode is enabled for concurrent reads during writes.

Critical operations wrapped in explicit `db.session` transactions:

| Operation | Transaction Scope |
|-----------|-------------------|
| Group leader binding swap | Deactivate old + insert new |
| Settlement run creation | Idempotency check + insert |
| Inventory receipt/issue/transfer | Lot update + transaction insert + cost layer update |
| Inventory adjustment | Lot update + transaction insert + audit log append |
| Content publish | Version status update + `current_version` bump |
| Template publish | Same as content + migration validation |

All transactions use `SERIALIZABLE` isolation for inventory and settlement paths (SQLite's default under WAL for write transactions).

---

## 9. API Versioning & Canary

- URL path versioning: `/api/v1/...`
- `APP_VERSION` environment variable injected at build time, returned in `GET /health`.
- Schema migrations are Alembic-managed; each migration tagged with the app version that requires it.
- Rollback procedure:
  1. Re-deploy prior Docker image.
  2. Run `alembic downgrade <revision>`.
  3. Inventory costing layers and template versions are never dropped by downgrade migrations — only additive changes are rolled back.
