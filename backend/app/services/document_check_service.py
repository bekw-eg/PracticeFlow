from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.document_check import (
    AssignmentStudent,
    CheckProfile,
    CheckProfileVersion,
    CheckRule,
    DocumentCheckAssignment,
)
from app.models.enums import (
    AuditEventType,
    CheckRuleSeverity,
    CheckRuleType,
    CheckProfileVersionStatus,
    DocumentCheckAssignmentStatus,
    EXECUTABLE_CHECK_RULE_TYPES,
)
from app.permissions.rbac import PermissionDenied, require_teacher_owns_group
from app.repositories.document_check_repository import (
    CheckProfileRepository,
    CheckProfileVersionRepository,
    CheckRuleRepository,
    DocumentCheckAssignmentRepository,
)
from app.repositories.group_member_repository import GroupMemberRepository
from app.repositories.group_repository import GroupRepository
from app.schemas.document_check import (
    BulkReplaceCheckRulesRequest,
    CreateCheckProfileVersionRequest,
    CreateDocumentCheckAssignmentRequest,
    UpdateDocumentCheckAssignmentRequest,
)
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity} not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


DEFAULT_EXECUTABLE_RULES = (
    {
        "rule_type": CheckRuleType.PAGE_FORMAT_MARGINS,
        "category": "formatting",
        "severity": CheckRuleSeverity.ERROR,
        "config": {
            "page_size": "A4",
            "orientation": "PORTRAIT",
            "margins": {"top_mm": 20.0, "right_mm": 15.0, "bottom_mm": 20.0, "left_mm": 30.0},
            "width_mm": None,
            "height_mm": None,
        },
    },
    {
        "rule_type": CheckRuleType.FONTS_SIZES,
        "category": "formatting",
        "severity": CheckRuleSeverity.ERROR,
        "config": {
            "allowed_fonts": ["Times New Roman"],
            "min_size_pt": 12.0,
            "max_size_pt": 14.0,
        },
    },
    {
        "rule_type": CheckRuleType.PARAGRAPH_SPACING_INDENTS,
        "category": "formatting",
        "severity": CheckRuleSeverity.WARNING,
        "config": {
            "line_spacing": 1.5,
            "space_before_pt": 0.0,
            "space_after_pt": 0.0,
            "first_line_indent_mm": 12.5,
            "left_indent_mm": 0.0,
            "right_indent_mm": 0.0,
        },
    },
)


class CheckProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.profiles = CheckProfileRepository(db)
        self.versions = CheckProfileVersionRepository(db)
        self.rules = CheckRuleRepository(db)
        self.audit = AuditService(db)

    def _lock_profile(self, org_id: uuid.UUID, profile_id: uuid.UUID) -> None:
        profile = self.db.scalar(select(CheckProfile.id).where(
            CheckProfile.organization_id == org_id, CheckProfile.id == profile_id,
        ).with_for_update())
        if profile is None:
            raise _not_found("Check profile")

    def _lock_version(self, org_id: uuid.UUID, profile_id: uuid.UUID, version_id: uuid.UUID) -> CheckProfileVersion:
        version = self.db.scalar(select(CheckProfileVersion).where(
            CheckProfileVersion.organization_id == org_id,
            CheckProfileVersion.profile_id == profile_id,
            CheckProfileVersion.id == version_id,
        ).options(selectinload(CheckProfileVersion.rules)).with_for_update().execution_options(populate_existing=True))
        if version is None:
            raise _not_found("Check profile version")
        return version

    def list_profiles(self, org_id: uuid.UUID, offset: int, limit: int) -> list[CheckProfile]:
        return self.profiles.list_for_org(org_id, offset, limit)

    def count_profiles(self, org_id: uuid.UUID) -> int:
        return self.profiles.count(org_id)

    def get_profile(self, org_id: uuid.UUID, profile_id: uuid.UUID) -> CheckProfile:
        profile = self.profiles.get_with_versions(org_id, profile_id)
        if profile is None:
            raise _not_found("Check profile")
        return profile

    def create_profile(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        name: str,
        description: str | None,
    ) -> CheckProfile:
        profile = CheckProfile(
            organization_id=org_id,
            created_by_teacher_id=teacher_id,
            name=name,
            description=description,
        )
        self.db.add(profile)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise _conflict("A check profile with this name already exists") from exc
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.CHECK_PROFILE_CREATED,
            entity_type="check_profile",
            entity_id=profile.id,
        )
        self.db.commit()
        return self.get_profile(org_id, profile.id)

    def update_profile(
        self, org_id: uuid.UUID, profile_id: uuid.UUID, values: dict[str, object]
    ) -> CheckProfile:
        profile = self.get_profile(org_id, profile_id)
        for field in ("name", "description"):
            if field in values:
                setattr(profile, field, values[field])
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise _conflict("A check profile with this name already exists") from exc
        return self.get_profile(org_id, profile_id)

    def delete_profile(self, org_id: uuid.UUID, profile_id: uuid.UUID) -> None:
        profile = self.get_profile(org_id, profile_id)
        if any(version.state != CheckProfileVersionStatus.DRAFT for version in profile.versions):
            raise _conflict("A profile with published or retired versions cannot be deleted")
        self.db.delete(profile)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise _conflict("This check profile is in use and cannot be deleted") from exc

    def list_versions(
        self, org_id: uuid.UUID, profile_id: uuid.UUID, offset: int, limit: int
    ) -> list[CheckProfileVersion]:
        self.get_profile(org_id, profile_id)
        return self.versions.list_for_profile(org_id, profile_id, offset, limit)

    def count_versions(self, org_id: uuid.UUID, profile_id: uuid.UUID) -> int:
        self.get_profile(org_id, profile_id)
        return self.versions.count_for_profile(org_id, profile_id)

    def get_version(
        self, org_id: uuid.UUID, profile_id: uuid.UUID, version_id: uuid.UUID
    ) -> CheckProfileVersion:
        version = self.versions.get_with_rules(org_id, version_id)
        if version is None or version.profile_id != profile_id:
            raise _not_found("Check profile version")
        return version

    def create_version(
        self,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        profile_id: uuid.UUID,
        payload: CreateCheckProfileVersionRequest,
    ) -> CheckProfileVersion:
        self._lock_profile(org_id, profile_id)
        source = None
        if payload.source_version_id is not None:
            source = self.get_version(org_id, profile_id, payload.source_version_id)

        version = CheckProfileVersion(
            organization_id=org_id,
            profile_id=profile_id,
            version_number=self.versions.next_version_number(org_id, profile_id),
            state=CheckProfileVersionStatus.DRAFT,
            notes=payload.notes,
        )
        self.db.add(version)
        self.db.flush()
        if source is not None:
            for rule in source.rules:
                self.db.add(
                    CheckRule(
                        organization_id=org_id,
                        profile_version_id=version.id,
                        rule_type=rule.rule_type,
                        category=rule.category,
                        severity=rule.severity,
                        enabled=rule.enabled,
                        sort_order=rule.sort_order,
                        config_schema_version=rule.config_schema_version,
                        config=dict(rule.config),
                    )
                )
        else:
            for sort_order, rule in enumerate(DEFAULT_EXECUTABLE_RULES):
                self.db.add(CheckRule(
                    organization_id=org_id,
                    profile_version_id=version.id,
                    rule_type=rule["rule_type"],
                    category=rule["category"],
                    severity=rule["severity"],
                    enabled=True,
                    sort_order=sort_order,
                    config_schema_version=1,
                    config=rule["config"],
                ))
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.CHECK_PROFILE_VERSION_CREATED,
            entity_type="check_profile_version",
            entity_id=version.id,
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise _conflict("A profile version was created concurrently; retry the request") from exc
        return self.get_version(org_id, profile_id, version.id)

    def update_version(
        self,
        org_id: uuid.UUID,
        profile_id: uuid.UUID,
        version_id: uuid.UUID,
        values: dict[str, object],
    ) -> CheckProfileVersion:
        version = self._lock_version(org_id, profile_id, version_id)
        if version.state != CheckProfileVersionStatus.DRAFT:
            raise _conflict("Only a draft profile version can be edited")
        if "notes" in values:
            version.notes = values["notes"]
        self.db.commit()
        return self.get_version(org_id, profile_id, version_id)

    def replace_rules(
        self,
        org_id: uuid.UUID,
        profile_id: uuid.UUID,
        version_id: uuid.UUID,
        payload: BulkReplaceCheckRulesRequest,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> CheckProfileVersion:
        self._lock_profile(org_id, profile_id)
        version = self._lock_version(org_id, profile_id, version_id)
        if version.state == CheckProfileVersionStatus.RETIRED:
            raise _conflict("This profile version is retired; open the current version to edit its rules")

        previous_rules = [{
            "rule_type": rule.rule_type.value, "category": rule.category,
            "severity": rule.severity.value, "enabled": rule.enabled,
            "sort_order": rule.sort_order, "config_schema_version": rule.config_schema_version,
            "config": rule.config,
        } for rule in version.rules]
        requested_rules = [item.model_dump(mode="json") for item in sorted(payload.rules, key=lambda item: item.sort_order)]
        if previous_rules == requested_rules:
            self.db.commit()
            return self.get_version(org_id, profile_id, version_id)

        published = version.state == CheckProfileVersionStatus.PUBLISHED
        target = version
        try:
            if published:
                # Existing submissions and queued jobs keep their original rule IDs.
                # Save the replacement and retire the old version in one transaction.
                target = CheckProfileVersion(
                    organization_id=org_id, profile_id=profile_id,
                    version_number=self.versions.next_version_number(org_id, profile_id),
                    state=CheckProfileVersionStatus.DRAFT, notes=version.notes,
                )
                self.db.add(target)
                self.db.flush()
            else:
                for rule in list(version.rules):
                    self.db.delete(rule)
                self.db.flush()
            for item in payload.rules:
                self.db.add(CheckRule(
                    organization_id=org_id, profile_version_id=target.id,
                    rule_type=item.rule_type, category=item.category, severity=item.severity,
                    enabled=item.enabled, sort_order=item.sort_order,
                    config_schema_version=item.config_schema_version, config=item.config,
                ))
            # Rules must be inserted while their version is still a draft.
            self.db.flush()
            if published:
                now = datetime.now(UTC)
                version.state = CheckProfileVersionStatus.RETIRED
                version.retired_at = now
                self.audit.record(
                    organization_id=org_id, actor_user_id=actor_user_id,
                    event_type=AuditEventType.CHECK_PROFILE_VERSION_CREATED,
                    entity_type="check_profile_version", entity_id=target.id,
                    metadata={"source_version_number": version.version_number},
                )
                self.audit.record(
                    organization_id=org_id, actor_user_id=actor_user_id,
                    event_type=AuditEventType.CHECK_PROFILE_VERSION_RETIRED,
                    entity_type="check_profile_version", entity_id=version.id,
                    metadata={"replacement_version_number": target.version_number},
                )
                if any(item.enabled and item.rule_type in EXECUTABLE_CHECK_RULE_TYPES for item in payload.rules):
                    target.state = CheckProfileVersionStatus.PUBLISHED
                    target.published_at = now
                    self.audit.record(
                        organization_id=org_id, actor_user_id=actor_user_id,
                        event_type=AuditEventType.CHECK_PROFILE_VERSION_PUBLISHED,
                        entity_type="check_profile_version", entity_id=target.id,
                    )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise _conflict("The profile rules changed concurrently; reload the current version and retry") from exc
        self.db.expire(target, ["rules"])
        return self.get_version(org_id, profile_id, target.id)

    def publish_version(
        self, org_id: uuid.UUID, actor_user_id: uuid.UUID, profile_id: uuid.UUID, version_id: uuid.UUID
    ) -> CheckProfileVersion:
        version = self._lock_version(org_id, profile_id, version_id)
        if version.state == CheckProfileVersionStatus.PUBLISHED:
            return version
        if version.state != CheckProfileVersionStatus.DRAFT:
            raise _conflict("Only a draft profile version can be published")
        if not any(
            rule.enabled and rule.rule_type in EXECUTABLE_CHECK_RULE_TYPES
            for rule in version.rules
        ):
            raise _conflict("Enable at least one supported rule before publishing this profile version")
        version.state = CheckProfileVersionStatus.PUBLISHED
        version.published_at = datetime.now(UTC)
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.CHECK_PROFILE_VERSION_PUBLISHED,
            entity_type="check_profile_version",
            entity_id=version.id,
        )
        self.db.commit()
        return self.get_version(org_id, profile_id, version_id)

    def retire_version(
        self, org_id: uuid.UUID, actor_user_id: uuid.UUID, profile_id: uuid.UUID, version_id: uuid.UUID
    ) -> CheckProfileVersion:
        version = self._lock_version(org_id, profile_id, version_id)
        if version.state == CheckProfileVersionStatus.RETIRED:
            return version
        if version.state != CheckProfileVersionStatus.PUBLISHED:
            raise _conflict("Only a published profile version can be retired")
        version.state = CheckProfileVersionStatus.RETIRED
        version.retired_at = datetime.now(UTC)
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.CHECK_PROFILE_VERSION_RETIRED,
            entity_type="check_profile_version",
            entity_id=version.id,
        )
        self.db.commit()
        return self.get_version(org_id, profile_id, version_id)


class DocumentCheckAssignmentService:
    def __init__(self, db: Session):
        self.db = db
        self.assignments = DocumentCheckAssignmentRepository(db)
        self.versions = CheckProfileVersionRepository(db)
        self.group_repo = GroupRepository(db)
        self.group_members = GroupMemberRepository(db)
        self.notifications = NotificationService(db)
        self.audit = AuditService(db)

    def _require_group(self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID) -> None:
        if self.group_repo.get(org_id, group_id) is None:
            raise PermissionDenied("Group not found or not accessible.")
        require_teacher_owns_group(self.group_repo, org_id, teacher_id, group_id)

    def _get_owned(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, assignment_id: uuid.UUID
    ) -> DocumentCheckAssignment:
        self._require_group(org_id, teacher_id, group_id)
        assignment = self.assignments.get_detail(org_id, assignment_id)
        if assignment is None or assignment.group_id != group_id:
            raise _not_found("Document check assignment")
        return assignment

    def list_for_group(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, offset: int, limit: int
    ) -> list[DocumentCheckAssignment]:
        self._require_group(org_id, teacher_id, group_id)
        return self.assignments.list_for_group(org_id, group_id, offset, limit)

    def count_for_group(self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID) -> int:
        self._require_group(org_id, teacher_id, group_id)
        return self.assignments.count_for_group(org_id, group_id)

    def detail(
        self, org_id: uuid.UUID, teacher_id: uuid.UUID, group_id: uuid.UUID, assignment_id: uuid.UUID
    ) -> DocumentCheckAssignment:
        return self._get_owned(org_id, teacher_id, group_id, assignment_id)

    def _published_version(self, org_id: uuid.UUID, version_id: uuid.UUID) -> CheckProfileVersion:
        version = self.versions.get(org_id, version_id)
        if version is None or version.state != CheckProfileVersionStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Profile version not found or not published",
            )
        return version

    def create(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        group_id: uuid.UUID,
        payload: CreateDocumentCheckAssignmentRequest,
    ) -> DocumentCheckAssignment:
        self._require_group(org_id, teacher_id, group_id)
        self._published_version(org_id, payload.profile_version_id)
        assignment = DocumentCheckAssignment(
            organization_id=org_id,
            group_id=group_id,
            created_by_teacher_id=teacher_id,
            profile_version_id=payload.profile_version_id,
            title=payload.title,
            instructions=payload.instructions,
            state=DocumentCheckAssignmentStatus.DRAFT,
            due_at=payload.due_at,
            assignment_timezone=payload.assignment_timezone,
        )
        self.db.add(assignment)
        self.db.flush()
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.DOCUMENT_CHECK_ASSIGNMENT_CREATED,
            entity_type="document_check_assignment",
            entity_id=assignment.id,
        )
        self.db.commit()
        return self.assignments.get_detail(org_id, assignment.id)

    def update(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        group_id: uuid.UUID,
        assignment_id: uuid.UUID,
        payload: UpdateDocumentCheckAssignmentRequest,
    ) -> DocumentCheckAssignment:
        assignment = self._get_owned(org_id, teacher_id, group_id, assignment_id)
        if assignment.state != DocumentCheckAssignmentStatus.DRAFT:
            raise _conflict("Only a draft assignment can be edited")
        values = payload.model_dump(exclude_unset=True)
        if "profile_version_id" in values:
            self._published_version(org_id, values["profile_version_id"])
        for field, value in values.items():
            setattr(assignment, field, value)
        self.db.commit()
        return self.assignments.get_detail(org_id, assignment.id)

    def publish(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        group_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> DocumentCheckAssignment:
        self._require_group(org_id, teacher_id, group_id)
        assignment = self.db.scalar(
            select(DocumentCheckAssignment)
            .where(
                DocumentCheckAssignment.organization_id == org_id,
                DocumentCheckAssignment.group_id == group_id,
                DocumentCheckAssignment.id == assignment_id,
            )
            .with_for_update()
        )
        if assignment is None:
            raise _not_found("Document check assignment")
        if assignment.state == DocumentCheckAssignmentStatus.PUBLISHED:
            return self.assignments.get_detail(org_id, assignment.id)
        if assignment.state != DocumentCheckAssignmentStatus.DRAFT:
            raise _conflict("Only a draft assignment can be published")
        self._published_version(org_id, assignment.profile_version_id)

        members = self.group_members.list_for_group(org_id, group_id)
        for member in members:
            self.db.add(
                AssignmentStudent(
                    organization_id=org_id,
                    assignment_id=assignment.id,
                    student_id=member.student_id,
                )
            )
            self.notifications.create_once(
                org_id,
                member.student.membership.user_id,
                "DOCUMENT_CHECK_ASSIGNED",
                "New document check assignment",
                body=assignment.title,
                link=f"/groups/{group_id}/check-assignments/{assignment.id}",
                dedupe_key=f"document-check-assignment:{assignment.id}:published",
            )
        self.db.flush()
        assignment.state = DocumentCheckAssignmentStatus.PUBLISHED
        assignment.published_at = datetime.now(UTC)
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.DOCUMENT_CHECK_ASSIGNMENT_PUBLISHED,
            entity_type="document_check_assignment",
            entity_id=assignment.id,
            metadata={"student_count": len(members)},
        )
        self.db.commit()
        return self.assignments.get_detail(org_id, assignment.id)

    def close(
        self,
        org_id: uuid.UUID,
        teacher_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        group_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> DocumentCheckAssignment:
        assignment = self._get_owned(org_id, teacher_id, group_id, assignment_id)
        if assignment.state == DocumentCheckAssignmentStatus.CLOSED:
            return assignment
        if assignment.state != DocumentCheckAssignmentStatus.PUBLISHED:
            raise _conflict("Only a published assignment can be closed")
        assignment.state = DocumentCheckAssignmentStatus.CLOSED
        assignment.closed_at = datetime.now(UTC)
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.DOCUMENT_CHECK_ASSIGNMENT_CLOSED,
            entity_type="document_check_assignment",
            entity_id=assignment.id,
        )
        self.db.commit()
        return self.assignments.get_detail(org_id, assignment.id)
