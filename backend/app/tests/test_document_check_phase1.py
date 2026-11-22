import pytest
from sqlalchemy.exc import IntegrityError

from app.models.document_check import CheckProfile, CheckProfileVersion, CheckRule
from app.tests.conftest import OrgFixture, auth_headers


def _create_published_profile(client, fixture: OrgFixture, *, name: str = "Academic standard") -> tuple[dict, dict]:
    headers = auth_headers(fixture.teacher_token(client))
    profile_response = client.post("/api/v1/check-profiles", headers=headers, json={"name": name})
    assert profile_response.status_code == 201, profile_response.text
    profile = profile_response.json()
    version_response = client.post(
        f"/api/v1/check-profiles/{profile['id']}/versions", headers=headers, json={}
    )
    assert version_response.status_code == 201, version_response.text
    version = version_response.json()
    rules_response = client.put(
        f"/api/v1/check-profiles/{profile['id']}/versions/{version['id']}/rules",
        headers=headers,
        json={
            "rules": [
                {
                    "rule_type": "PAGE_FORMAT_MARGINS",
                    "category": "formatting",
                    "severity": "ERROR",
                    "enabled": True,
                    "sort_order": 0,
                    "config_schema_version": 1,
                    "config": {
                        "page_size": "A4",
                        "orientation": "PORTRAIT",
                        "margins": {"top_mm": 20.0, "right_mm": 15.0, "bottom_mm": 20.0, "left_mm": 30.0},
                        "width_mm": None,
                        "height_mm": None,
                    },
                }
            ]
        },
    )
    assert rules_response.status_code == 200, rules_response.text
    publish_response = client.post(
        f"/api/v1/check-profiles/{profile['id']}/versions/{version['id']}/publish", headers=headers
    )
    assert publish_response.status_code == 200, publish_response.text
    return profile, publish_response.json()


def test_profile_tenant_isolation_and_student_cannot_mutate(client, org_a: OrgFixture, org_b: OrgFixture):
    profile, _ = _create_published_profile(client, org_a)
    other_teacher = auth_headers(org_b.teacher_token(client))
    assert client.get(f"/api/v1/check-profiles/{profile['id']}", headers=other_teacher).status_code == 404
    assert client.patch(
        f"/api/v1/check-profiles/{profile['id']}", headers=other_teacher, json={"name": "Cross tenant"}
    ).status_code == 404

    student_headers = auth_headers(org_a.student_token(client))
    assert client.get("/api/v1/check-profiles", headers=student_headers).status_code == 403
    assert client.post("/api/v1/check-profiles", headers=student_headers, json={"name": "Forbidden"}).status_code == 403


def test_published_rules_can_be_removed_without_erasing_history(client, org_a: OrgFixture):
    profile, version = _create_published_profile(client, org_a)
    headers = auth_headers(org_a.teacher_token(client))
    removed = client.put(
        f"/api/v1/check-profiles/{profile['id']}/versions/{version['id']}/rules",
        headers=headers,
        json={"rules": []},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["id"] != version["id"]
    assert removed.json()["state"] == "DRAFT"
    assert removed.json()["rules"] == []
    assert removed.json()["executable_rule_count"] == 0
    original = client.get(f"/api/v1/check-profiles/{profile['id']}/versions/{version['id']}", headers=headers).json()
    assert original["state"] == "RETIRED"
    assert original["rules"] == version["rules"]
    assert client.patch(
        f"/api/v1/check-profiles/{profile['id']}/versions/{version['id']}",
        headers=headers,
        json={"notes": "silent rewrite"},
    ).status_code == 409


def test_rule_config_remains_strict(client, org_a: OrgFixture):
    headers = auth_headers(org_a.teacher_token(client))

    profile2 = client.post("/api/v1/check-profiles", headers=headers, json={"name": "Strict JSON"}).json()
    draft = client.post(f"/api/v1/check-profiles/{profile2['id']}/versions", headers=headers, json={}).json()
    response = client.put(
        f"/api/v1/check-profiles/{profile2['id']}/versions/{draft['id']}/rules",
        headers=headers,
        json={
            "rules": [{
                "rule_type": "SPELLING_LANGUAGES", "category": "language", "severity": "WARNING",
                "enabled": True, "sort_order": 0, "config_schema_version": 1,
                "config": {"languages": ["en-US"], "ignore_uppercase": True, "ignore_urls": True, "typo": True},
            }]
        },
    )
    assert response.status_code == 422


def test_published_rule_edit_replaces_active_version_and_retires_original(client, org_a: OrgFixture):
    profile, original = _create_published_profile(client, org_a)
    headers = auth_headers(org_a.teacher_token(client))
    old_url = f"/api/v1/check-profiles/{profile['id']}/versions/{original['id']}"
    rules = [{key: value for key, value in rule.items() if key != "id"} for rule in original["rules"]]
    assert client.put(f"{old_url}/rules", headers=headers, json={"rules": rules}).json()["id"] == original["id"]
    rules[0]["config"]["margins"]["left_mm"] = 25.0
    response = client.put(f"{old_url}/rules", headers=headers, json={"rules": rules})
    assert response.status_code == 200, response.text
    current = response.json()
    assert current["id"] != original["id"]
    assert current["state"] == "PUBLISHED"
    assert current["version_number"] == original["version_number"] + 1
    assert current["rules"][0]["id"] != original["rules"][0]["id"]
    assert current["rules"][0]["config"]["margins"]["left_mm"] == 25.0
    historical = client.get(old_url, headers=headers).json()
    assert historical["state"] == "RETIRED"
    assert historical["rules"][0]["config"]["margins"]["left_mm"] == 30.0
    assert client.put(f"{old_url}/rules", headers=headers, json={"rules": rules}).status_code == 409


def test_database_composite_fk_rejects_cross_tenant_version_relationship(db, org_a: OrgFixture, org_b: OrgFixture):
    # The composite tenant FK is authoritative even when a caller bypasses the service.
    profile = CheckProfile(
        organization_id=org_a.org.id,
        created_by_teacher_id=org_a.teacher.id,
        name="Tenant A profile",
    )
    db.add(profile)
    db.flush()
    db.add(CheckProfileVersion(
        organization_id=org_b.org.id,
        profile_id=profile.id,
        version_number=1,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_document_check_entities_have_no_grade_fields():
    for model in (CheckProfile, CheckProfileVersion, CheckRule):
        assert "organization_id" in model.__table__.columns
    assert "grade" not in CheckProfileVersion.__table__.columns
