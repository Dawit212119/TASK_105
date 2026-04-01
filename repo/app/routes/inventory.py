from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.inventory_service import InventoryService

inventory_bp = Blueprint("inventory", __name__)

_STAFF_ROLES = ("Administrator", "Operations Manager", "Staff")
_MANAGER_ROLES = ("Administrator", "Operations Manager")


@inventory_bp.post("/warehouses")
@require_auth
@require_roles(*_MANAGER_ROLES)
def create_warehouse():
    data = request.get_json(force=True) or {}
    wh = InventoryService.create_warehouse(data)
    return jsonify(wh.to_dict()), 201


@inventory_bp.get("/warehouses")
@require_auth
@require_roles(*_STAFF_ROLES)
def list_warehouses():
    return jsonify(InventoryService.list_warehouses())


@inventory_bp.post("/warehouses/<warehouse_id>/bins")
@require_auth
@require_roles(*_MANAGER_ROLES)
def create_bin(warehouse_id):
    data = request.get_json(force=True) or {}
    b = InventoryService.create_bin(warehouse_id, data)
    return jsonify(b.to_dict()), 201


@inventory_bp.get("/warehouses/<warehouse_id>/bins")
@require_auth
@require_roles(*_STAFF_ROLES)
def list_bins(warehouse_id):
    return jsonify(InventoryService.list_bins(warehouse_id))


@inventory_bp.post("/inventory/receipts")
@require_auth
@require_roles(*_STAFF_ROLES)
def create_receipt():
    data = request.get_json(force=True) or {}
    txn = InventoryService.record_receipt(data, actor=g.current_user)
    return jsonify(txn.to_dict()), 201


@inventory_bp.post("/inventory/issues")
@require_auth
@require_roles(*_STAFF_ROLES)
def create_issue():
    data = request.get_json(force=True) or {}
    txn = InventoryService.record_issue(data, actor=g.current_user)
    return jsonify(txn.to_dict()), 201


@inventory_bp.post("/inventory/transfers")
@require_auth
@require_roles(*_STAFF_ROLES)
def create_transfer():
    data = request.get_json(force=True) or {}
    txns = InventoryService.record_transfer(data, actor=g.current_user)
    return jsonify([t.to_dict() for t in txns]), 201


@inventory_bp.post("/inventory/adjustments")
@require_auth
@require_roles(*_MANAGER_ROLES)
def create_adjustment():
    data = request.get_json(force=True) or {}
    result = InventoryService.record_adjustment(data, actor=g.current_user)
    return jsonify(result), 201


@inventory_bp.post("/inventory/cycle-counts")
@require_auth
@require_roles(*_STAFF_ROLES)
def create_cycle_count():
    data = request.get_json(force=True) or {}
    result = InventoryService.record_cycle_count(data, actor=g.current_user)
    return jsonify(result), 201


@inventory_bp.get("/inventory/stock")
@require_auth
@require_roles(*_STAFF_ROLES)
def get_stock():
    params = {
        "sku_id": request.args.get("sku_id"),
        "warehouse_id": request.args.get("warehouse_id"),
        "bin_id": request.args.get("bin_id"),
        "below_safety_stock": request.args.get("below_safety_stock") == "true",
        "slow_moving": request.args.get("slow_moving") == "true",
    }
    return jsonify(InventoryService.query_stock(params))


@inventory_bp.get("/inventory/transactions")
@require_auth
@require_roles(*_STAFF_ROLES)
def list_transactions():
    params = {
        "sku_id": request.args.get("sku_id"),
        "warehouse_id": request.args.get("warehouse_id"),
        "type": request.args.get("type"),
        "from": request.args.get("from"),
        "to": request.args.get("to"),
        "page": int(request.args.get("page", 1)),
        "page_size": min(int(request.args.get("page_size", 20)), 100),
    }
    return jsonify(InventoryService.list_transactions(params))
