"""Organization-level administration with explicit tenant checks.

Directors administer only their current organization.  Super administrators
can additionally create and list organizations, while all membership, group
and catalogue operations below remain scoped to the organization in the
authenticated request context.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import hash_password
from app.models.department import Department
from app.models.enums import AuditEventType, RoleName
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.report import Report
from app.models.role import Role
from app.models.specialty import Specialty
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.teacher_group import TeacherGroup
from app.models.user import User
from app.permissions.rbac import PermissionDenied
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.management import (
    CreateGroupRequest,
    CreateMemberRequest,
    ManagementGroupOut,
    MemberOut,
    UpdateMemberRequest,
)
from app.services.access_link_service import AccessLinkService
from app.services.audit_service import AuditService
from app.services.mfa_service import MfaService


class ManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    def overview(self, org_id: uuid.UUID) -> dict:
        org = self.db.get(Organization, org_id)
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        members = self.db.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == org_id)) or 0
        students = self.db.scalar(
            select(func.count()).select_from(Student).join(OrganizationMembership).where(OrganizationMembership.organization_id == org_id)
        ) or 0
        teachers = self.db.scalar(
            select(func.count()).select_from(Teacher).join(OrganizationMembership).where(OrganizationMembership.organization_id == org_id)
        ) or 0
        groups = self.db.scalar(select(func.count()).select_from(Group).where(Group.organization_id == org_id)) or 0
        reports = self.db.scalar(select(func.count()).select_from(Report).where(Report.organization_id == org_id)) or 0
        return {"organization": org, "members_count": members, "students_count": students, "teachers_count": teachers, "groups_count": groups, "active_reports_count": reports}

    def list_members(
        self, org_id: uuid.UUID, offset: int = 0, limit: int | None = None, q: str | None = None
    ) -> list[MemberOut]:
        stmt = (
            select(OrganizationMembership)
            .join(User, OrganizationMembership.user_id == User.id)
            .options(
                joinedload(OrganizationMembership.user),
                joinedload(OrganizationMembership.role),
                joinedload(OrganizationMembership.teacher_profile).joinedload(Teacher.department),
                joinedload(OrganizationMembership.student_profile).joinedload(Student.specialty),
            )
            .where(OrganizationMembership.organization_id == org_id)
            .order_by(OrganizationMembership.created_at, OrganizationMembership.id)
            .offset(offset)
        )
        if q:
            term = f"%{q}%"
            stmt = stmt.where(or_(User.full_name.ilike(term), User.email.ilike(term)))
        if limit is not None:
            stmt = stmt.limit(limit)
        memberships = list(
            self.db.execute(stmt).unique().scalars().all()
        )
        result: list[MemberOut] = []
        for membership in memberships:
            profile = membership.teacher_profile or membership.student_profile
            group_names: list[str] = []
            if membership.student_profile:
                group_names = list(self.db.execute(
                    select(Group.name).join(GroupMember).where(GroupMember.student_id == membership.student_profile.id, Group.organization_id == org_id)
                ).scalars().all())
            result.append(MemberOut(
                id=membership.id,
                user_id=membership.user_id,
                full_name=membership.user.full_name,
                email=membership.user.email,
                role=RoleName(membership.role.name),
                profile_id=profile.id if profile else None,
                department_id=membership.teacher_profile.department_id if membership.teacher_profile else None,
                specialty_id=membership.student_profile.specialty_id if membership.student_profile else None,
                group_names=group_names,
                is_active=membership.is_active,
            ))
        return result

    def count_members(self, org_id: uuid.UUID, q: str | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(OrganizationMembership)
            .join(User, OrganizationMembership.user_id == User.id)
            .where(OrganizationMembership.organization_id == org_id)
        )
        if q:
            term = f"%{q}%"
            stmt = stmt.where(or_(User.full_name.ilike(term), User.email.ilike(term)))
        return int(self.db.scalar(stmt) or 0)

    @staticmethod
    def _assert_role_can_be_managed(actor_role: str, target_role: str) -> None:
        """Enforce the privilege boundary independently of the HTTP route.

        Directors are roster administrators, not peer administrators.  They
        can only create or mutate Teacher and Student memberships.  Keeping
        this check in the service prevents a future CLI/background endpoint
        from accidentally bypassing the same rule.
        """
        if actor_role == RoleName.DIRECTOR.value and target_role not in {
            RoleName.TEACHER.value,
            RoleName.STUDENT.value,
        }:
            raise PermissionDenied("Directors can manage only Teacher and Student memberships.")

    def _get_manageable_membership(
        self,
        org_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor_role: str,
    ) -> OrganizationMembership:
        membership = self.db.scalar(
            select(OrganizationMembership)
            .options(joinedload(OrganizationMembership.user), joinedload(OrganizationMembership.role))
            .where(
                OrganizationMembership.id == membership_id,
                OrganizationMembership.organization_id == org_id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        self._assert_role_can_be_managed(actor_role, membership.role.name)
        return membership

    def create_member(
        self, org_id: uuid.UUID, payload: CreateMemberRequest, actor_role: str, actor_user_id: uuid.UUID | None = None
    ) -> MemberOut:
        self._assert_role_can_be_managed(actor_role, payload.role.value)
        user = self.db.scalar(select(User).where(User.email == payload.email.lower()))
        if user is None:
            if not payload.password:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Password is required for a new user")
            user = User(email=payload.email.lower(), full_name=payload.full_name, hashed_password=hash_password(payload.password))
            self.db.add(user)
            self.db.flush()
        elif self.db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id, OrganizationMembership.organization_id == org_id)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This user is already a member of the organization")

        role = self.db.scalar(select(Role).where(Role.name == payload.role.value))
        if role is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role catalog is not initialized")
        if payload.department_id:
            department = self.db.get(Department, payload.department_id)
            if department is None or department.organization_id != org_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        specialty = self.db.get(Specialty, payload.specialty_id) if payload.specialty_id else None
        if payload.specialty_id and (specialty is None or specialty.organization_id != org_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specialty not found")

        membership = OrganizationMembership(user_id=user.id, organization_id=org_id, role_id=role.id)
        self.db.add(membership)
        self.db.flush()
        if payload.role == RoleName.TEACHER:
            self.db.add(Teacher(membership_id=membership.id, department_id=payload.department_id))
        if payload.role == RoleName.STUDENT:
            self.db.add(Student(membership_id=membership.id, specialty_id=payload.specialty_id))
        self.audit.record(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            event_type=AuditEventType.MEMBERSHIP_CREATED,
            entity_type="membership",
            entity_id=membership.id,
            metadata={"role": payload.role.value},
        )
        self.db.commit()
        return next(member for member in self.list_members(org_id) if member.id == membership.id)

    def update_member(
        self,
        org_id: uuid.UUID,
        membership_id: uuid.UUID,
        payload: UpdateMemberRequest,
        actor_role: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> MemberOut:
        membership = self._get_manageable_membership(org_id, membership_id, actor_role)
        old_role = membership.role.name
        old_active = membership.is_active
        if payload.role is not None:
            self._assert_role_can_be_managed(actor_role, payload.role.value)
        must_revoke_sessions = payload.role is not None or payload.is_active is not None
        if payload.full_name is not None:
            membership.user.full_name = payload.full_name
        if payload.is_active is not None:
            membership.is_active = payload.is_active
        if payload.role is not None:
            role = self.db.scalar(select(Role).where(Role.name == payload.role.value))
            membership.role_id = role.id
            if payload.role == RoleName.TEACHER and self.db.scalar(select(Teacher).where(Teacher.membership_id == membership.id)) is None:
                self.db.add(Teacher(membership_id=membership.id, department_id=payload.department_id))
            if payload.role == RoleName.STUDENT and self.db.scalar(select(Student).where(Student.membership_id == membership.id)) is None:
                self.db.add(Student(membership_id=membership.id, specialty_id=payload.specialty_id))
        teacher = self.db.scalar(select(Teacher).where(Teacher.membership_id == membership.id))
        student = self.db.scalar(select(Student).where(Student.membership_id == membership.id))
        if teacher and payload.department_id is not None:
            department = self.db.get(Department, payload.department_id)
            if department is None or department.organization_id != org_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
            teacher.department_id = payload.department_id
        if student and payload.specialty_id is not None:
            specialty = self.db.get(Specialty, payload.specialty_id)
            if specialty is None or specialty.organization_id != org_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specialty not found")
            student.specialty_id = payload.specialty_id
        if must_revoke_sessions:
            # Privilege changes and deactivation take effect immediately rather
            # than waiting for an access token to expire.  MFA enrollment is
            # retained; a later privileged login will still require it.
            RefreshTokenRepository(self.db).revoke_all_for_user(membership.user_id)
            MfaService(self.db).revoke_pending_for_user(membership.user_id)
        if payload.role is not None and payload.role.value != old_role:
            self.audit.record(
                organization_id=org_id, actor_user_id=actor_user_id,
                event_type=AuditEventType.MEMBERSHIP_ROLE_CHANGED,
                entity_type="membership", entity_id=membership.id,
                metadata={"from_role": old_role, "to_role": payload.role.value},
            )
        if payload.is_active is not None and payload.is_active != old_active:
            self.audit.record(
                organization_id=org_id, actor_user_id=actor_user_id,
                event_type=AuditEventType.MEMBERSHIP_ACTIVATED if payload.is_active else AuditEventType.MEMBERSHIP_DEACTIVATED,
                entity_type="membership", entity_id=membership.id,
            )
        if teacher and payload.department_id is not None:
            self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.TEACHER_UPDATED, entity_type="teacher", entity_id=teacher.id)
        if student and payload.specialty_id is not None:
            self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.STUDENT_UPDATED, entity_type="student", entity_id=student.id)
        self.db.commit()
        return next(member for member in self.list_members(org_id) if member.id == membership.id)

    def create_access_link(
        self,
        org_id: uuid.UUID,
        membership_id: uuid.UUID,
        purpose: str,
        actor_role: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> dict:
        membership = self._get_manageable_membership(org_id, membership_id, actor_role)
        return AccessLinkService(self.db).create(membership.user, org_id, purpose, actor_user_id=actor_user_id)

    def list_groups(self, org_id: uuid.UUID, offset: int = 0, limit: int | None = None) -> list[ManagementGroupOut]:
        stmt = (
            select(Group)
            .options(joinedload(Group.teacher_links).joinedload(TeacherGroup.teacher).joinedload(Teacher.membership).joinedload(OrganizationMembership.user))
            .where(Group.organization_id == org_id)
            .order_by(Group.name, Group.id)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        groups = list(self.db.execute(stmt).unique().scalars().all())
        result = []
        for group in groups:
            student_count = self.db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group.id)) or 0
            result.append(ManagementGroupOut(
                id=group.id, name=group.name, academic_year=group.academic_year, specialty_id=group.specialty_id,
                student_count=student_count,
                teacher_ids=[link.teacher_id for link in group.teacher_links],
                teacher_names=[link.teacher.membership.user.full_name for link in group.teacher_links],
            ))
        return result

    def count_groups(self, org_id: uuid.UUID) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Group).where(Group.organization_id == org_id)) or 0)

    def create_group(self, org_id: uuid.UUID, payload: CreateGroupRequest, actor_user_id: uuid.UUID | None = None) -> ManagementGroupOut:
        if self.db.scalar(select(Group).where(Group.organization_id == org_id, Group.name == payload.name)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A group with this name already exists")
        specialty = self.db.get(Specialty, payload.specialty_id) if payload.specialty_id else None
        if payload.specialty_id and (specialty is None or specialty.organization_id != org_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specialty not found")
        group = Group(organization_id=org_id, name=payload.name, academic_year=payload.academic_year, specialty_id=payload.specialty_id)
        self.db.add(group)
        self.db.flush()
        self._assign_teachers(org_id, group.id, payload.teacher_ids)
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.GROUP_CREATED, entity_type="group", entity_id=group.id)
        if payload.teacher_ids:
            self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.GROUP_TEACHERS_UPDATED, entity_type="group", entity_id=group.id, metadata={"assigned_count": len(set(payload.teacher_ids))})
        self.db.commit()
        return next(item for item in self.list_groups(org_id) if item.id == group.id)

    def assign_teachers(self, org_id: uuid.UUID, group_id: uuid.UUID, teacher_ids: list[uuid.UUID], actor_user_id: uuid.UUID | None = None) -> ManagementGroupOut:
        group = self.db.scalar(select(Group).where(Group.id == group_id, Group.organization_id == org_id))
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        self._assign_teachers(org_id, group_id, teacher_ids)
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.GROUP_TEACHERS_UPDATED, entity_type="group", entity_id=group_id, metadata={"assigned_count": len(set(teacher_ids))})
        self.db.commit()
        return next(item for item in self.list_groups(org_id) if item.id == group_id)

    def remove_teacher(self, org_id: uuid.UUID, group_id: uuid.UUID, teacher_id: uuid.UUID, actor_user_id: uuid.UUID | None = None) -> None:
        group = self.db.scalar(select(Group).where(Group.id == group_id, Group.organization_id == org_id))
        link = self.db.scalar(select(TeacherGroup).join(Teacher).join(OrganizationMembership).where(TeacherGroup.group_id == group_id, TeacherGroup.teacher_id == teacher_id, OrganizationMembership.organization_id == org_id))
        if group is None or link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher assignment not found")
        self.db.delete(link)
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.GROUP_TEACHERS_UPDATED, entity_type="group", entity_id=group_id, metadata={"removed_count": 1})
        self.db.commit()

    def _assign_teachers(self, org_id: uuid.UUID, group_id: uuid.UUID, teacher_ids: list[uuid.UUID]) -> None:
        if not teacher_ids:
            return
        teachers = list(self.db.execute(
            select(Teacher).join(OrganizationMembership).where(Teacher.id.in_(teacher_ids), OrganizationMembership.organization_id == org_id)
        ).scalars().all())
        if len(teachers) != len(set(teacher_ids)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more teachers were not found")
        existing = set(self.db.execute(select(TeacherGroup.teacher_id).where(TeacherGroup.group_id == group_id)).scalars().all())
        for teacher_id in teacher_ids:
            if teacher_id not in existing:
                self.db.add(TeacherGroup(teacher_id=teacher_id, group_id=group_id))

    def catalog(self, org_id: uuid.UUID) -> dict:
        return {
            "departments": list(self.db.execute(select(Department).where(Department.organization_id == org_id).order_by(Department.name)).scalars().all()),
            "specialties": list(self.db.execute(select(Specialty).where(Specialty.organization_id == org_id).order_by(Specialty.name)).scalars().all()),
        }

    def create_department(self, org_id: uuid.UUID, name: str, actor_user_id: uuid.UUID | None = None) -> Department:
        if self.db.scalar(select(Department).where(Department.organization_id == org_id, Department.name == name)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department already exists")
        department = Department(organization_id=org_id, name=name)
        self.db.add(department)
        self.db.flush()
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.DEPARTMENT_CREATED, entity_type="department", entity_id=department.id)
        self.db.commit()
        self.db.refresh(department)
        return department

    def create_specialty(self, org_id: uuid.UUID, department_id: uuid.UUID, name: str, code: str | None, actor_user_id: uuid.UUID | None = None) -> Specialty:
        department = self.db.get(Department, department_id)
        if department is None or department.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        specialty = Specialty(organization_id=org_id, department_id=department_id, name=name, code=code)
        self.db.add(specialty)
        self.db.flush()
        self.audit.record(organization_id=org_id, actor_user_id=actor_user_id, event_type=AuditEventType.SPECIALTY_CREATED, entity_type="specialty", entity_id=specialty.id)
        self.db.commit()
        self.db.refresh(specialty)
        return specialty

    def list_organizations(self, offset: int = 0, limit: int | None = None) -> list[Organization]:
        stmt = select(Organization).order_by(Organization.name, Organization.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def count_organizations(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Organization)) or 0)

    def create_organization(self, name: str, slug: str, super_admin_user_id: uuid.UUID) -> Organization:
        if self.db.scalar(select(Organization).where(Organization.slug == slug)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization slug already exists")
        organization = Organization(name=name, slug=slug)
        self.db.add(organization)
        self.db.flush()
        super_admin_role = self.db.scalar(select(Role).where(Role.name == RoleName.SUPER_ADMIN.value))
        if super_admin_role is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role catalog is not initialized")
        self.db.add(OrganizationMembership(user_id=super_admin_user_id, organization_id=organization.id, role_id=super_admin_role.id))
        self.audit.record(
            organization_id=organization.id,
            actor_user_id=super_admin_user_id,
            event_type=AuditEventType.ORGANIZATION_CREATED,
            entity_type="organization",
            entity_id=organization.id,
        )
        self.db.commit()
        self.db.refresh(organization)
        return organization
