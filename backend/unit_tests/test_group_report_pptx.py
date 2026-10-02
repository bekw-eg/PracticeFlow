import io
import zipfile
from xml.etree import ElementTree as ET

import pytest

from app.services.group_report_pptx import NS, REPORT_TEXT, RULE_TYPES, render_group_report


def sample(kind="partial"):
    rows = [{"rule_type": rule, "violations_count": 30 + index, "works_count": 2 + index}
            for index, rule in enumerate(RULE_TYPES if kind == "many" else RULE_TYPES[:1])]
    if kind == "clean":
        rows = []
    snapshot = {"schema_version": 1, "group_name": "БК 2405", "captured_at": "2026-10-03T10:00:00+00:00",
        "summary": {"total_works": 30, "reviewed_works": 12 if kind == "partial" else 30,
            "pending_works": 18 if kind == "partial" else 0, "included_works": 12 if kind == "partial" else 30,
            "truncated_works": 2 if kind == "many" else 0, "violations": rows}, "skipped_works": 2 if kind == "many" else 0}
    content = {"title": "Результаты проверки работ группы БК 2405", "introduction": "Проверены работы группы по сохранённым правилам.",
        "conclusions": "" if kind == "clean" else "Преподаватель добавляет свои выводы.",
        "selected_rule_types": [row["rule_type"] for row in rows], "examples": [], "remarks": []}
    if kind in {"partial", "many"}:
        content["examples"] = [{"id": "not-exported", "rule_type": RULE_TYPES[0], "location": {"paragraph_index": 8},
                               "actual": {"value": 10, "unit": "mm"}, "expected": {"value": 20, "unit": "mm"}}]
    if kind == "long":
        content["title"] = "Заголовок с длинным текстом " * 15
        content["conclusions"] = "Длинные выводы преподавателя сохраняют содержание на дополнительных слайдах. " * 18
        content["introduction"] = "НепрерывныйТекст" * 45
    return snapshot, content


@pytest.mark.parametrize("locale", ["ru", "kk", "en"])
@pytest.mark.parametrize("kind", ["partial", "clean", "many", "long"])
def test_real_editable_package_geometry_chart_and_text(kind, locale):
    snapshot, content = sample(kind)
    payload = render_group_report(snapshot, content, locale)
    with zipfile.ZipFile(io.BytesIO(payload)) as package:
        slides = [name for name in package.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        cover = ET.fromstring(package.read("ppt/slides/slide1.xml"))
        cover_text = " ".join(item.text or "" for item in cover.findall(".//a:t", NS))
        assert snapshot["group_name"] in cover_text
        assert snapshot["captured_at"][:10] in cover_text
        all_text = []
        for name in slides:
            root = ET.fromstring(package.read(name))
            assert {item.get("lang") for item in root.findall(".//a:rPr", NS)} == {
                {"ru": "ru-RU", "kk": "kk-KZ", "en": "en-US"}[locale]}
            all_text.extend(item.text or "" for item in root.findall(".//a:t", NS)
                            if not (item.text or "").startswith("PracticeFlow")
                            and item.text not in {REPORT_TEXT[locale]["conclusions"], REPORT_TEXT[locale]["cover"]})
            for transform in root.findall(".//a:xfrm", NS) + root.findall(".//p:xfrm", NS):
                offset, extent = transform.find("a:off", NS), transform.find("a:ext", NS)
                if offset is not None and extent is not None:
                    assert 0 <= int(offset.attrib["x"]) + int(extent.attrib["cx"]) <= 12192000
                    assert 0 <= int(offset.attrib["y"]) + int(extent.attrib["cy"]) <= 6858000
        joined = "".join(all_text).replace(" ", "").replace("\n", "")
        assert content["conclusions"].replace(" ", "").replace("\n", "") in joined
        assert content["title"].replace(" ", "").replace("\n", "") in joined
        if kind == "long":
            assert len(slides) > 10
        charts = [name for name in package.namelist() if name.startswith("ppt/charts/chart") and name.endswith(".xml")]
        if kind == "clean":
            assert not charts
            assert REPORT_TEXT[locale]["no_findings"].replace(" ", "") in joined
        else:
            assert charts
            values = []
            for name in charts:
                root = ET.fromstring(package.read(name))
                values.extend(int(item.text) for item in root.findall(".//c:val/c:numRef/c:numCache/c:pt/c:v", NS))
            assert values == [row["works_count"] for row in snapshot["summary"]["violations"]]
            for name in package.namelist():
                if name.endswith(".xlsx"):
                    with zipfile.ZipFile(io.BytesIO(package.read(name))) as workbook:
                        assert "xl/worksheets/sheet1.xml" in workbook.namelist()
        assert "not-exported" not in joined
