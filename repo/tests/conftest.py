"""
Shared pytest fixtures.
Uses in-memory SQLite so no files are created on disk.
"""
import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture(scope="session")
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        yield _db
        _db.session.rollback()


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def admin_token(client):
    """Register an admin user and return a Bearer token."""
    client.post("/api/v1/auth/register", json={
        "username": "test_admin",
        "password": "AdminPass1234!",
        "role": "Administrator",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "test_admin",
        "password": "AdminPass1234!",
    })
    return resp.json["token"]


@pytest.fixture(scope="function")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
