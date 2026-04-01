"""
Capture template service.
Enforces schema evolution rules:
  - Adding new optional fields: allowed without migration.
  - All other structural changes require a TemplateMigration record before publish.
"""
import json
from datetime import datetime, timezone

from app.extensions import db
from app.models.content import CaptureTemplate, TemplateVersion, TemplateMigration
from app.models.user import User
from app.models.audit import AuditLog
from app.errors import NotFoundError, UnprocessableError
from flask import g


def _cid() -> str:
    return getattr(g, "correlation_id", "n/a")


def _requires_migration(old_fields: list, new_fields: list) -> bool:
    """Return True if the change is non-additive (needs a migration record before publish)."""
    old_names = {f["name"] for f in old_fields}
    new_names = {f["name"] for f in new_fields}
    # Removed fields
    if old_names - new_names:
        return True
    # Changed field type or required flag
    old_map = {f["name"]: f for f in old_fields}
    for field in new_fields:
        old = old_map.get(field["name"])
        if old and (old.get("type") != field.get("type")):
            return True
    return False


class TemplateService:

    @staticmethod
    def _get_or_404(template_id: str) -> CaptureTemplate:
        t = db.session.get(CaptureTemplate, template_id)
        if t is None or t.deleted_at is not None:
            raise NotFoundError("capture_template")
        return t

    @staticmethod
    def create(data: dict, author: User) -> dict:
        tmpl = CaptureTemplate(name=data["name"], status="draft", created_by=author.user_id)
        db.session.add(tmpl)
        db.session.flush()
        version = TemplateVersion(
            template_id=tmpl.template_id,
            version=1,
            fields=json.dumps(data.get("fields", [])),
            status="draft",
        )
        db.session.add(version)
        db.session.commit()
        result = tmpl.to_dict()
        result.update(version.to_dict())
        return result

    @staticmethod
    def get(template_id: str, version: int | None = None) -> dict:
        tmpl = TemplateService._get_or_404(template_id)
        v_num = version or tmpl.current_version
        v = TemplateVersion.query.filter_by(template_id=template_id, version=v_num).first()
        if v is None:
            raise NotFoundError("template_version")
        result = tmpl.to_dict()
        result.update(v.to_dict())
        return result

    @staticmethod
    def update(template_id: str, data: dict, author: User) -> dict:
        tmpl = TemplateService._get_or_404(template_id)
        current_v = TemplateVersion.query.filter_by(template_id=template_id, version=tmpl.current_version).first()
        old_fields = json.loads(current_v.fields) if current_v else []
        new_fields = data.get("fields", old_fields)

        new_v_num = tmpl.current_version + 1
        version = TemplateVersion(
            template_id=tmpl.template_id,
            version=new_v_num,
            fields=json.dumps(new_fields),
            status="draft",
        )
        tmpl.current_version = new_v_num
        if "name" in data:
            tmpl.name = data["name"]
        db.session.add(version)
        db.session.commit()
        result = tmpl.to_dict()
        result.update(version.to_dict())
        return result

    @staticmethod
    def publish(template_id: str, actor: User) -> dict:
        tmpl = TemplateService._get_or_404(template_id)
        v = TemplateVersion.query.filter_by(template_id=template_id, version=tmpl.current_version).first()
        if v is None:
            raise NotFoundError("template_version")

        # Check if migration is required
        prev_v = TemplateVersion.query.filter_by(template_id=template_id, version=tmpl.current_version - 1).first()
        if prev_v:
            old_fields = json.loads(prev_v.fields)
            new_fields = json.loads(v.fields)
            if _requires_migration(old_fields, new_fields):
                migration_exists = TemplateMigration.query.filter_by(
                    template_id=template_id,
                    from_version=tmpl.current_version - 1,
                    to_version=tmpl.current_version,
                ).first()
                if not migration_exists:
                    raise UnprocessableError(
                        "migration_required",
                        "A migration mapping is required before publishing this version",
                    )

        v.status = "published"
        v.published_at = datetime.now(timezone.utc)
        tmpl.status = "published"
        db.session.add(AuditLog(
            action_type="template", actor_id=actor.user_id,
            target_type="capture_template", target_id=str(template_id),
            after_state=json.dumps({"status": "published", "version": v.version}),
            correlation_id=_cid(),
        ))
        db.session.commit()
        result = tmpl.to_dict()
        result.update(v.to_dict())
        return result

    @staticmethod
    def rollback(template_id: str, target_version: int, actor: User) -> dict:
        tmpl = TemplateService._get_or_404(template_id)
        v = TemplateVersion.query.filter_by(template_id=template_id, version=target_version).first()
        if v is None:
            raise NotFoundError("template_version")
        tmpl.current_version = target_version
        tmpl.status = v.status
        db.session.add(AuditLog(
            action_type="template", actor_id=actor.user_id,
            target_type="capture_template", target_id=str(template_id),
            after_state=json.dumps({"rollback_to_version": target_version}),
            correlation_id=_cid(),
        ))
        db.session.commit()
        result = tmpl.to_dict()
        result.update(v.to_dict())
        return result

    @staticmethod
    def list_versions(template_id: str) -> list:
        TemplateService._get_or_404(template_id)
        versions = (TemplateVersion.query.filter_by(template_id=template_id)
                    .order_by(TemplateVersion.version.asc()).all())
        return [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat()} for v in versions]

    @staticmethod
    def create_migration(template_id: str, data: dict) -> TemplateMigration:
        TemplateService._get_or_404(template_id)
        migration = TemplateMigration(
            template_id=template_id,
            from_version=data["from_version"],
            to_version=data["to_version"],
            field_mappings=json.dumps(data.get("field_mappings", [])),
        )
        db.session.add(migration)
        db.session.commit()
        return migration
