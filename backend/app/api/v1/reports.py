import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.dependencies.features import require_legacy_document_editor_enabled
from app.models.enums import ReportStatus, RoleName
from app.models.group import Group
from app.models.internship import Internship
from app.models.report import Report
from app.models.report_version import ReportVersion
from app.permissions.rbac import require_role
from app.repositories.internship_repository import InternshipRepository
from app.repositories.report_version_repository import ReportVersionRepository
from app.schemas.report import (
    ReportDetail,
    ReportDocumentResponse,
    ReportHistoryEntry,
    ReviewQueueDeadlineFilter,
    ReportOut,
    ReportDeadlineState,
    ReportVersionOut,
    StudentReportOut,
    TeacherReviewQueueItem,
    UpdateReportDocumentRequest,
)
from app.services.report_service import ReportService

router = APIRouter(tags=["reports"])

_DEADLINE_SOON_DAYS = 3


def _deadline_state(
    deadline: date, submitted_at: datetime | None, *, today: date | None = None
) -> ReportDeadlineState:
    today = today or datetime.now(timezone.utc).date()
    if submitted_at is not None:
        return ReportDeadlineState.SUBMITTED_LATE if submitted_at.date() > deadline else ReportDeadlineState.SUBMITTED_ON_TIME
    if deadline < today:
        return ReportDeadlineState.OVERDUE
    if deadline == today:
        return ReportDeadlineState.DUE_TODAY
    if deadline <= today + timedelta(days=_DEADLINE_SOON_DAYS):
        return ReportDeadlineState.DUE_SOON
    return ReportDeadlineState.UPCOMING


@router.get("/reports", response_model=list[StudentReportOut])
def my_reports(
    response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[StudentReportOut]:
    require_role(ctx.role, RoleName.STUDENT)
    service = ReportService(db)
    rows = db.execute(
        select(
            Report.id,
            Report.internship_id,
            Report.student_id,
            Report.status,
            Report.current_version_id,
            Report.created_at,
            Internship.title.label("internship_title"),
            Internship.description.label("internship_description"),
            Group.name.label("group_name"),
            Internship.start_date,
            Internship.end_date,
            Internship.deadline,
            ReportVersion.submitted_at,
        )
        .join(Internship, Report.internship_id == Internship.id)
        .join(Group, Internship.group_id == Group.id)
        .outerjoin(ReportVersion, ReportVersion.id == Report.current_version_id)
        .where(
            Report.organization_id == ctx.organization_id,
            Report.student_id == ctx.student_id,
            Internship.organization_id == ctx.organization_id,
            Group.organization_id == ctx.organization_id,
        )
        .order_by(Report.created_at.desc(), Report.id.desc())
        .offset(page.offset)
        .limit(page.limit)
    ).mappings().all()
    set_pagination_headers(response, page, total=service.count_for_student(ctx.organization_id, ctx.student_id), returned=len(rows))
    return [
        StudentReportOut(
            id=row["id"],
            internship_id=row["internship_id"],
            student_id=row["student_id"],
            status=row["status"],
            current_version_id=row["current_version_id"],
            created_at=row["created_at"],
            internship_title=row["internship_title"],
            internship_description=row["internship_description"],
            group_name=row["group_name"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            deadline=row["deadline"],
            deadline_state=_deadline_state(row["deadline"], row["submitted_at"]),
        )
        for row in rows
    ]


@router.get("/reports/{report_id}", response_model=ReportDetail)
def report_detail(
    report_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportDetail:
    """Rule 5/38: both the reviewing teacher and the owning student can read
    a report's detail — ownership/authorization differs per role but the
    shape of the response doesn't."""
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = ReportService(db)
    if ctx.role == "STUDENT":
        report = service.get_for_student(ctx.organization_id, ctx.student_id, report_id)
    else:
        report = service.get_for_teacher(ctx.organization_id, ctx.teacher_id, report_id)

    internship = InternshipRepository(db).get(ctx.organization_id, report.internship_id)
    versions_repo = ReportVersionRepository(db)
    versions = versions_repo.list_for_report(report.id, page.offset, page.limit)
    set_pagination_headers(response, page, total=versions_repo.count_for_report(report.id), returned=len(versions))
    return ReportDetail(
        id=report.id,
        internship_id=report.internship_id,
        student_id=report.student_id,
        status=report.status,
        current_version_id=report.current_version_id,
        created_at=report.created_at,
        deadline=internship.deadline.isoformat(),
        internship_title=internship.title,
        versions=[
            ReportVersionOut(
                id=v.id, version_number=v.version_number, submitted_at=v.submitted_at,
                is_late=v.submitted_at.date() > internship.deadline,
            )
            for v in versions
        ],
    )


@router.get("/reports/{report_id}/history", response_model=list[ReportHistoryEntry])
def report_history(
    report_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[ReportHistoryEntry]:
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = ReportService(db)
    entries = service.get_history(
        ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id, page.offset, page.limit
    )
    set_pagination_headers(
        response,
        page,
        total=service.count_history(ctx.organization_id, ctx.role, ctx.teacher_id, ctx.student_id, report_id),
        returned=len(entries),
    )
    return [
        ReportHistoryEntry(
            event=e.event_type.value,
            actor_name=e.actor.full_name if e.actor else None,
            actor_role=None,
            created_at=e.created_at,
            metadata=e.event_metadata,
        )
        for e in entries
    ]


@router.get("/reports/{report_id}/document", response_model=ReportDocumentResponse)
def get_report_document(
    report_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportDocumentResponse:
    """Rule 15/28: same underlying document engine for both roles — a
    Teacher gets a read-only resolved view (via a group they own), a Student
    gets their own editable working draft, with variables resolved either way."""
    require_role(ctx.role, RoleName.TEACHER, RoleName.STUDENT)
    service = ReportService(db)
    if ctx.role == "STUDENT":
        result = service.get_document_for_student(ctx.organization_id, ctx.student_id, report_id)
    else:
        result = service.get_document_for_teacher(ctx.organization_id, ctx.teacher_id, report_id)
    return ReportDocumentResponse(**result)


@router.patch("/reports/{report_id}/document", response_model=ReportDocumentResponse)
def update_report_document(
    report_id: uuid.UUID,
    payload: UpdateReportDocumentRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> ReportDocumentResponse:
    require_role(ctx.role, RoleName.STUDENT)
    service = ReportService(db)
    service.update_document_for_student(
        ctx.organization_id,
        ctx.student_id,
        report_id,
        payload.expected_revision,
        payload.sections,
    )
    result = service.get_document_for_student(ctx.organization_id, ctx.student_id, report_id)
    return ReportDocumentResponse(**result)


@router.post("/reports/{report_id}/submit", response_model=ReportOut)
def submit_report(
    report_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> ReportOut:
    require_role(ctx.role, RoleName.STUDENT)
    report = ReportService(db).submit(ctx.organization_id, ctx.student_id, ctx.user_id, report_id)
    return ReportOut.model_validate(report)


@router.get("/groups/{group_id}/reports", response_model=list[ReportOut])
def group_reports(
    group_id: uuid.UUID, response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> list[ReportOut]:
    require_role(ctx.role, RoleName.TEACHER)
    service = ReportService(db)
    reports = service.list_for_group(ctx.organization_id, ctx.teacher_id, group_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_for_group(ctx.organization_id, ctx.teacher_id, group_id), returned=len(reports))
    return [ReportOut.model_validate(r) for r in reports]


@router.get("/groups/{group_id}/reports/queue", response_model=list[TeacherReviewQueueItem])
def teacher_review_queue(
    group_id: uuid.UUID,
    response: Response,
    page: PaginationParams = Depends(),
    status_filter: Annotated[ReportStatus | None, Query(alias="status")] = None,
    internship_id: uuid.UUID | None = None,
    deadline: ReviewQueueDeadlineFilter | None = None,
    student: Annotated[str | None, Query(max_length=100)] = None,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[TeacherReviewQueueItem]:
    """Paginated, teacher-owned read model for a group's review queue."""
    require_role(ctx.role, RoleName.TEACHER)
    items, total = ReportService(db).list_review_queue(
        ctx.organization_id,
        ctx.teacher_id,
        group_id,
        status_filter=status_filter,
        internship_id=internship_id,
        deadline_filter=deadline.value if deadline else None,
        student_query=student,
        offset=page.offset,
        limit=page.limit,
    )
    set_pagination_headers(response, page, total=total, returned=len(items))
    return [TeacherReviewQueueItem.model_validate(item) for item in items]


@router.get("/groups/{group_id}/reports/{report_id}/next-in-queue", response_model=TeacherReviewQueueItem | None)
def next_teacher_review_queue_item(
    group_id: uuid.UUID,
    report_id: uuid.UUID,
    status_filter: Annotated[ReportStatus | None, Query(alias="status")] = None,
    internship_id: uuid.UUID | None = None,
    deadline: ReviewQueueDeadlineFilter | None = None,
    student: Annotated[str | None, Query(max_length=100)] = None,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> TeacherReviewQueueItem | None:
    require_role(ctx.role, RoleName.TEACHER)
    item = ReportService(db).next_review_queue_item(
        ctx.organization_id,
        ctx.teacher_id,
        group_id,
        report_id,
        status_filter=status_filter,
        internship_id=internship_id,
        deadline_filter=deadline.value if deadline else None,
        student_query=student,
    )
    return TeacherReviewQueueItem.model_validate(item) if item is not None else None
