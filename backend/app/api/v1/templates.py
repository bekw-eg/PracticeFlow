import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.dependencies.features import require_legacy_document_editor_enabled
from app.documents.numbering import compute_numbering
from app.documents.schemas import DocumentModel
from app.models.enums import RoleName
from app.models.template import Template
from app.models.template_version import TemplateVersion
from app.permissions.rbac import require_role
from app.schemas.template import (
    CreateTemplateRequest,
    CreateTemplateVersionRequest,
    TemplateOut,
    TemplateVersionDetail,
    TemplateVersionSummary,
    UpdateTemplateVersionDocumentRequest,
)
from app.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


def _version_summary(service: TemplateService, version: TemplateVersion) -> TemplateVersionSummary:
    return TemplateVersionSummary(
        id=version.id,
        version_number=version.version_number,
        is_published=version.is_published,
        is_locked=service.is_locked(version.id),
        created_at=version.created_at,
    )


def _template_out(service: TemplateService, template: Template) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        versions=[_version_summary(service, v) for v in template.versions],
    )


@router.get("", response_model=list[TemplateOut])
def list_templates(response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> list[TemplateOut]:
    """Org-wide list — templates are reusable across groups and, deliberately,
    across teachers within the same organization (rule 8)."""
    require_role(ctx.role, RoleName.TEACHER)
    service = TemplateService(db)
    templates = service.list_for_org(ctx.organization_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_for_org(ctx.organization_id), returned=len(templates))
    return [_template_out(service, t) for t in templates]


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    payload: CreateTemplateRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> TemplateOut:
    require_role(ctx.role, RoleName.TEACHER)
    service = TemplateService(db)
    template = service.create_template(ctx.organization_id, ctx.teacher_id, ctx.user_id, payload.name, payload.description)
    return _template_out(service, template)


@router.post("/{template_id}/versions", response_model=TemplateVersionSummary, status_code=201)
def create_version(
    template_id: uuid.UUID,
    payload: CreateTemplateVersionRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> TemplateVersionSummary:
    require_role(ctx.role, RoleName.TEACHER)
    service = TemplateService(db)
    version = service.create_version(ctx.organization_id, ctx.user_id, template_id)
    return _version_summary(service, version)


@router.get("/{template_id}/versions/{version_id}/document", response_model=TemplateVersionDetail)
def get_version_document(
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> TemplateVersionDetail:
    """Teacher template editor: fetch the RAW document (variables shown as
    {{key}} placeholders, not resolved — there's no student/internship
    context yet at template-editing time)."""
    require_role(ctx.role, RoleName.TEACHER)
    service = TemplateService(db)
    version = service.get_version(ctx.organization_id, version_id)
    document = DocumentModel.model_validate(version.document_data)
    return TemplateVersionDetail(
        id=version.id,
        version_number=version.version_number,
        is_published=version.is_published,
        is_locked=service.is_locked(version.id),
        created_at=version.created_at,
        document=document,
        numbering=compute_numbering(document),
        revision=version.revision,
    )


@router.patch("/{template_id}/versions/{version_id}/document", response_model=TemplateVersionDetail)
def update_version_document(
    template_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: UpdateTemplateVersionDocumentRequest,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_legacy_document_editor_enabled),
) -> TemplateVersionDetail:
    require_role(ctx.role, RoleName.TEACHER)
    service = TemplateService(db)
    version = service.update_document(ctx.organization_id, ctx.user_id, version_id, payload.expected_revision, payload.document)
    updated_document = DocumentModel.model_validate(version.document_data)
    return TemplateVersionDetail(
        id=version.id,
        version_number=version.version_number,
        is_published=version.is_published,
        is_locked=service.is_locked(version.id),
        created_at=version.created_at,
        document=updated_document,
        numbering=compute_numbering(updated_document),
        revision=version.revision,
    )
