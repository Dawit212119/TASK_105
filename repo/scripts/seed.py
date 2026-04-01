"""
Seed script — populates a fresh database with representative fixtures.

Usage:
    cd repo/
    python scripts/seed.py

Idempotent: running twice is safe (duplicate registrations are silently skipped).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

os.makedirs("data/keys", exist_ok=True)
os.makedirs("data/logs", exist_ok=True)
os.makedirs("data/attachments", exist_ok=True)

# Generate Fernet key if not present
key_path = "data/keys/secret.key"
if not os.path.exists(key_path):
    from cryptography.fernet import Fernet
    with open(key_path, "wb") as kf:
        kf.write(Fernet.generate_key())
    print(f"  Generated Fernet key at {key_path}")

app = create_app(os.environ.get("FLASK_ENV", "development"))


def _post(client, path, json=None, headers=None):
    resp = client.post(path, json=json or {}, headers=headers or {})
    return resp


def seed():
    # Schema is owned by Alembic migrations only — never db.create_all() here,
    # or Docker restarts can end up with tables but no alembic_version row.

    with app.test_client() as client:
        # ----------------------------------------------------------------
        # 1. Users
        # ----------------------------------------------------------------
        users = [
            {"username": "admin",     "password": "AdminPass1234!",   "role": "Administrator"},
            {"username": "opsmanager", "password": "OpsPass1234!",    "role": "Operations Manager"},
            {"username": "moderator", "password": "ModPass1234!",     "role": "Moderator"},
            {"username": "gl_alice",  "password": "AlicePass1234!",   "role": "Group Leader"},
            {"username": "member_bob", "password": "BobPass1234!",    "role": "Member"},
        ]
        tokens = {}
        for u in users:
            _post(client, "/api/v1/auth/register", json=u)  # 409 on re-run is safe
            resp = _post(client, "/api/v1/auth/login",
                         json={"username": u["username"], "password": u["password"]})
            tokens[u["username"]] = resp.json.get("token", "")
            print(f"  user  {u['username']:20s}  token={tokens[u['username']][:16]}…")

        admin_h = {"Authorization": f"Bearer {tokens['admin']}"}

        # ----------------------------------------------------------------
        # 2. Community
        # ----------------------------------------------------------------
        comm_resp = _post(client, "/api/v1/communities", json={
            "name": "Austin Community",
            "address_line1": "100 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
        }, headers=admin_h)
        if comm_resp.status_code == 201:
            community_id = comm_resp.json["community_id"]
            print(f"  community  {community_id}")

            # Service area
            _post(client, f"/api/v1/communities/{community_id}/service-areas", json={
                "name": "Downtown",
                "address_line1": "200 Congress Ave",
                "city": "Austin", "state": "TX", "zip": "78701",
            }, headers=admin_h)

            # Bind group leader
            gl_resp = _post(client, "/api/v1/auth/login",
                            json={"username": "gl_alice", "password": "AlicePass1234!"})
            gl_token = gl_resp.json.get("token", "")
            # Get gl user_id by registering again to extract it
            reg = _post(client, "/api/v1/auth/register",
                        json={"username": "gl_alice", "password": "AlicePass1234!", "role": "Group Leader"})
            gl_uid = reg.json.get("user_id") if reg.status_code == 201 else None
            if gl_uid:
                _post(client, f"/api/v1/communities/{community_id}/leader-binding",
                      json={"user_id": gl_uid}, headers=admin_h)

            # Commission rule
            _post(client, f"/api/v1/communities/{community_id}/commission-rules", json={
                "rate": 8.0, "floor": 2.0, "ceiling": 12.0, "settlement_cycle": "weekly",
            }, headers=admin_h)

        # ----------------------------------------------------------------
        # 3. Products
        # ----------------------------------------------------------------
        products = [
            {"sku": "LAPTOP-001", "name": "ProBook 15", "brand": "TechCo",
             "category": "Electronics", "price_usd": 999.99,
             "tags": ["laptop", "pro"], "attributes": [{"key": "ram", "value": "16GB"}]},
            {"sku": "MOUSE-001", "name": "ErgoMouse", "brand": "TechCo",
             "category": "Electronics", "price_usd": 49.99, "tags": ["mouse", "ergonomic"]},
            {"sku": "BOOK-001", "name": "Python Mastery", "brand": "PressHouse",
             "category": "Books", "price_usd": 34.99, "tags": ["python", "programming"]},
        ]
        product_ids = {}
        for p in products:
            resp = _post(client, "/api/v1/products", json=p, headers=admin_h)
            if resp.status_code == 201:
                product_ids[p["sku"]] = resp.json["product_id"]
                print(f"  product  {p['sku']:20s}  id={product_ids[p['sku']][:8]}…")

        # ----------------------------------------------------------------
        # 4. Warehouse + inventory
        # ----------------------------------------------------------------
        wh_resp = _post(client, "/api/v1/warehouses",
                        json={"name": "Austin Main", "location": "Austin, TX"},
                        headers=admin_h)
        if wh_resp.status_code == 201:
            wh_id = wh_resp.json["warehouse_id"]
            print(f"  warehouse  {wh_id[:8]}…")

            bin_resp = _post(client, f"/api/v1/warehouses/{wh_id}/bins",
                             json={"bin_code": "A-01", "description": "Aisle 1"},
                             headers=admin_h)

            for sku, pid in product_ids.items():
                _post(client, "/api/v1/inventory/receipts", json={
                    "sku_id": pid, "warehouse_id": wh_id, "quantity": 50, "unit_cost_usd": 10.0,
                }, headers=admin_h)
                print(f"    receipt  {sku}")

        # ----------------------------------------------------------------
        # 5. Content
        # ----------------------------------------------------------------
        art_resp = _post(client, "/api/v1/content", json={
            "type": "article",
            "title": "Getting Started with Austin Community",
            "body": "<p>Welcome to the Austin Community platform.</p>",
            "tags": ["welcome", "getting-started"],
            "categories": ["announcements"],
        }, headers=admin_h)
        if art_resp.status_code == 201:
            cid = art_resp.json["content_id"]
            _post(client, f"/api/v1/content/{cid}/publish", headers=admin_h)
            print(f"  content  {cid[:8]}…  published")

        # ----------------------------------------------------------------
        # 6. Template
        # ----------------------------------------------------------------
        tmpl_resp = _post(client, "/api/v1/templates", json={
            "name": "Product Capture Form",
            "fields": [
                {"name": "product_name", "type": "text",   "required": True},
                {"name": "quantity",     "type": "number",  "required": True},
                {"name": "notes",        "type": "textarea", "required": False},
            ],
        }, headers=admin_h)
        if tmpl_resp.status_code == 201:
            tid = tmpl_resp.json["template_id"]
            _post(client, f"/api/v1/templates/{tid}/publish", headers=admin_h)
            print(f"  template  {tid[:8]}…  published")

        print("\nSeed complete.")


if __name__ == "__main__":
    seed()
