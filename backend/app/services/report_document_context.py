"""Builds the VariableContext for a specific report — the one place that
knows how to gather organization/student/teacher/internship/group data for
variable resolution (rule 18: dedicated service, never scattered)."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.documents.variables import VariableContext
from app.models.group import Group
from app.models.internship import Internship
from app.models.organization import Organization
from app.models.report import Report
from app.models.teacher import Teacher


def build_context_for_report(db: Session, report: Report, internship: Internship) -> VariableContext:
    organization = db.get(Organization, report.organization_id)
    group = db.get(Group, internship.group_id)
    teacher = db.get(Teacher, internship.created_by_teacher_id)
    student = report.student

    return VariableContext(
        organization_name=organization.name if organization else "",
        student_full_name=student.membership.user.full_name if student and student.membership else "",
        student_group=group.name if group else "",
        student_specialty=student.specialty.name if student and student.specialty else "",
        student_department=teacher.department.name if teacher and teacher.department else "",
        teacher_full_name=teacher.membership.user.full_name if teacher and teacher.membership else "",
        internship_title=internship.title,
        internship_start_date=internship.start_date.isoformat(),
        internship_end_date=internship.end_date.isoformat(),
        academic_year=group.academic_year or "" if group else "",
        current_year=str(datetime.now().year),
    )
