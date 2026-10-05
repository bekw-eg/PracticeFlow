"""Real PostgreSQL and API tests for the curriculum tenant/owner boundary."""
import hashlib
import io
from pathlib import Path
import uuid
import zipfile
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.models.discipline import Discipline, DisciplineGroup, DisciplineTopic, TeachingMaterial
from app.models.membership import OrganizationMembership
from app.models.group import Group
from app.models.teacher import Teacher
from app.rate_limit.dependencies import get_resource_guard
from app.repositories.file_repository import FileRepository
from app.resource_protection import MemoryResourceGuard, ResourceProtectionConfig
from app.storage.base import StorageUnavailableError
from app.storage.local import LocalStorageService
from app.tests.conftest import auth_headers
from app.tests.test_document_check_phase21 import docx_bytes

PREFIX = "/api/v1"
PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def pptx_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/></Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
        archive.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>')
    return stream.getvalue()


@pytest.fixture
def material_storage(monkeypatch, tmp_path):
    storage = LocalStorageService(str(tmp_path / "private"))
    monkeypatch.setattr("app.services.discipline_service.get_storage_service", lambda: storage)
    guard = MemoryResourceGuard(ResourceProtectionConfig.from_settings())
    app.dependency_overrides[get_resource_guard] = lambda: guard
    return storage


def headers(org, client):
    return auth_headers(org.teacher_token(client))


def curriculum(client, auth, group_ids=None):
    response = client.post(PREFIX + "/disciplines", headers=auth, json={
        "name": "Web Development", "description": "Curriculum", "academic_year": "2026–2027",
        "group_ids": group_ids or [],
    })
    assert response.status_code == 201, response.text
    discipline = response.json()
    response = client.post(f"{PREFIX}/disciplines/{discipline['id']}/topics", headers=auth, json={
        "title": "React Hooks", "description": "Hooks lecture", "learning_goal": "Use useState and useEffect",
    })
    assert response.status_code == 201, response.text
    return discipline, response.json()


def upload(client, auth, topic, *, extension="pdf", body=PDF, key=None, title=None, content_type=None):
    return client.post(f"{PREFIX}/topics/{topic['id']}/materials",
        headers={**auth, "Idempotency-Key": key or str(uuid.uuid4())},
        data={"title": title} if title else {},
        files={"file": ("lecture." + extension, body, content_type or MIME.get(extension, "application/octet-stream"))})


def test_teacher_create_persistence_edit_order_and_groups(client, db, org_a):
    auth = headers(org_a, client)
    discipline, topic = curriculum(client, auth, [str(org_a.group.id)])
    row = db.scalar(select(Discipline).where(Discipline.id == uuid.UUID(discipline["id"])))
    assert row.organization_id == org_a.org.id
    assert row.created_by_user_id == org_a.teacher_user.id
    assert client.get(PREFIX + "/disciplines", headers=auth).json()[0]["id"] == discipline["id"]
    assert client.get(f"{PREFIX}/disciplines/{discipline['id']}/groups", headers=auth).json()[0]["id"] == str(org_a.group.id)
    assert topic["position"] == 0
    second = client.post(f"{PREFIX}/disciplines/{discipline['id']}/topics", headers=auth, json={"title": "Effects"}).json()
    assert second["position"] == 1
    assert client.patch(f"{PREFIX}/topics/{topic['id']}", headers=auth, json={
        "title": "React state", "learning_goal": "Manage state", "position": 4,
    }).status_code == 200
    topics = client.get(f"{PREFIX}/disciplines/{discipline['id']}/topics", headers=auth)
    assert topics.json()[0]["id"] == second["id"]
    assert topics.headers["x-total-count"] == "2"
    assert client.patch(f"{PREFIX}/disciplines/{discipline['id']}", headers=auth,
                        json={"name": "Web", "group_ids": []}).status_code == 200
    assert client.get(f"{PREFIX}/disciplines/{discipline['id']}/groups", headers=auth).json() == []


def test_role_membership_and_payload_are_server_validated(client, db, org_a):
    student = auth_headers(org_a.student_token(client))
    assert client.post(PREFIX + "/disciplines", headers=student, json={"name": "Denied"}).status_code == 403
    auth = headers(org_a, client)
    assert client.post(PREFIX + "/disciplines", json={"name": "Anonymous"}).status_code == 401
    for payload in [{"name": "   "}, {"name": "X", "organization_id": str(uuid.uuid4())},
                    {"name": "X", "created_by_user_id": str(uuid.uuid4())}]:
        assert client.post(PREFIX + "/disciplines", headers=auth, json=payload).status_code == 422
    discipline, topic = curriculum(client, auth)
    for path, payload in [(f"/disciplines/{discipline['id']}", {"name": None}),
                          (f"/topics/{topic['id']}", {"position": None})]:
        assert client.patch(PREFIX + path, headers=auth, json=payload).status_code == 422
    membership = org_a.teacher.membership
    membership.is_active = False
    db.commit()
    assert client.get(PREFIX + "/disciplines", headers=auth).status_code == 401


def test_other_tenant_and_same_tenant_teacher_cannot_probe_objects(client, db, org_a, org_b, material_storage):
    auth = headers(org_a, client)
    discipline, topic = curriculum(client, auth)
    material = upload(client, auth, topic).json()
    outsider = headers(org_b, client)
    for candidate in [outsider]:
        assert client.get(PREFIX + "/disciplines", headers=candidate).json() == []
        for path in [f"/disciplines/{discipline['id']}", f"/disciplines/{discipline['id']}/groups",
                     f"/disciplines/{discipline['id']}/topics", f"/topics/{topic['id']}",
                     f"/topics/{topic['id']}/materials", f"/materials/{material['id']}",
                     f"/materials/{material['id']}/download"]:
            assert client.get(PREFIX + path, headers=candidate).status_code == 404
        assert client.post(f"{PREFIX}/disciplines/{discipline['id']}/topics", headers=candidate,
                           json={"title": "Intrusion"}).status_code == 404
        assert client.patch(f"{PREFIX}/topics/{topic['id']}", headers=candidate,
                            json={"title": "Intrusion"}).status_code == 404
        assert upload(client, candidate, topic).status_code == 404
        for path in [f"/disciplines/{discipline['id']}", f"/topics/{topic['id']}", f"/materials/{material['id']}"]:
            assert client.delete(PREFIX + path, headers=candidate).status_code == 404
    membership = OrganizationMembership(user_id=org_b.teacher_user.id, organization_id=org_a.org.id,
                                         role_id=org_a.role_teacher.id)
    db.add(membership)
    db.flush()
    db.add(Teacher(membership_id=membership.id))
    db.commit()
    colleague = auth_headers(org_a.login(client, org_b.teacher_user.email))
    assert client.get(f"{PREFIX}/disciplines/{discipline['id']}", headers=colleague).status_code == 404
    assert client.get(f"{PREFIX}/materials/{material['id']}/download", headers=colleague).status_code == 404
    assert client.delete(f"{PREFIX}/materials/{material['id']}", headers=colleague).status_code == 404


def test_cannot_link_foreign_or_unassigned_group_and_db_enforces_tenant(client, db, org_a, org_b):
    auth = headers(org_a, client)
    assert client.post(PREFIX + "/disciplines", headers=auth, json={
        "name": "Invalid link", "group_ids": [str(org_b.group.id)],
    }).status_code == 404
    discipline, topic = curriculum(client, auth)
    unassigned = Group(organization_id=org_a.org.id, name="Unassigned")
    db.add(unassigned)
    db.commit()
    assert client.patch(f"{PREFIX}/disciplines/{discipline['id']}", headers=auth,
                        json={"group_ids": [str(unassigned.id)]}).status_code == 404
    assert client.patch(f"{PREFIX}/disciplines/{discipline['id']}", headers=auth,
                        json={"group_ids": [str(org_b.group.id)]}).status_code == 404
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(DisciplineGroup(organization_id=org_a.org.id, discipline_id=uuid.UUID(discipline["id"]),
                               group_id=org_b.group.id))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(DisciplineTopic(organization_id=org_b.org.id, discipline_id=uuid.UUID(discipline["id"]),
                              title="Wrong tenant", position=0))
        db.flush()
    other, _ = curriculum(client, headers(org_b, client))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(TeachingMaterial(organization_id=org_b.org.id, discipline_id=uuid.UUID(other["id"]),
            topic_id=uuid.UUID(topic["id"]), uploaded_by_user_id=org_b.teacher_user.id, title="Wrong parent",
            original_filename="x.pdf", storage_key="synthetic/wrong-parent", content_type=MIME["pdf"],
            size_bytes=1, sha256="a" * 64, idempotency_key="synthetic"))
        db.flush()


@pytest.mark.parametrize("extension", ["pdf", "docx", "pptx"])
def test_material_upload_roundtrip_idempotency_and_private_metadata(client, db, org_a, material_storage, extension):
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    if extension == "docx":
        body = docx_bytes()
    elif extension == "pptx":
        body = pptx_bytes()
    else:
        body = PDF
    key = str(uuid.uuid4())
    accepted = upload(client, auth, topic, extension=extension, body=body, key=key)
    assert accepted.status_code == 201, accepted.text
    material = accepted.json()
    assert material["sha256"] == hashlib.sha256(body).hexdigest()
    assert material["size_bytes"] == len(body)
    assert material["content_type"] == MIME[extension]
    assert "storage_key" not in material and "organization_id" not in material and "idempotency_key" not in material
    retry = upload(client, auth, topic, extension=extension, body=body, key=key)
    assert retry.status_code == 200 and retry.json()["id"] == material["id"]
    assert upload(client, auth, topic, extension=extension, body=body, key=key, title="Different").status_code == 409
    download = client.get(f"{PREFIX}/materials/{material['id']}/download", headers=auth)
    assert download.status_code == 200 and download.content == body
    assert download.headers["cache-control"] == "private, no-store"
    assert "attachment" in download.headers["content-disposition"]
    assert FileRepository(db).total_size_bytes(org_a.org.id) == len(body)
    assert client.get(f"{PREFIX}/topics/{topic['id']}/materials", headers=auth).json()[0]["id"] == material["id"]
    assert db.scalar(select(func.count()).select_from(TeachingMaterial)) == 1


@pytest.mark.parametrize("extension,body,content_type", [
    ("exe", b"MZ unsafe", None), ("pdf", b"HTML disguised as PDF", None),
    ("docx", PDF, None), ("pptx", docx_bytes(), None), ("pdf", PDF, "text/html"),
    ("docx", docx_bytes(extra={"word/vbaProject.bin": b"macro"}), None),
    ("pptx", docx_bytes(extra={"../escape": b"x"}), None),
    ("pdf", b"", None),
])
def test_invalid_material_rejected(client, db, org_a, material_storage, extension, body, content_type):
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    rejected = upload(client, auth, topic, extension=extension, body=body, content_type=content_type)
    assert rejected.status_code == 400, rejected.text
    assert db.scalar(select(func.count()).select_from(TeachingMaterial)) == 0
    assert not list(material_storage.root.rglob("*.*"))


def test_upload_byte_and_multipart_limits(client, org_a, material_storage, monkeypatch):
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    monkeypatch.setattr("app.services.teaching_material_preflight.MAX_MATERIAL_BYTES", 10)
    assert upload(client, auth, topic).status_code == 413
    monkeypatch.setattr("app.document_submission_limits.MAX_MATERIAL_BYTES", 10)
    oversized = client.post(f"{PREFIX}/topics/{topic['id']}/materials", headers={
        **auth, "Idempotency-Key": str(uuid.uuid4()), "Content-Type": "multipart/form-data; boundary=x",
    }, content=b"x" * (64 * 1024 + 11))
    assert oversized.status_code == 413


def test_archive_preserves_data_and_material_delete_cleans_storage(client, db, org_a, material_storage):
    auth = headers(org_a, client)
    discipline, topic = curriculum(client, auth)
    material = upload(client, auth, topic).json()
    assert client.delete(f"{PREFIX}/topics/{topic['id']}", headers=auth).status_code == 204
    assert client.get(f"{PREFIX}/topics/{topic['id']}", headers=auth).json()["is_archived"] is True
    assert client.get(f"{PREFIX}/disciplines/{discipline['id']}/topics", headers=auth).json() == []
    assert len(client.get(f"{PREFIX}/disciplines/{discipline['id']}/topics?archived=true", headers=auth).json()) == 1
    assert upload(client, auth, topic).status_code == 409
    assert client.delete(f"{PREFIX}/disciplines/{discipline['id']}", headers=auth).status_code == 204
    assert client.get(PREFIX + "/disciplines", headers=auth).json() == []
    assert len(client.get(PREFIX + "/disciplines?archived=true", headers=auth).json()) == 1
    assert client.get(f"{PREFIX}/materials/{material['id']}/download", headers=auth).content == PDF
    assert client.delete(f"{PREFIX}/materials/{material['id']}", headers=auth).status_code == 204
    assert client.get(f"{PREFIX}/materials/{material['id']}/download", headers=auth).status_code == 404
    assert client.get(f"{PREFIX}/topics/{topic['id']}/materials", headers=auth).json() == []
    assert FileRepository(db).total_size_bytes(org_a.org.id) == 0
    assert not list(material_storage.root.rglob("*.*"))
    assert client.delete(f"{PREFIX}/materials/{material['id']}", headers=auth).status_code == 204


def test_storage_failure_never_exposes_deleted_material_and_retry_cleans_it(client, db, org_a, material_storage, monkeypatch):
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    material = upload(client, auth, topic).json()
    original_delete = material_storage.delete
    monkeypatch.setattr(material_storage, "delete", lambda key: (_ for _ in ()).throw(StorageUnavailableError("offline")))
    assert client.delete(f"{PREFIX}/materials/{material['id']}", headers=auth).status_code == 503
    assert client.get(f"{PREFIX}/materials/{material['id']}", headers=auth).status_code == 404
    assert FileRepository(db).total_size_bytes(org_a.org.id) == len(PDF)
    monkeypatch.setattr(material_storage, "delete", original_delete)
    assert client.delete(f"{PREFIX}/materials/{material['id']}", headers=auth).status_code == 204
    assert FileRepository(db).total_size_bytes(org_a.org.id) == 0


def test_failed_db_commit_removes_new_orphan(client, db, org_a, material_storage):
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    with patch.object(db, "commit", side_effect=RuntimeError("synthetic failure")):
        assert upload(client, auth, topic).status_code == 503
    assert db.scalar(select(func.count()).select_from(TeachingMaterial)) == 0
    assert not list(material_storage.root.rglob("*.*"))


def test_student_cannot_mutate_topic_or_read_material(client, org_a, material_storage):
    teacher = headers(org_a, client)
    discipline, topic = curriculum(client, teacher)
    material = upload(client, teacher, topic).json()
    student = auth_headers(org_a.student_token(client))
    assert client.post(f"{PREFIX}/disciplines/{discipline['id']}/topics", headers=student, json={"title": "Denied"}).status_code == 403
    assert client.patch(f"{PREFIX}/topics/{topic['id']}", headers=student, json={"title": "Denied"}).status_code == 403
    assert upload(client, student, topic).status_code == 403
    assert client.get(f"{PREFIX}/materials/{material['id']}/download", headers=student).status_code == 403


def test_existing_presentation_template_is_accepted_as_original_material(client, org_a, material_storage):
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    body = (Path(__file__).resolve().parents[1] / "documents/templates/group_review_base.pptx").read_bytes()
    result = upload(client, auth, topic, extension="pptx", body=body)
    assert result.status_code == 201, result.text
    assert client.get(f"{PREFIX}/materials/{result.json()['id']}/download", headers=auth).content == body


def test_lost_commit_acknowledgement_preserves_accepted_original(client, db, org_a, material_storage):
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    key = str(uuid.uuid4())
    original_commit = db.commit

    def lost_acknowledgement():
        original_commit()
        raise RuntimeError("Synthetic lost acknowledgement")

    with patch.object(db, "commit", side_effect=lost_acknowledgement):
        assert upload(client, auth, topic, key=key).status_code == 503
    retry = upload(client, auth, topic, key=key)
    assert retry.status_code == 200, retry.text
    assert client.get(f"{PREFIX}/materials/{retry.json()['id']}/download", headers=auth).content == PDF
    assert db.scalar(select(func.count()).select_from(TeachingMaterial)) == 1


def test_storage_migration_includes_active_materials_and_skips_deleted(client, db, org_a, material_storage):
    from scripts.migrate_local_storage_to_s3 import candidates_from_database
    auth = headers(org_a, client)
    _, topic = curriculum(client, auth)
    material = upload(client, auth, topic).json()
    candidates = [row for row in candidates_from_database(db) if row.source == "teaching_material"]
    assert len(candidates) == 1 and candidates[0].expected_size_bytes == len(PDF)
    assert client.delete(f"{PREFIX}/materials/{material['id']}", headers=auth).status_code == 204
    assert not [row for row in candidates_from_database(db) if row.source == "teaching_material"]
