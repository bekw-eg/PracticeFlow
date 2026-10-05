import uuid

from fastapi import APIRouter, Depends, File, Form, Header, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.rate_limit.dependencies import get_resource_guard
from app.resource_protection import ResourceGuard
from app.schemas.discipline import DisciplineCreate, DisciplineGroupOut, DisciplineOut, DisciplineUpdate, MaterialOut, TopicCreate, TopicOut, TopicUpdate
from app.services.discipline_service import DisciplineService
from app.services.submission_storage import iter_original
from app.services.teaching_material_preflight import material_disposition

router = APIRouter(tags=["disciplines"])


def service(db: Session = Depends(get_db)) -> DisciplineService:
    return DisciplineService(db)


@router.get("/disciplines", response_model=list[DisciplineOut])
def disciplines(response: Response, archived: bool = False, page: PaginationParams = Depends(),
                ctx: RequestContext = Depends(get_current_context), svc: DisciplineService = Depends(service)):
    rows, total = svc.list(ctx, archived, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(rows))
    return rows


@router.post("/disciplines", response_model=DisciplineOut, status_code=201)
def create_discipline(payload: DisciplineCreate, ctx: RequestContext = Depends(get_current_context),
                      svc: DisciplineService = Depends(service)):
    return svc.create(ctx, payload)


@router.get("/disciplines/{discipline_id}", response_model=DisciplineOut)
def discipline(discipline_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context),
               svc: DisciplineService = Depends(service)):
    return svc.get(ctx, discipline_id)


@router.patch("/disciplines/{discipline_id}", response_model=DisciplineOut)
def update_discipline(discipline_id: uuid.UUID, payload: DisciplineUpdate,
                      ctx: RequestContext = Depends(get_current_context), svc: DisciplineService = Depends(service)):
    return svc.update(ctx, discipline_id, payload)


@router.delete("/disciplines/{discipline_id}", status_code=204)
def archive_discipline(discipline_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context),
                       svc: DisciplineService = Depends(service)):
    svc.update(ctx, discipline_id, DisciplineUpdate(is_archived=True))


@router.get("/disciplines/{discipline_id}/groups", response_model=list[DisciplineGroupOut])
def discipline_groups(discipline_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context),
                      svc: DisciplineService = Depends(service)):
    return svc.groups(ctx, discipline_id)


@router.get("/disciplines/{discipline_id}/topics", response_model=list[TopicOut])
def topics(discipline_id: uuid.UUID, response: Response, archived: bool = False, page: PaginationParams = Depends(),
           ctx: RequestContext = Depends(get_current_context), svc: DisciplineService = Depends(service)):
    rows, total = svc.topics(ctx, discipline_id, archived, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(rows))
    return rows


@router.post("/disciplines/{discipline_id}/topics", response_model=TopicOut, status_code=201)
def create_topic(discipline_id: uuid.UUID, payload: TopicCreate, ctx: RequestContext = Depends(get_current_context),
                 svc: DisciplineService = Depends(service)):
    return svc.create_topic(ctx, discipline_id, payload)


@router.get("/topics/{topic_id}", response_model=TopicOut)
def topic(topic_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context), svc: DisciplineService = Depends(service)):
    return svc.topic(ctx, topic_id)


@router.patch("/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: uuid.UUID, payload: TopicUpdate, ctx: RequestContext = Depends(get_current_context),
                 svc: DisciplineService = Depends(service)):
    return svc.update_topic(ctx, topic_id, payload)


@router.delete("/topics/{topic_id}", status_code=204)
def archive_topic(topic_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context),
                  svc: DisciplineService = Depends(service)):
    svc.update_topic(ctx, topic_id, TopicUpdate(is_archived=True))


@router.get("/topics/{topic_id}/materials", response_model=list[MaterialOut])
def materials(topic_id: uuid.UUID, response: Response, page: PaginationParams = Depends(),
              ctx: RequestContext = Depends(get_current_context), svc: DisciplineService = Depends(service)):
    rows, total = svc.materials(ctx, topic_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=total, returned=len(rows))
    return rows


@router.post("/topics/{topic_id}/materials", response_model=MaterialOut, status_code=201)
def upload_material(topic_id: uuid.UUID, response: Response, file: UploadFile = File(),
                    title: str | None = Form(default=None, max_length=255),
                    idempotency_key: str = Header(alias="Idempotency-Key"),
                    ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db),
                    guard: ResourceGuard = Depends(get_resource_guard)):
    try:
        row, created = DisciplineService(db, guard).upload(ctx, topic_id, file, title, idempotency_key)
        response.status_code = 201 if created else 200
        return row
    finally:
        file.file.close()


@router.get("/materials/{material_id}", response_model=MaterialOut)
def material(material_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context),
             svc: DisciplineService = Depends(service)):
    return svc.material(ctx, material_id)


@router.get("/materials/{material_id}/download")
def download_material(material_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context),
                      svc: DisciplineService = Depends(service)):
    row, stream = svc.download(ctx, material_id)
    return StreamingResponse(iter_original(stream), media_type=row.content_type, headers={
        "Content-Disposition": material_disposition(row.original_filename),
        "Content-Length": str(row.size_bytes), "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.delete("/materials/{material_id}", status_code=204)
def delete_material(material_id: uuid.UUID, ctx: RequestContext = Depends(get_current_context),
                    svc: DisciplineService = Depends(service)):
    svc.delete_material(ctx, material_id)
