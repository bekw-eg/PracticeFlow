import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.schemas.document_check import TeacherDocumentSubmissionOut
from app.schemas.review_group import (
    ReviewGroupOut, ReviewGroupSummary, ReviewGroupWrite, ReviewStatus,
    TeacherReviewComplete, TeacherReviewOut, TeacherReviewWrite,
)
from app.api.v1.group_review_reports import router as group_reports_router
from app.services.review_group_service import ReviewGroupService, TeacherReviewService


def private_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/document-checks/teacher", dependencies=[Depends(private_response)])
router.include_router(group_reports_router)


@router.get("/groups", response_model=list[ReviewGroupOut])
def list_groups(response: Response, page: PaginationParams = Depends(),
                ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    items, total = ReviewGroupService(db).list(ctx, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(items))
    return items


@router.post("/groups", response_model=ReviewGroupOut, status_code=201)
def create_group(request: ReviewGroupWrite, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return ReviewGroupService(db).create(ctx, request)


@router.get("/groups/{group_id}", response_model=ReviewGroupOut)
def get_group(group_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return ReviewGroupService(db).get(ctx, group_id)


@router.put("/groups/{group_id}", response_model=ReviewGroupOut)
def update_group(group_id: uuid.UUID, request: ReviewGroupWrite,
                 ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return ReviewGroupService(db).update(ctx, group_id, request)


@router.get("/groups/{group_id}/works", response_model=list[TeacherDocumentSubmissionOut])
def list_works(group_id: uuid.UUID, response: Response, review_status: ReviewStatus | None = None,
               page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    items, total = ReviewGroupService(db).works(ctx, group_id, page.offset, page.limit, review_status)
    set_pagination_headers(response, page, total=total, returned=len(items))
    return items


@router.get("/groups/{group_id}/summary", response_model=ReviewGroupSummary)
def group_summary(group_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return ReviewGroupService(db).summary(ctx, group_id)


@router.put("/submissions/{submission_id}/review", response_model=TeacherReviewOut)
def save_review(submission_id: uuid.UUID, request: TeacherReviewWrite,
                ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return TeacherReviewService(db).save(ctx, submission_id, request)


@router.post("/submissions/{submission_id}/review/complete", response_model=TeacherReviewOut)
def complete_review(submission_id: uuid.UUID, request: TeacherReviewComplete,
                    ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    return TeacherReviewService(db).save(ctx, submission_id, request, complete=True)
