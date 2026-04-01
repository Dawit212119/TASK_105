# Neighborhood Commerce & Content Operations Management System

Backend service for a local group-leader commerce model with catalog/search, inventory, settlements, content/templates, messaging, and admin governance.

## Tech Stack

- Python, Flask, SQLAlchemy, Alembic
- SQLite (single-machine/offline deployment)
- Flask-SocketIO (messaging transport)
- APScheduler (background jobs)

## Core Capabilities

- Auth + RBAC with session token (`Bearer`) flow
- Communities, service areas, and group-leader bindings
- Commission rules, settlement runs, and disputes
- Catalog management + search/autocomplete/history/trending
- Multi-warehouse inventory with FIFO or moving-average costing
- Content/versioning/templates with publish/rollback + migrations
- Admin tickets, audit log, health/readiness, structured logs

## Project Layout

```text
repo/
├── app/                 # Flask application (routes, services, models, middleware, jobs)
├── migrations/          # Alembic migrations
├── scripts/             # Helper scripts (start, seed, migrate)
├── unit_tests/          # Unit tests (service/domain level)
├── API_tests/           # API functional tests (HTTP-level)
├── run_tests.sh         # One-click test runner (bash)
├── run_tests.ps1        # One-click test runner (PowerShell)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Prerequisites

- Docker
- Docker Compose

Useful endpoints:

- `GET /health`
- `GET /health/ready`
- API base: `/api/v1`

## Docker Run

From `repo/`:

```bash
docker compose up --build
```

Default mapping:

- App: `http://localhost:5000`
- DB and runtime data persisted via mounted `repo/data/*`

Stop the app:

```bash
docker compose down
```

## Local Development (no Docker)

```bash
cd repo
pip install -r requirements.txt
cp .env.example .env          # edit as needed
flask db upgrade
flask run --host 0.0.0.0 --port 5000
```

Set `FLASK_ENV=development` in `.env`. The Fernet key is auto-generated on first startup
if `FERNET_KEY_PATH` points to a writable path.

## Database and Seeding (Docker)

From `repo/`:

```bash
# run migrations inside the container
docker compose exec app sh -c "scripts/migrate.sh"

# seed data inside the container
docker compose exec app python scripts/seed.py
```

## Testing

One-click (recommended), from `repo/`:

```bash
# bash/Git-Bash
bash run_tests.sh

# PowerShell
powershell -ExecutionPolicy Bypass -File run_tests.ps1
```

Direct pytest:

```bash
python -m pytest unit_tests/ API_tests/ -v
python -m pytest unit_tests/ -v
python -m pytest API_tests/ -v
```

## Configuration

Use `.env.example` as the template. Key settings:

- `FLASK_ENV`
- `APP_VERSION`
- `DATABASE_URL`
- `FERNET_KEY_PATH`
- `LOG_FILE`
- `ATTACHMENT_DIR`
- `JOBS_ENABLED`

## Notes

- This project is designed for single-machine/offline operation.
- Background jobs are enabled by `JOBS_ENABLED=true`.
- Keep `data/keys/secret.key` private and out of source control.
