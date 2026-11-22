import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.document_check import (
    CheckProfile,
    CheckProfileVersion,
    CheckRule,
)
from app.repositories.base import TenantScopedRepository


class CheckProfileRepository(TenantScopedRepository[CheckProfile]):
    model = CheckProfile

    def get_with_versions(self, org_id: uuid.UUID, profile_id: uuid.UUID) -> CheckProfile | None:
        return self.db.scalar(
            select(CheckProfile)
            .options(selectinload(CheckProfile.versions).selectinload(CheckProfileVersion.rules))
            .where(CheckProfile.organization_id == org_id, CheckProfile.id == profile_id)
        )

    def list_for_org(self, org_id: uuid.UUID, offset: int, limit: int) -> list[CheckProfile]:
        stmt = (
            select(CheckProfile)
            .options(selectinload(CheckProfile.versions).selectinload(CheckProfileVersion.rules))
            .where(CheckProfile.organization_id == org_id)
            .order_by(CheckProfile.name, CheckProfile.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())


class CheckProfileVersionRepository(TenantScopedRepository[CheckProfileVersion]):
    model = CheckProfileVersion

    def get_with_rules(self, org_id: uuid.UUID, version_id: uuid.UUID) -> CheckProfileVersion | None:
        return self.db.scalar(
            select(CheckProfileVersion)
            .options(selectinload(CheckProfileVersion.rules))
            .where(CheckProfileVersion.organization_id == org_id, CheckProfileVersion.id == version_id)
        )

    def list_for_profile(
        self, org_id: uuid.UUID, profile_id: uuid.UUID, offset: int, limit: int
    ) -> list[CheckProfileVersion]:
        return list(
            self.db.execute(
                select(CheckProfileVersion)
                .options(selectinload(CheckProfileVersion.rules))
                .where(
                    CheckProfileVersion.organization_id == org_id,
                    CheckProfileVersion.profile_id == profile_id,
                )
                .order_by(CheckProfileVersion.version_number, CheckProfileVersion.id)
                .offset(offset)
                .limit(limit)
            ).scalars().all()
        )

    def count_for_profile(self, org_id: uuid.UUID, profile_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(CheckProfileVersion)
                .where(
                    CheckProfileVersion.organization_id == org_id,
                    CheckProfileVersion.profile_id == profile_id,
                )
            )
            or 0
        )

    def next_version_number(self, org_id: uuid.UUID, profile_id: uuid.UUID) -> int:
        current = self.db.scalar(
            select(func.coalesce(func.max(CheckProfileVersion.version_number), 0)).where(
                CheckProfileVersion.organization_id == org_id,
                CheckProfileVersion.profile_id == profile_id,
            )
        )
        return int(current or 0) + 1


class CheckRuleRepository(TenantScopedRepository[CheckRule]):
    model = CheckRule

    def list_for_version(self, org_id: uuid.UUID, version_id: uuid.UUID) -> list[CheckRule]:
        return list(
            self.db.execute(
                select(CheckRule)
                .where(CheckRule.organization_id == org_id, CheckRule.profile_version_id == version_id)
                .order_by(CheckRule.sort_order, CheckRule.id)
            ).scalars().all()
        )
