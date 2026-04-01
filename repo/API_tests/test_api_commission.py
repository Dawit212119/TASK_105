"""
API functional tests for commission rules and settlement endpoints.

Covers: commission rule CRUD, rate validation, idempotent settlement creation,
        dispute filing/resolving/rejecting, and settlement finalization.
All tests use the Flask test client against /api/v1/communities/{id}/commission-rules
and /api/v1/settlements/* endpoints.
"""
import uuid
import pytest

BASE = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_community(client, headers):
    resp = client.post(f"{BASE}/communities", json={
        "name": f"Comm_{uuid.uuid4().hex[:6]}",
        "address_line1": "1 Oak St",
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json["community_id"]


def _create_rule(client, headers, community_id, **overrides):
    payload = {
        "rate": 6.0,
        "floor": 0.0,
        "ceiling": 15.0,
        "settlement_cycle": "weekly",
    }
    payload.update(overrides)
    return client.post(f"{BASE}/communities/{community_id}/commission-rules",
                       json=payload, headers=headers)


def _create_settlement(client, headers, community_id, idempotency_key=None):
    if idempotency_key is None:
        idempotency_key = uuid.uuid4().hex
    return client.post(f"{BASE}/settlements", json={
        "community_id": community_id,
        "period_start": "2026-01-01",
        "period_end": "2026-01-07",
        "idempotency_key": idempotency_key,
    }, headers=headers)


# ---------------------------------------------------------------------------
# Commission rule CRUD
# ---------------------------------------------------------------------------

def test_create_rule_201(client, auth_headers):
    """POST /communities/{id}/commission-rules returns 201 with rule_id/rate/floor/ceiling."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, rate=8.0, floor=1.0, ceiling=12.0)
    assert resp.status_code == 201
    data = resp.json
    assert "rule_id" in data
    assert data["rate"] == 8.0
    assert data["floor"] == 1.0
    assert data["ceiling"] == 12.0


def test_create_rule_floor_gt_rate_400(client, auth_headers):
    """floor > rate returns 400 with error=invalid_rate_range."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, rate=6.0, floor=10.0, ceiling=15.0)
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rate_range"


def test_create_rule_ceiling_above_15_400(client, auth_headers):
    """ceiling > 15.0 returns 400."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, rate=6.0, floor=0.0, ceiling=16.0)
    assert resp.status_code == 400


def test_create_rule_invalid_cycle_400(client, auth_headers):
    """settlement_cycle='monthly' returns 400."""
    cid = _create_community(client, auth_headers)
    resp = _create_rule(client, auth_headers, cid, settlement_cycle="monthly")
    assert resp.status_code == 400


def test_update_rule_200(client, auth_headers):
    """PATCH commission rule returns 200 with updated values."""
    cid = _create_community(client, auth_headers)
    rule_id = _create_rule(client, auth_headers, cid).json["rule_id"]
    resp = client.patch(
        f"{BASE}/communities/{cid}/commission-rules/{rule_id}",
        json={"rate": 7.5, "ceiling": 12.0},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json["rate"] == 7.5


def test_update_rule_invalid_bounds_400(client, auth_headers):
    """PATCH making floor > rate returns 400."""
    cid = _create_community(client, auth_headers)
    rule_id = _create_rule(client, auth_headers, cid, rate=6.0, floor=0.0, ceiling=10.0).json["rule_id"]
    resp = client.patch(
        f"{BASE}/communities/{cid}/commission-rules/{rule_id}",
        json={"floor": 9.0},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json["error"] == "invalid_rate_range"


def test_delete_rule_204(client, auth_headers):
    """DELETE commission rule returns 204."""
    cid = _create_community(client, auth_headers)
    rule_id = _create_rule(client, auth_headers, cid).json["rule_id"]
    resp = client.delete(
        f"{BASE}/communities/{cid}/commission-rules/{rule_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Settlements
# ---------------------------------------------------------------------------

def test_create_settlement_201(client, auth_headers):
    """POST /settlements returns 201 with settlement_id/status/period_start/period_end."""
    cid = _create_community(client, auth_headers)
    resp = _create_settlement(client, auth_headers, cid)
    assert resp.status_code == 201
    data = resp.json
    assert "settlement_id" in data
    assert "status" in data
    assert "period_start" in data
    assert "period_end" in data


def test_settlement_idempotent_409(client, auth_headers):
    """Same idempotency_key → 409 with the same settlement_id returned."""
    cid = _create_community(client, auth_headers)
    key = uuid.uuid4().hex
    first = _create_settlement(client, auth_headers, cid, idempotency_key=key)
    assert first.status_code == 201

    second = _create_settlement(client, auth_headers, cid, idempotency_key=key)
    assert second.status_code == 409
    assert second.json["settlement_id"] == first.json["settlement_id"]


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------

def test_dispute_within_window_201(client, auth_headers):
    """POST /settlements/{id}/disputes returns 201 with dispute_id and status=open."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    resp = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Wrong amount",
        "disputed_amount": 50.0,
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json
    assert "dispute_id" in data
    assert data["status"] == "open"


def test_dispute_resolve_200(client, auth_headers):
    """PATCH dispute with resolution=resolved returns 200 with status=resolved."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Test",
        "disputed_amount": 10.0,
    }, headers=auth_headers).json
    did = dispute["dispute_id"]
    resp = client.patch(f"{BASE}/settlements/{sid}/disputes/{did}", json={
        "resolution": "resolved",
        "notes": "Accepted",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "resolved"


def test_dispute_reject_200(client, auth_headers):
    """PATCH dispute with resolution=rejected returns 200 with status=rejected."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Test",
        "disputed_amount": 5.0,
    }, headers=auth_headers).json
    did = dispute["dispute_id"]
    resp = client.patch(f"{BASE}/settlements/{sid}/disputes/{did}", json={
        "resolution": "rejected",
        "notes": "Not valid",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "rejected"


# ---------------------------------------------------------------------------
# Settlement finalization
# ---------------------------------------------------------------------------

def test_finalize_settlement_blocked_422(client, auth_headers):
    """Finalizing with an open dispute returns 422 with error=settlement_blocked_by_open_dispute."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Open dispute",
        "disputed_amount": 25.0,
    }, headers=auth_headers)
    resp = client.post(f"{BASE}/settlements/{sid}/finalize", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json["error"] == "settlement_blocked_by_open_dispute"


def test_finalize_settlement_ok_200(client, auth_headers):
    """After resolving all disputes, finalize returns 200 with status=completed."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    dispute = client.post(f"{BASE}/settlements/{sid}/disputes", json={
        "reason": "Test",
        "disputed_amount": 10.0,
    }, headers=auth_headers).json
    did = dispute["dispute_id"]
    client.patch(f"{BASE}/settlements/{sid}/disputes/{did}", json={
        "resolution": "resolved",
        "notes": "Accepted",
    }, headers=auth_headers)
    resp = client.post(f"{BASE}/settlements/{sid}/finalize", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "completed"


def test_finalize_no_disputes_200(client, auth_headers):
    """Finalizing a settlement with no disputes returns 200 with status=completed."""
    cid = _create_community(client, auth_headers)
    sid = _create_settlement(client, auth_headers, cid).json["settlement_id"]
    resp = client.post(f"{BASE}/settlements/{sid}/finalize", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "completed"
