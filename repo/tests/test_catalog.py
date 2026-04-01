"""Product catalog and search tests."""


_PRODUCT = {
    "sku": "WIDGET-001",
    "name": "Widget",
    "brand": "Acme",
    "category": "Tools",
    "description": "A useful widget",
    "price_usd": 9.99,
    "tags": ["popular"],
}


def test_create_product(client, auth_headers):
    resp = client.post("/api/v1/products", json=_PRODUCT, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json["sku"] == "WIDGET-001"


def test_get_product(client, auth_headers):
    create_resp = client.post("/api/v1/products", json={**_PRODUCT, "sku": "WIDGET-GET"}, headers=auth_headers)
    pid = create_resp.json["product_id"]
    resp = client.get(f"/api/v1/products/{pid}", headers=auth_headers)
    assert resp.status_code == 200


def test_duplicate_sku(client, auth_headers):
    client.post("/api/v1/products", json={**_PRODUCT, "sku": "DUP-SKU"}, headers=auth_headers)
    resp = client.post("/api/v1/products", json={**_PRODUCT, "sku": "DUP-SKU"}, headers=auth_headers)
    assert resp.status_code == 409


def test_search_products(client, auth_headers):
    client.post("/api/v1/products", json={**_PRODUCT, "sku": "SEARCH-001"}, headers=auth_headers)
    resp = client.get("/api/v1/search/products?q=Widget", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json


def test_search_history(client, auth_headers):
    client.get("/api/v1/search/products?q=Gadget", headers=auth_headers)
    resp = client.get("/api/v1/search/history", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json["history"], list)


def test_delete_product(client, auth_headers):
    create_resp = client.post("/api/v1/products", json={**_PRODUCT, "sku": "DEL-PROD"}, headers=auth_headers)
    pid = create_resp.json["product_id"]
    resp = client.delete(f"/api/v1/products/{pid}", headers=auth_headers)
    assert resp.status_code == 204
