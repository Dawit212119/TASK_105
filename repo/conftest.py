"""
Root conftest.py — executed by pytest before any test is collected.

Sets PYTHONPATH and required environment variables so that both
unit_tests/ and API_tests/ can import from app/ regardless of
the working directory.
"""
import os
import sys

# Make the Flask application package importable
_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if _REPO_DIR not in sys.path:
    sys.path.insert(0, _REPO_DIR)

# Point data-layer env vars at the repo's data/ tree
_DATA_DIR = os.path.join(_REPO_DIR, "data")
os.environ.setdefault("FERNET_KEY_PATH", os.path.join(_DATA_DIR, "keys", "secret.key"))
os.environ.setdefault("LOG_FILE",        os.path.join(_DATA_DIR, "logs", "app.jsonl"))
os.environ.setdefault("ATTACHMENT_DIR",  os.path.join(_DATA_DIR, "attachments"))

# Ensure the directories exist (safe even if already present)
os.makedirs(os.path.join(_DATA_DIR, "keys"),        exist_ok=True)
os.makedirs(os.path.join(_DATA_DIR, "logs"),         exist_ok=True)
os.makedirs(os.path.join(_DATA_DIR, "attachments"),  exist_ok=True)
