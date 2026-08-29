from app.tests.conftest import OrgFixture, auth_headers


def test_org_a_teacher_my_groups_never_includes_org_b_groups(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get("/api/v1/groups", headers=auth_headers(token))
    assert resp.status_code == 200
    names = [g["name"] for g in resp.json()]
    assert org_a.group.name in names
    assert org_b.group.name not in names


def test_org_a_teacher_cannot_read_org_b_group_by_id(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get(f"/api/v1/groups/{org_b.group.id}", headers=auth_headers(token))
    # Must not leak existence via a different status code than "not found".
    assert resp.status_code == 403


def test_org_a_teacher_cannot_list_org_b_internships(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get(f"/api/v1/groups/{org_b.group.id}/internships", headers=auth_headers(token))
    assert resp.status_code == 403


def test_org_a_teacher_cannot_create_internship_in_org_b_group(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.post(
        f"/api/v1/groups/{org_b.group.id}/internships",
        headers=auth_headers(token),
        json={
            "title": "Cross-tenant attack",
            "template_version_id": str(org_a.template_version.id),
            "start_date": "2025-01-01",
            "end_date": "2025-02-01",
            "deadline": "2025-02-05",
        },
    )
    assert resp.status_code == 403


def test_org_a_teacher_cannot_use_org_b_template_version_for_own_group(client, org_a: OrgFixture, org_b: OrgFixture):
    """Even inside their OWN group, a teacher must not be able to attach
    another organization's template version to an internship."""
    token = org_a.teacher_token(client)
    resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/internships",
        headers=auth_headers(token),
        json={
            "title": "Using someone else's template",
            "template_version_id": str(org_b.template_version.id),
            "start_date": "2025-01-01",
            "end_date": "2025-02-01",
            "deadline": "2025-02-05",
        },
    )
    assert resp.status_code == 400


def test_org_a_templates_list_excludes_org_b_templates(client, org_a: OrgFixture, org_b: OrgFixture):
    token = org_a.teacher_token(client)
    resp = client.get("/api/v1/templates", headers=auth_headers(token))
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert org_a.template.name in names
    # both fixtures use the same template name "Test Template" by default in this suite;
    # assert by id instead to be unambiguous
    ids = [t["id"] for t in resp.json()]
    assert str(org_b.template.id) not in ids


def test_org_a_teacher_cannot_publish_org_b_internship(client, db, org_a: OrgFixture, org_b: OrgFixture):
    from datetime import date

    from app.models.internship import Internship

    org_b_internship = Internship(
        organization_id=org_b.org.id,
        group_id=org_b.group.id,
        template_version_id=org_b.template_version.id,
        created_by_teacher_id=org_b.teacher.id,
        title="Org B internship",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 2, 1),
        deadline=date(2025, 2, 5),
    )
    db.add(org_b_internship)
    db.commit()

    token = org_a.teacher_token(client)
    resp = client.post(f"/api/v1/internships/{org_b_internship.id}/publish", headers=auth_headers(token))
    # Repository lookup is org-scoped, so a cross-tenant id simply doesn't resolve.
    assert resp.status_code == 404


def test_student_cannot_read_another_students_report(client, db, org_a: OrgFixture):
    """Same-org, different-student isolation (rule 29: Student A must never
    access Student B's report)."""
    from app.models.membership import OrganizationMembership
    from app.models.report import Report
    from app.models.internship import Internship
    from app.models.student import Student
    from app.models.user import User
    from app.core.security import hash_password
    from datetime import date

    other_user = User(email="other-student@org-a.edu", hashed_password=hash_password("Practice123!"), full_name="Other Student")
    db.add(other_user)
    db.flush()
    other_membership = OrganizationMembership(user_id=other_user.id, organization_id=org_a.org.id, role_id=org_a.role_student.id)
    db.add(other_membership)
    db.flush()
    other_student = Student(membership_id=other_membership.id)
    db.add(other_student)
    db.flush()

    internship = Internship(
        organization_id=org_a.org.id,
        group_id=org_a.group.id,
        template_version_id=org_a.template_version.id,
        created_by_teacher_id=org_a.teacher.id,
        title="Shared internship",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 2, 1),
        deadline=date(2025, 2, 5),
    )
    db.add(internship)
    db.flush()

    other_report = Report(organization_id=org_a.org.id, internship_id=internship.id, student_id=other_student.id)
    db.add(other_report)
    db.commit()

    token = org_a.student_token(client)
    resp = client.get(f"/api/v1/reports/{other_report.id}", headers=auth_headers(token))
    assert resp.status_code == 403


def test_group_member_add_is_tenant_scoped(client, org_a: OrgFixture, org_b: OrgFixture):
    """A teacher cannot add org_b's student into org_a's group by guessing the student_id."""
    token = org_a.teacher_token(client)
    resp = client.post(
        f"/api/v1/groups/{org_a.group.id}/students",
        headers=auth_headers(token),
        json={"student_id": str(org_b.student.id)},
    )
    assert resp.status_code == 404
