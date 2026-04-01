"""Commission rules and settlement service."""
from datetime import datetime, timezone, timedelta, date

from app.extensions import db
from app.models.commission import CommissionRule, SettlementRun, SettlementDispute, SETTLEMENT_CYCLES
from app.models.user import User
from app.errors import NotFoundError, UnprocessableError, ForbiddenError, AppError

_DISPUTE_WINDOW_DAYS = 2
_SYSTEM_DEFAULT_RATE = 6.0


class CommissionService:

    # --- Commission Rules ---

    @staticmethod
    def create_rule(community_id: str, data: dict) -> CommissionRule:
        rate = float(data.get("rate", _SYSTEM_DEFAULT_RATE))
        floor = float(data.get("floor", 0.0))
        ceiling = float(data.get("ceiling", 15.0))
        if not (0 <= floor <= rate <= ceiling <= 15.0):
            raise AppError("invalid_rate_range", "Must satisfy: 0 ≤ floor ≤ rate ≤ ceiling ≤ 15", status_code=400)
        settlement_cycle = data.get("settlement_cycle", "weekly")
        if settlement_cycle not in SETTLEMENT_CYCLES:
            raise AppError("invalid_cycle", "settlement_cycle must be 'weekly' or 'biweekly'",
                           field="settlement_cycle", status_code=400)
        rule = CommissionRule(
            community_id=community_id,
            product_category=data.get("product_category"),
            rate=rate,
            floor=floor,
            ceiling=ceiling,
            settlement_cycle=settlement_cycle,
        )
        db.session.add(rule)
        db.session.commit()
        return rule

    @staticmethod
    def list_rules(community_id: str) -> list:
        rules = CommissionRule.query.filter_by(community_id=community_id, deleted_at=None).all()
        return [r.to_dict() for r in rules]

    @staticmethod
    def resolve_rate(community_id: str, product_category: str | None = None) -> float:
        """
        Apply commission resolution precedence:
          1. Category-specific rule for this community + category
          2. Community default rule (product_category IS NULL)
          3. System default 6.0%
        """
        if product_category:
            rule = CommissionRule.query.filter_by(
                community_id=community_id,
                product_category=product_category,
                deleted_at=None,
            ).first()
            if rule:
                return rule.rate

        default = CommissionRule.query.filter(
            CommissionRule.community_id == community_id,
            CommissionRule.product_category.is_(None),
            CommissionRule.deleted_at.is_(None),
        ).first()
        if default:
            return default.rate

        return _SYSTEM_DEFAULT_RATE

    @staticmethod
    def assert_can_read(community_id: str, user: User) -> None:
        if user.role in ("Administrator", "Operations Manager"):
            return
        if user.role == "Group Leader":
            from app.models.community import GroupLeaderBinding
            binding = GroupLeaderBinding.query.filter_by(
                community_id=community_id, user_id=user.user_id, active=True
            ).first()
            if binding:
                return
        raise ForbiddenError("forbidden", "Access denied")

    @staticmethod
    def update_rule(community_id: str, rule_id: str, data: dict) -> CommissionRule:
        rule = db.session.get(CommissionRule, rule_id)
        if rule is None or str(rule.community_id) != community_id or rule.deleted_at is not None:
            raise NotFoundError("commission_rule")

        # Compute new values without touching the model yet (avoids dirty-session issues)
        new_rate = float(data["rate"]) if "rate" in data else rule.rate
        new_floor = float(data["floor"]) if "floor" in data else rule.floor
        new_ceiling = float(data["ceiling"]) if "ceiling" in data else rule.ceiling
        new_cycle = data.get("settlement_cycle", rule.settlement_cycle)

        if new_cycle not in SETTLEMENT_CYCLES:
            raise AppError("invalid_cycle", "settlement_cycle must be 'weekly' or 'biweekly'",
                           field="settlement_cycle", status_code=400)
        if not (0 <= new_floor <= new_rate <= new_ceiling <= 15.0):
            raise AppError("invalid_rate_range", "Must satisfy: 0 ≤ floor ≤ rate ≤ ceiling ≤ 15", status_code=400)

        rule.rate = new_rate
        rule.floor = new_floor
        rule.ceiling = new_ceiling
        rule.settlement_cycle = new_cycle
        db.session.commit()
        return rule

    @staticmethod
    def delete_rule(community_id: str, rule_id: str) -> None:
        rule = db.session.get(CommissionRule, rule_id)
        if rule is None or str(rule.community_id) != community_id:
            raise NotFoundError("commission_rule")
        rule.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

    # --- Settlements ---

    @staticmethod
    def create_settlement(data: dict, actor: User) -> tuple:
        """
        Returns (settlement, created: bool).
        If the idempotency_key already exists, returns (existing, False) so the
        route can respond 409 with the existing settlement object.
        """
        key = data.get("idempotency_key")
        if not key:
            raise AppError("idempotency_key_required", "idempotency_key is required",
                           field="idempotency_key", status_code=400)
        existing = SettlementRun.query.filter_by(idempotency_key=key).first()
        if existing:
            return existing, False  # idempotent duplicate

        settlement = SettlementRun(
            community_id=data["community_id"],
            idempotency_key=key,
            status="pending",
            period_start=date.fromisoformat(data["period_start"]),
            period_end=date.fromisoformat(data["period_end"]),
        )
        db.session.add(settlement)
        db.session.commit()
        return settlement, True

    @staticmethod
    def get_settlement(settlement_id: str) -> SettlementRun:
        s = db.session.get(SettlementRun, settlement_id)
        if s is None:
            raise NotFoundError("settlement")
        return s

    @staticmethod
    def assert_can_read_settlement(settlement_id: str, user: User) -> None:
        if user.role in ("Administrator", "Operations Manager"):
            return
        if user.role == "Group Leader":
            s = CommissionService.get_settlement(settlement_id)
            from app.models.community import GroupLeaderBinding
            binding = GroupLeaderBinding.query.filter_by(
                community_id=s.community_id, user_id=user.user_id, active=True
            ).first()
            if binding:
                return
        raise ForbiddenError("forbidden", "Access denied")

    @staticmethod
    def file_dispute(settlement_id: str, data: dict, actor: User) -> SettlementDispute:
        s = CommissionService.get_settlement(settlement_id)
        # Dispute window: 2 days from finalized_at (or created_at if not yet finalized)
        window_start = s.finalized_at or s.created_at
        deadline = window_start + timedelta(days=_DISPUTE_WINDOW_DAYS)
        if datetime.now(timezone.utc) > deadline.replace(tzinfo=timezone.utc):
            raise UnprocessableError("dispute_window_expired", "Dispute window has closed")
        dispute = SettlementDispute(
            settlement_id=settlement_id,
            filed_by=actor.user_id,
            reason=data["reason"],
            disputed_amount=float(data.get("disputed_amount", 0)),
        )
        db.session.add(dispute)
        db.session.commit()
        return dispute

    @staticmethod
    def resolve_dispute(settlement_id: str, dispute_id: str, data: dict) -> SettlementDispute:
        dispute = db.session.get(SettlementDispute, dispute_id)
        if dispute is None or str(dispute.settlement_id) != settlement_id:
            raise NotFoundError("dispute")
        resolution = data.get("resolution")
        if resolution not in ("resolved", "rejected"):
            raise AppError("invalid_resolution", "resolution must be 'resolved' or 'rejected'",
                           field="resolution", status_code=400)
        dispute.status = resolution
        dispute.resolution_notes = data.get("notes")
        dispute.resolved_at = datetime.now(timezone.utc)
        db.session.commit()
        return dispute

    @staticmethod
    def finalize(settlement_id: str, actor: User) -> SettlementRun:
        s = CommissionService.get_settlement(settlement_id)
        open_disputes = SettlementDispute.query.filter_by(
            settlement_id=settlement_id, status="open"
        ).count()
        if open_disputes > 0:
            raise UnprocessableError(
                "settlement_blocked_by_open_dispute",
                "Cannot finalize while disputes are open",
            )
        s.status = "completed"
        s.finalized_at = datetime.now(timezone.utc)
        db.session.commit()
        return s
