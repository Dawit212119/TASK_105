#!/usr/bin/env bash
set -euo pipefail

# Seeds the first Administrator account.
# Run once after a fresh migration.
python - <<'EOF'
from app import create_app
from app.services.auth_service import AuthService

app = create_app()
with app.app_context():
    user = AuthService.register(
        username="admin",
        password="AdminPass1234!",
        role="Administrator",
    )
    print(f"Seeded administrator: {user.username} ({user.user_id})")
EOF
