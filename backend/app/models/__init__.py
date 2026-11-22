from app.models.access_link import AccessLink
from app.models.audit_chain_head import AuditChainHead
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.models.discipline import Discipline, DisciplineGroup, DisciplineTopic, TeachingMaterial
from app.models.document_check import (
    CheckProfile,
    CheckProfileVersion,
    CheckRule,
    DocumentCheckFinding,
    DocumentCheckJob,
    DocumentCheckRunRule,
    DocumentCheckSettings,
    LocalPlagiarismIndex,
    LocalPlagiarismMatch,
    LocalPlagiarismParagraph,
    LocalPlagiarismRun,
    TeacherDocumentLifecycle,
    TeacherDocumentSubmission,
)
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.group_review_report import GroupReviewReport
from app.models.membership import OrganizationMembership
from app.models.mfa_challenge import MfaChallenge
from app.models.mfa_credential import MfaCredential
from app.models.mfa_recovery_code import MfaRecoveryCode
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.review_group import ReviewGroup, TeacherDocumentReview
from app.models.role import Role
from app.models.specialty import Specialty
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.teacher_group import TeacherGroup
from app.models.user import User

__all__ = [
    "Discipline",
    "DisciplineGroup",
    "DisciplineTopic",
    "TeachingMaterial",
    "AuditLog",
    "AuditChainHead",
    "AccessLink",
    "Department",
    "CheckProfile",
    "CheckProfileVersion",
    "CheckRule",
    "TeacherDocumentSubmission",
    "TeacherDocumentLifecycle",
    "DocumentCheckJob",
    "DocumentCheckFinding",
    "DocumentCheckSettings",
    "DocumentCheckRunRule",
    "LocalPlagiarismIndex",
    "LocalPlagiarismParagraph",
    "LocalPlagiarismRun",
    "LocalPlagiarismMatch",
    "Group",
    "GroupReviewReport",
    "ReviewGroup",
    "TeacherDocumentReview",
    "GroupMember",
    "Notification",
    "OrganizationMembership",
    "MfaChallenge",
    "MfaCredential",
    "MfaRecoveryCode",
    "Organization",
    "RefreshToken",
    "Role",
    "Specialty",
    "Student",
    "Teacher",
    "TeacherGroup",
    "User",
]
