"""Admin ticket and reporting service."""
from datetime import datetime, timezone

from app.extensions import db
from app.models.admin import AdminTicket
from app.models.user import User
from app.errors import NotFoundError, ForbiddenError
from app.services.audit_service import AuditService
from flask import g


def _cid() -> str:
    return getattr(g, "correlation_id", "n/a")


class AdminService:

    @staticmethod
    def create_ticket(data: dict, actor: User) -> AdminTicket:
        ticket = AdminTicket(
            type=data["type"],
            subject=data["subject"],
            body=data["body"],
            target_type=data.get("target_type"),
            target_id=data.get("target_id"),
            created_by=actor.user_id,
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket

    @staticmethod
    def list_tickets(params: dict, requester: User) -> dict:
        q = AdminTicket.query
        if requester.role == "Moderator":
            q = q.filter(AdminTicket.created_by == requester.user_id)
        if params.get("status"):
            q = q.filter(AdminTicket.status == params["status"])
        if params.get("type"):
            q = q.filter(AdminTicket.type == params["type"])
        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        total = q.count()
        items = q.order_by(AdminTicket.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "page": page, "page_size": page_size, "items": [t.to_dict() for t in items]}

    @staticmethod
    def update_ticket(ticket_id: str, data: dict, actor: User) -> AdminTicket:
        ticket = db.session.get(AdminTicket, ticket_id)
        if ticket is None:
            raise NotFoundError("admin_ticket")
        if "status" in data:
            ticket.status = data["status"]
            if data["status"] == "closed":
                ticket.resolved_at = datetime.now(timezone.utc)
        if "resolution_notes" in data:
            ticket.resolution_notes = data["resolution_notes"]
        AuditService.append(
            action_type="moderation", actor_id=actor.user_id,
            target_type="admin_ticket", target_id=str(ticket_id),
            after={"status": ticket.status},
            correlation_id=_cid(),
        )
        db.session.commit()
        return ticket

    @staticmethod
    def group_leader_performance(params: dict, requester: User) -> dict:
        """
        Scaffold: returns structure. Full implementation queries SettlementRuns,
        InventoryTransactions, and Products to compute actual metrics.
        Row-level scoping: Group Leaders may only query their bound community.
        """
        community_id = params.get("community_id")

        if requester.role == "Group Leader":
            from app.models.community import GroupLeaderBinding
            binding = GroupLeaderBinding.query.filter_by(
                user_id=requester.user_id, active=True,
            ).first()
            if binding is None or (community_id and str(binding.community_id) != community_id):
                raise ForbiddenError("forbidden", "Access restricted to your bound community")
            community_id = str(binding.community_id)

        return {
            "community_id": community_id,
            "period": {"from": params.get("from"), "to": params.get("to")},
            "total_orders": 0,
            "total_order_value_usd": 0.0,
            "commission_earned_usd": 0.0,
            "top_products": [],
        }
