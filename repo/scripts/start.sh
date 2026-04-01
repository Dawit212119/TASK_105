#!/usr/bin/env bash
set -euo pipefail

# Generate Fernet key if none exists
KEY_PATH="${FERNET_KEY_PATH:-data/keys/secret.key}"
if [ ! -f "$KEY_PATH" ]; then
  echo "Generating new Fernet key at $KEY_PATH"
  python - <<'EOF'
import os
from cryptography.fernet import Fernet
key_path = os.environ.get("FERNET_KEY_PATH", "data/keys/secret.key")
os.makedirs(os.path.dirname(key_path), exist_ok=True)
with open(key_path, "wb") as f:
    f.write(Fernet.generate_key())
EOF
fi

# Run migrations
echo "Running Alembic migrations..."
flask db upgrade

# Start app via eventlet WSGI server
echo "Starting application..."
exec python -m flask run --host=0.0.0.0 --port=5000
