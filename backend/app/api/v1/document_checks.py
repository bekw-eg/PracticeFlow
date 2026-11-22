import uuid

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.dependencies.features import require_document_check_enabled
from app.models.document_check import CheckProfile, CheckProfileVersion
from app.schemas.review_group import WorkType
from app.api.v1.review_groups import router as review_groups_router
from app.models.enums import RoleName
from app.permissions.rbac import require_role
from app.schemas.document_check import (
    BulkReplaceCheckRulesRequest,
    CheckProfileOut,
    CheckProfileVersionDetail,
    CheckProfileVersionSummary,
    CreateCheckProfileRequest,
    CreateCheckProfileVersionRequest,
    DocumentCheckFindingOut,
    DocumentCheckJobOut,
    DocumentSettingsWrite,
    DocumentSettingsOut,
    DocumentLifecycleWrite,
    DocumentOriginalDelete,
    DocumentRecheckRequest,
    DocumentRunDetailOut,
    LocalPlagiarismMatchOut,
    LocalPlagiarismRunOut,
    ParagraphClassificationOut,
    TeacherDocumentSubmissionOut,
    TeacherDocumentPreviewOut,
    UpdateCheckProfileRequest,
    UpdateCheckProfileVersionRequest,
)
from app.services.document_check_service import CheckProfileService
from app.rate_limit.dependencies import get_resource_guard
from app.resource_protection import ResourceGuard
from app.services.document_check_job_service import DocumentCheckJobService
from app.services.submission_storage import iter_original, original_content_disposition
from app.services.teacher_document_submission_service import TeacherDocumentSubmissionService
from app.services.document_settings_service import DocumentSettingsService
from app.services.local_plagiarism_service import LocalPlagiarismService

router = APIRouter(
    tags=["document-checks"],
    dependencies=[Depends(require_document_check_enabled)],
)


router.include_router(review_groups_router)

def _profile_out(profile: CheckProfile) -> CheckProfileOut:
    return CheckProfileOut(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        created_at=profile.created_at,
        versions=[CheckProfileVersionSummary.model_validate(version) for version in profile.versions],
    )


def _version_detail(version: CheckProfileVersion) -> CheckProfileVersionDetail:
    return CheckProfileVersionDetail.model_validate(version)


@router.get("/check-profiles", response_model=list[CheckProfileOut])
def list_check_profiles(
    response: Response,
    page: PaginationParams = Depends(),
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[CheckProfileOut]:
    require_role(ctx.role, RoleName.TEACHER)
    service = CheckProfileService(db)
    profiles = service.list_profiles(ctx.organization_id, page.offset, page.limit)
    set_pagination_headers(
        response, page, total=service.count_profiles(ctx.organization_id), returned=len(profiles)
    )
    return [_profile_out(profile) for profile in profiles]


@router.post("/check-profiles", response_model=CheckProfileOut, status_code=status.HTTP_201_CREATED)
def create_check_profile(
    payload: CreateCheckProfileRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileOut:
    require_role(ctx.role, RoleName.TEACHER)
    profile = CheckProfileService(db).create_profile(
        ctx.organization_id, ctx.teacher_id, ctx.user_id, payload.name, payload.description
    )
    return _profile_out(profile)


@router.get("/check-profiles/{profile_id}", response_model=CheckProfileOut)
def get_check_profile(
    profile_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileOut:
    require_role(ctx.role, RoleName.TEACHER)
    return _profile_out(CheckProfileService(db).get_profile(ctx.organization_id, profile_id))


@router.patch("/check-profiles/{profile_id}", response_model=CheckProfileOut)
def update_check_profile(
    profile_id: uuid.UUID,
    payload: UpdateCheckProfileRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileOut:
    require_role(ctx.role, RoleName.TEACHER)
    profile = CheckProfileService(db).update_profile(
        ctx.organization_id, profile_id, payload.model_dump(exclude_unset=True)
    )
    return _profile_out(profile)


@router.delete("/check-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check_profile(
    profile_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> None:
    require_role(ctx.role, RoleName.TEACHER)
    CheckProfileService(db).delete_profile(ctx.organization_id, profile_id)


@router.get("/check-profiles/{profile_id}/versions", response_model=list[CheckProfileVersionSummary])
def list_check_profile_versions(
    profile_id: uuid.UUID,
    response: Response,
    page: PaginationParams = Depends(),
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[CheckProfileVersionSummary]:
    require_role(ctx.role, RoleName.TEACHER)
    service = CheckProfileService(db)
    versions = service.list_versions(ctx.organization_id, profile_id, page.offset, page.limit)
    set_pagination_headers(
        response,
        page,
        total=service.count_versions(ctx.organization_id, profile_id),
        returned=len(versions),
    )
    return [CheckProfileVersionSummary.model_validate(version) for version in versions]


@router.post(
    "/check-profiles/{profile_id}/versions",
    response_model=CheckProfileVersionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_check_profile_version(
    profile_id: uuid.UUID,
    payload: CreateCheckProfileVersionRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileVersionDetail:
    require_role(ctx.role, RoleName.TEACHER)
    version = CheckProfileService(db).create_version(
        ctx.organization_id, ctx.user_id, profile_id, payload
    )
    return _version_detail(version)


@router.get(
    "/check-profiles/{profile_id}/versions/{version_id}", response_model=CheckProfileVersionDetail
)
def get_check_profile_version(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileVersionDetail:
    require_role(ctx.role, RoleName.TEACHER)
    return _version_detail(
        CheckProfileService(db).get_version(ctx.organization_id, profile_id, version_id)
    )


@router.patch(
    "/check-profiles/{profile_id}/versions/{version_id}", response_model=CheckProfileVersionDetail
)
def update_check_profile_version(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: UpdateCheckProfileVersionRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileVersionDetail:
    require_role(ctx.role, RoleName.TEACHER)
    version = CheckProfileService(db).update_version(
        ctx.organization_id,
        profile_id,
        version_id,
        payload.model_dump(exclude_unset=True),
    )
    return _version_detail(version)


@router.put(
    "/check-profiles/{profile_id}/versions/{version_id}/rules",
    response_model=CheckProfileVersionDetail,
)
def replace_check_profile_rules(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: BulkReplaceCheckRulesRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileVersionDetail:
    """Save rules; published edits return a replacement version with a new ID."""
    require_role(ctx.role, RoleName.TEACHER)
    version = CheckProfileService(db).replace_rules(
        ctx.organization_id, profile_id, version_id, payload, actor_user_id=ctx.user_id
    )
    return _version_detail(version)


@router.post(
    "/check-profiles/{profile_id}/versions/{version_id}/publish",
    response_model=CheckProfileVersionDetail,
)
def publish_check_profile_version(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileVersionDetail:
    require_role(ctx.role, RoleName.TEACHER)
    version = CheckProfileService(db).publish_version(
        ctx.organization_id, ctx.user_id, profile_id, version_id
    )
    return _version_detail(version)


@router.post(
    "/check-profiles/{profile_id}/versions/{version_id}/retire",
    response_model=CheckProfileVersionDetail,
)
def retire_check_profile_version(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> CheckProfileVersionDetail:
    require_role(ctx.role, RoleName.TEACHER)
    version = CheckProfileService(db).retire_version(
        ctx.organization_id, ctx.user_id, profile_id, version_id
    )
    return _version_detail(version)


@router.get(
    "/document-checks/teacher/submissions",
    response_model=list[TeacherDocumentSubmissionOut],
)
def list_direct_teacher_document_submissions(
    response: Response,
    archived: bool = False,
    page: PaginationParams = Depends(),
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[TeacherDocumentSubmissionOut]:
    response.headers["Cache-Control"] = "private, no-store"
    items, total = TeacherDocumentSubmissionService(db).list(ctx, page.offset, page.limit, archived)
    set_pagination_headers(response, page, total=total, returned=len(items))
    return [TeacherDocumentSubmissionOut.model_validate(item) for item in items]


@router.post(
    "/document-checks/teacher/submissions",
    response_model=TeacherDocumentSubmissionOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": TeacherDocumentSubmissionOut, "description": "Identical idempotent retry"}},
)
def upload_direct_teacher_document_submission(
    response: Response,
    file: UploadFile,
    profile_version_id: Annotated[uuid.UUID, Form()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    student_label: Annotated[str | None, Form(max_length=255)] = None,
    plagiarism_source_disclosure_allowed: Annotated[bool, Form()] = False,
    review_group_id: Annotated[uuid.UUID | None, Form()] = None,
    work_title: Annotated[str | None, Form(max_length=255)] = None,
    work_type: Annotated[WorkType | None, Form()] = None,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    guard: ResourceGuard = Depends(get_resource_guard),
) -> TeacherDocumentSubmissionOut:
    submission, created = TeacherDocumentSubmissionService(db, guard).upload(
        ctx, profile_version_id, file, idempotency_key, student_label, plagiarism_source_disclosure_allowed,
        review_group_id, work_title, work_type,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return TeacherDocumentSubmissionOut.model_validate(submission)


@router.get(
    "/document-checks/teacher/submissions/{submission_id}",
    response_model=TeacherDocumentSubmissionOut,
)
def get_direct_teacher_document_submission(
    submission_id: uuid.UUID,
    response: Response,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> TeacherDocumentSubmissionOut:
    response.headers["Cache-Control"] = "private, no-store"
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    return TeacherDocumentSubmissionOut.model_validate(submission)


@router.get(
    "/document-checks/teacher/submissions/{submission_id}/preview",
    response_model=TeacherDocumentPreviewOut,
)
def preview_direct_teacher_document(
    submission_id: uuid.UUID,
    response: Response,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> TeacherDocumentPreviewOut:
    response.headers["Cache-Control"] = "private, no-store"
    preview = TeacherDocumentSubmissionService(db).preview(ctx, submission_id)
    return TeacherDocumentPreviewOut.model_validate(preview)


@router.get(
    "/document-checks/teacher/submissions/{submission_id}/original",
    response_class=StreamingResponse,
    responses={200: {"content": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
            "schema": {"type": "string", "format": "binary"}},
    }, "description": "Unmodified private Teacher-uploaded original"}},
)
def download_direct_teacher_document_original(
    submission_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    submission, stream = TeacherDocumentSubmissionService(db).download_original(ctx, submission_id)
    return StreamingResponse(
        iter_original(stream), media_type=submission.detected_mime,
        headers={
            "Content-Disposition": original_content_disposition(submission.original_filename),
            "Content-Length": str(submission.size_bytes),
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(stream.close),
    )


@router.get(
    "/document-checks/teacher/submissions/{submission_id}/findings",
    response_model=list[DocumentCheckFindingOut],
)
def list_direct_teacher_document_findings(
    submission_id: uuid.UUID,
    response: Response,
    job_id: uuid.UUID | None = None,
    page: PaginationParams = Depends(),
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[DocumentCheckFindingOut]:
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    job = DocumentSettingsService(db).get_job(submission, job_id) if job_id else (submission.latest_completed_job or submission.job)
    response.headers["Cache-Control"] = "private, no-store"
    items, total = DocumentCheckJobService(db).list_findings(job, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(items))
    return [DocumentCheckFindingOut.model_validate(item) for item in items]


@router.get("/document-checks/teacher/submissions/{submission_id}/settings", response_model=DocumentSettingsOut)
def get_document_settings(submission_id: uuid.UUID, response: Response,
                          ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    draft = DocumentSettingsService(db).ensure(submission)
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return DocumentSettingsOut.model_validate(draft, from_attributes=True)


@router.put("/document-checks/teacher/submissions/{submission_id}/settings", response_model=DocumentSettingsOut)
def save_document_settings(submission_id: uuid.UUID, request: DocumentSettingsWrite, response: Response,
                           ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    service = TeacherDocumentSubmissionService(db)
    submission = service.get(ctx, submission_id)
    if request.page_exclusions.pages:
        from app.services.document_page_exclusions import validate_preview_locations
        preview = service.preview(ctx, submission_id)
        try:
            validate_preview_locations(request.page_exclusions, preview.html)
        except ValueError:
            raise HTTPException(422, detail={"code": "PAGE_LAYOUT_INVALID",
                                            "message": "Reload the document preview and select pages again."}) from None
    if request.paragraph_overrides:
        indexes = {str(item["paragraph_index"]) for item in service.paragraphs(submission)}
        if set(request.paragraph_overrides) - indexes:
            raise HTTPException(422, detail={"code": "PARAGRAPH_INDEX_INVALID", "message": "Unknown paragraph in this document."})
    draft = DocumentSettingsService(db).save(submission, request)
    response.headers["Cache-Control"] = "private, no-store"
    return DocumentSettingsOut.model_validate(draft, from_attributes=True)


@router.get("/document-checks/teacher/submissions/{submission_id}/paragraphs", response_model=list[ParagraphClassificationOut])
def get_document_paragraphs(submission_id: uuid.UUID, response: Response, job_id: uuid.UUID | None = None,
                            ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    service = TeacherDocumentSubmissionService(db)
    submission = service.get(ctx, submission_id)
    settings_service = DocumentSettingsService(db)
    if job_id:
        job = settings_service.get_job(submission, job_id)
        overrides = (job.settings_snapshot or {}).get("paragraph_overrides", {})
    else:
        overrides = settings_service.ensure(submission).paragraph_overrides
    result = service.paragraphs(submission, overrides)
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.post("/document-checks/teacher/submissions/{submission_id}/recheck", response_model=DocumentCheckJobOut)
def recheck_document(submission_id: uuid.UUID, request: DocumentRecheckRequest,
                     idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
                     ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    return DocumentCheckJobOut.model_validate(DocumentSettingsService(db).recheck(ctx, submission, request.revision, idempotency_key))


@router.get("/document-checks/teacher/submissions/{submission_id}/runs", response_model=list[DocumentCheckJobOut])
def get_document_runs(submission_id: uuid.UUID, response: Response, page: PaginationParams = Depends(),
                      ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    items = submission.jobs[page.offset:page.offset + page.limit]
    set_pagination_headers(response, page, total=len(submission.jobs), returned=len(items))
    response.headers["Cache-Control"] = "private, no-store"
    return [DocumentCheckJobOut.model_validate(job) for job in items]


@router.get("/document-checks/teacher/submissions/{submission_id}/runs/{job_id}", response_model=DocumentRunDetailOut)
def get_document_run(submission_id: uuid.UUID, job_id: uuid.UUID, response: Response,
                     ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    service = DocumentSettingsService(db)
    job = service.get_job(submission, job_id)
    response.headers["Cache-Control"] = "private, no-store"
    return DocumentRunDetailOut(**DocumentCheckJobOut.model_validate(job).model_dump(),
                                rules=service.run_rules(submission, job),
                                paragraph_overrides=(job.settings_snapshot or {}).get("paragraph_overrides", {}),
                                page_exclusions=(job.settings_snapshot or {}).get("page_exclusions", {}))


@router.get(
    "/document-checks/teacher/submissions/{submission_id}/plagiarism-runs",
    response_model=list[LocalPlagiarismRunOut],
)
def list_local_plagiarism_runs(
    submission_id: uuid.UUID,
    response: Response,
    page: PaginationParams = Depends(),
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[LocalPlagiarismRunOut]:
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    items, total = LocalPlagiarismService(db).list_runs(submission, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(items))
    response.headers["Cache-Control"] = "private, no-store"
    return [LocalPlagiarismRunOut.model_validate(item) for item in items]


@router.get(
    "/document-checks/teacher/submissions/{submission_id}/plagiarism-runs/{run_id}",
    response_model=LocalPlagiarismRunOut,
)
def get_local_plagiarism_run(
    submission_id: uuid.UUID,
    run_id: uuid.UUID,
    response: Response,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> LocalPlagiarismRunOut:
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    response.headers["Cache-Control"] = "private, no-store"
    return LocalPlagiarismRunOut.model_validate(LocalPlagiarismService(db).get_run(submission, run_id))


@router.get(
    "/document-checks/teacher/submissions/{submission_id}/plagiarism-runs/{run_id}/matches",
    response_model=list[LocalPlagiarismMatchOut],
)
def list_local_plagiarism_matches(
    submission_id: uuid.UUID,
    run_id: uuid.UUID,
    response: Response,
    page: PaginationParams = Depends(),
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> list[LocalPlagiarismMatchOut]:
    submission = TeacherDocumentSubmissionService(db).get(ctx, submission_id)
    service = LocalPlagiarismService(db)
    run = service.get_run(submission, run_id)
    if ctx.teacher_id is None:
        raise HTTPException(404, detail="Local similarity result not found")
    items, total = service.list_matches(run, ctx.teacher_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(items))
    response.headers["Cache-Control"] = "private, no-store"
    result: list[LocalPlagiarismMatchOut] = []
    for match, source in items:
        from app.services.document_lifecycle_service import source_disclosure_allowed
        disclose = source.teacher_id == ctx.teacher_id or source_disclosure_allowed(source)
        result.append(LocalPlagiarismMatchOut(
            id=match.id,
            sequence=match.sequence,
            target_paragraph_index=match.target_paragraph_index,
            source_paragraph_index=match.source_paragraph_index if disclose else None,
            matched_word_count=match.matched_word_count,
            target_excerpt=match.target_excerpt,
            source_excerpt=match.source_excerpt if disclose else None,
            source_submission_id=source.id if disclose else None,
            source_label=(source.student_label or source.original_filename) if disclose else None,
            source_filename=source.original_filename if disclose else None,
            source_restricted=not disclose,
        ))
    return result


@router.put("/document-checks/teacher/submissions/{submission_id}/lifecycle", response_model=TeacherDocumentSubmissionOut)
def update_document_lifecycle(submission_id: uuid.UUID, request: DocumentLifecycleWrite, response: Response,
                              ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    from app.services.document_lifecycle_service import DocumentLifecycleService
    service = TeacherDocumentSubmissionService(db)
    submission = service.get(ctx, submission_id)
    result = DocumentLifecycleService(db, service.storage).update(ctx, submission, request)
    response.headers["Cache-Control"] = "private, no-store"
    return TeacherDocumentSubmissionOut.model_validate(result)


@router.delete("/document-checks/teacher/submissions/{submission_id}/original", response_model=TeacherDocumentSubmissionOut)
def remove_document_original(submission_id: uuid.UUID, request: DocumentOriginalDelete, response: Response,
                              ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)):
    from app.services.document_lifecycle_service import DocumentLifecycleService
    service = TeacherDocumentSubmissionService(db)
    submission = service.get(ctx, submission_id)
    result = DocumentLifecycleService(db, service.storage).delete_original(ctx, submission, request.revision)
    response.headers["Cache-Control"] = "private, no-store"
    return TeacherDocumentSubmissionOut.model_validate(result)
