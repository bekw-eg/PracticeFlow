import uuid

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.documents.defaults import build_default_document
from app.documents.schemas import DocumentModel
from app.documents.validators import validate_document
from app.models.enums import AuditEventType
from app.models.template import Template
from app.models.template_version import TemplateVersion
from app.repositories.internship_repository import InternshipRepository
from app.repositories.template_repository import TemplateRepository
from app.repositories.template_version_repository import TemplateVersionRepository
from app.services.audit_service import AuditService
from app.services.report_service import _stale_document_revision


class TemplateService:
    def __init__(self, db: Session):
        self.db = db
        self.template_repo = TemplateRepository(db)
        self.version_repo = TemplateVersionRepository(db)
        self.internship_repo = InternshipRepository(db)
        self.audit = AuditService(db)

    def list_for_org(self, org_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[Template]:
        return self.template_repo.list_for_org(org_id, offset, limit)

    def count_for_org(self, org_id: uuid.UUID) -> int:
        return self.template_repo.count(org_id)

    def create_template(self, org_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID, name: str, description: str | None) -> Template:
        template = Template(organization_id=org_id, created_by_teacher_id=teacher_id, name=name, description=description)
        self.template_repo.add(template)
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.TEMPLATE_CREATED,
            entity_type="template",
            entity_id=template.id,
        )
        self.db.commit()
        self.db.refresh(template)
        return template

    def is_locked(self, version_id: uuid.UUID) -> bool:
        """A version LOCKS the moment any Internship is created against it
        (rule 5/30) — from then on it's part of the historical record for
        whatever group used it, and editing it would silently rewrite that
        history. The teacher must create a new version instead."""
        return self.internship_repo.any_uses_template_version(version_id)

    def create_version(self, org_id: uuid.UUID, actor_user_id: uuid.UUID, template_id: uuid.UUID) -> TemplateVersion:
        template = self.template_repo.get(org_id, template_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

        document = build_default_document()
        version = TemplateVersion(
            template_id=template_id,
            version_number=self.version_repo.next_version_number(template_id),
            document_data=document.model_dump(mode="json"),
            schema_version=document.schema_version,
            is_published=True,
        )
        self.version_repo.add(version)
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.TEMPLATE_VERSION_CREATED,
            entity_type="template_version",
            entity_id=version.id,
        )
        self.db.commit()
        self.db.refresh(version)
        return version

    def get_version(self, org_id: uuid.UUID, version_id: uuid.UUID) -> TemplateVersion:
        version = self.version_repo.get(org_id, version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template version not found")
        return version

    def update_document(
        self,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        version_id: uuid.UUID,
        expected_revision: int,
        document: DocumentModel,
    ) -> TemplateVersion:
        version = self.get_version(org_id, version_id)
        if self.is_locked(version.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This template version is in use by an internship and can no longer be edited. Create a new version instead.",
            )

        errors = validate_document(document)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"errors": errors})

        updated = self.db.execute(
            update(TemplateVersion)
            .where(
                TemplateVersion.id == version.id,
                TemplateVersion.revision == expected_revision,
                TemplateVersion.template_id == Template.id,
                Template.organization_id == org_id,
            )
            .values(
                document_data=document.model_dump(mode="json"),
                schema_version=document.schema_version,
                revision=TemplateVersion.revision + 1,
            )
            .returning(TemplateVersion.id)
        ).scalar_one_or_none()
        if updated is None:
            self.db.rollback()
            raise _stale_document_revision()

        self.db.commit()
        self.db.refresh(version)
        return version
