"""Bounded, editable OOXML presentations from saved group evidence.

The checked-in blank 16:9 template was authored with Artifact Tool. Runtime
uses stdlib OOXML only: no AI, Node process, office installation or new queue.
Text is conservatively wrapped and paginated, never shrunk to fit.
"""
import io
import math
import textwrap
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import HTTPException

REPORT_TEXT = {
    "ru": {
        "units": {"mm": "мм", "pt": "пт", "multiple": "кратно"},
        "values": {"LEFT": "По левому краю", "CENTER": "По центру", "RIGHT": "По правому краю", "JUSTIFY": "По ширине", "PORTRAIT": "Книжная", "LANDSCAPE": "Альбомная", "CUSTOM": "Свой вариант", "UNKNOWN": "Не определено"},
        "default_title": "Результаты проверки работ группы {group}", "cover": "Отчёт о проверке группы",
        "date": "Дата формирования", "scope": "Объём проверки", "total": "Всего работ", "reviewed": "Проверено преподавателем",
        "pending": "Ожидают проверки", "included": "Включено в статистику", "problems": "Основные проблемы",
        "statistics": "Подробная статистика", "type": "Тип нарушения", "violations": "Нарушений", "works": "Работ с нарушением",
        "introduction": "Вступление", "examples": "Выбранные примеры ошибок", "example": "Пример {number}",
        "location": "Место в документе", "actual": "Фактическое значение", "expected": "Требование проверки",
        "conclusions": "Выводы преподавателя", "remarks": "Выбранные замечания преподавателя", "empty_text": "Текст не добавлен",
        "no_findings": "В сохранённых результатах нарушений не обнаружено", "no_selection": "Типы нарушений не выбраны",
        "no_examples": "Примеры не выбраны", "unknown": "Не указано или исключено из безопасного примера",
        "partial": "Проверена только часть группы: {reviewed} из {total}. В статистику включено: {included}.",
        "truncated": "Список findings ограничен у {count} работ. Статистика неполная и показывает только сохранённые нарушения.",
        "skipped": "В {count} работах часть правил не выполнена. Отсутствие findings не означает отсутствие ошибок по всем требованиям.",
        "missing": "Включено {included} из {reviewed} завершённых проверок: часть закреплённых результатов недоступна.",
        "limits": "Статистика основана на завершённых проверках преподавателя и закреплённых результатах анализа. Проверяются только исполняемые правила; академические оценки не выставляются.",
        "warnings": "Охват и ограничения", "paragraph_index": "Абзац", "section_index": "Раздел", "run_index": "Фрагмент",
        "table_index": "Таблица", "page": "Страница", "yes": "Да", "no": "Нет",
        "rule_types": ["Формат страницы и поля", "Шрифты и размеры", "Интервалы и отступы", "Заголовки", "Таблицы", "Подписи рисунков", "Список источников", "Обязательные разделы", "Орфография и языки"],
    },
    "kk": {
        "units": {"mm": "мм", "pt": "пт", "multiple": "есе"},
        "values": {"LEFT": "Сол жаққа", "CENTER": "Ортаға", "RIGHT": "Оң жаққа", "JUSTIFY": "Ені бойынша", "PORTRAIT": "Кітаптық", "LANDSCAPE": "Альбомдық", "CUSTOM": "Өз нұсқасы", "UNKNOWN": "Анықталмаған"},
        "default_title": "{group} тобының жұмыстарын тексеру нәтижелері", "cover": "Топты тексеру есебі",
        "date": "Қалыптастыру күні", "scope": "Тексеру көлемі", "total": "Барлық жұмыстар", "reviewed": "Оқытушы тексерген",
        "pending": "Тексеруді күтуде", "included": "Статистикаға енгізілген", "problems": "Негізгі мәселелер",
        "statistics": "Толық статистика", "type": "Бұзушылық түрі", "violations": "Бұзушылықтар", "works": "Бұзушылығы бар жұмыстар",
        "introduction": "Кіріспе", "examples": "Таңдалған қате мысалдары", "example": "{number}-мысал",
        "location": "Құжаттағы орны", "actual": "Нақты мәні", "expected": "Тексеру талабы",
        "conclusions": "Оқытушы қорытындысы", "remarks": "Оқытушының таңдалған ескертулері", "empty_text": "Мәтін қосылмаған",
        "no_findings": "Сақталған нәтижелерде бұзушылықтар табылмады", "no_selection": "Бұзушылық түрлері таңдалмаған",
        "no_examples": "Мысалдар таңдалмаған", "unknown": "Көрсетілмеген немесе қауіпсіз мысалдан алынып тасталған",
        "partial": "Топтың бір бөлігі ғана тексерілді: {total} жұмыстың {reviewed}. Статистикаға енгізілгені: {included}.",
        "truncated": "{count} жұмыста findings тізімі шектелген. Статистика толық емес, тек сақталған бұзушылықтарды көрсетеді.",
        "skipped": "{count} жұмыста кейбір ережелер орындалмады. Findings болмауы барлық талаптар бойынша қате жоқ екенін білдірмейді.",
        "missing": "{reviewed} аяқталған тексерудің {included} енгізілді: кейбір бекітілген нәтижелер қолжетімсіз.",
        "limits": "Статистика оқытушы аяқтаған тексерулерге және бекітілген талдау нәтижелеріне негізделген. Тек орындалатын ережелер тексеріледі; академиялық баға қойылмайды.",
        "warnings": "Қамту және шектеулер", "paragraph_index": "Абзац", "section_index": "Бөлім", "run_index": "Үзінді",
        "table_index": "Кесте", "page": "Бет", "yes": "Иә", "no": "Жоқ",
        "rule_types": ["Бет пішімі мен жиектері", "Қаріптер мен өлшемдер", "Аралықтар мен шегіністер", "Тақырыптар", "Кестелер", "Сурет жазулары", "Дереккөздер тізімі", "Міндетті бөлімдер", "Емле және тілдер"],
    },
    "en": {
        "units": {"mm": "mm", "pt": "pt", "multiple": "multiple"},
        "values": {"LEFT": "Left aligned", "CENTER": "Centered", "RIGHT": "Right aligned", "JUSTIFY": "Justified", "PORTRAIT": "Portrait", "LANDSCAPE": "Landscape", "CUSTOM": "Custom", "UNKNOWN": "Unknown"},
        "default_title": "Review results for group {group}", "cover": "Group review report",
        "date": "Report date", "scope": "Review coverage", "total": "Total works", "reviewed": "Reviewed by teacher",
        "pending": "Awaiting review", "included": "Included in statistics", "problems": "Main issues",
        "statistics": "Detailed statistics", "type": "Violation type", "violations": "Violations", "works": "Affected works",
        "introduction": "Introduction", "examples": "Selected violation examples", "example": "Example {number}",
        "location": "Document location", "actual": "Actual value", "expected": "Check requirement",
        "conclusions": "Teacher conclusions", "remarks": "Explicitly selected teacher remarks", "empty_text": "No text added",
        "no_findings": "No violations found in the saved results", "no_selection": "No violation types selected",
        "no_examples": "No examples selected", "unknown": "Unavailable or excluded from the safe example",
        "partial": "Only part of the group was reviewed: {reviewed} of {total}. Included in statistics: {included}.",
        "truncated": "Findings were limited for {count} works. Statistics are incomplete and count only saved violations.",
        "skipped": "Some rules were not executed for {count} works. No findings does not mean all requirements were satisfied.",
        "missing": "Included {included} of {reviewed} completed reviews: some pinned results are unavailable.",
        "limits": "Statistics use completed teacher reviews and pinned analysis results. Only executable rules are checked; no academic grades are assigned.",
        "warnings": "Coverage and limitations", "paragraph_index": "Paragraph", "section_index": "Section", "run_index": "Run",
        "table_index": "Table", "page": "Page", "yes": "Yes", "no": "No",
        "rule_types": ["Page format and margins", "Fonts and sizes", "Spacing and indents", "Headings", "Tables", "Figure captions", "References", "Required sections", "Spelling and languages"],
    },
}
RULE_TYPES = ["PAGE_FORMAT_MARGINS", "FONTS_SIZES", "PARAGRAPH_SPACING_INDENTS", "HEADINGS", "TABLES",
              "FIGURE_CAPTIONS", "REFERENCES", "REQUIRED_SECTIONS", "SPELLING_LANGUAGES"]
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
      "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
      "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
FONT = "Arial"
EMU = 9525


def node(tag, parent=None, **attrs):
    prefix, name = tag.split(":")
    element = ET.Element(f"{{{NS[prefix]}}}{name}", {key: str(value) for key, value in attrs.items()})
    if parent is not None:
        parent.append(element)
    return element


def xml(element):
    payload = ET.tostring(element, encoding="utf-8", xml_declaration=True)
    # OPC package metadata requires a default namespace, rather than a
    # namespace prefix accepted by general XML parsers.
    for prefix in ("ct", "rel"):
        if element.tag.startswith("{" + NS[prefix] + "}"):
            payload = payload.replace(f"xmlns:{prefix}=".encode(), b"xmlns=")
            payload = payload.replace(f"<{prefix}:".encode(), b"<").replace(f"</{prefix}:".encode(), b"</")
    return payload


def lines(text, width=1120, size=20, *, break_words=True):
    # A full em per character plus 15% reserve is intentionally conservative
    # for Arial in Latin/Cyrillic/Kazakh and Office's fallback fonts.
    count = max(8, math.floor(width / (size * 96 / 72 * 1.15)))
    return [line for paragraph in text.splitlines() or [""]
            for line in textwrap.wrap(paragraph, width=count, replace_whitespace=False, drop_whitespace=False,
                                      break_long_words=break_words, break_on_hyphens=break_words) or [""]]


def paragraphs(parent, value, size=20, color="18334A", bold=False, lang="ru-RU"):
    for line in value:
        paragraph = node("a:p", parent)
        props = node("a:pPr", paragraph)
        spacing = node("a:lnSpc", props)
        node("a:spcPts", spacing, val=int(size * 150))
        node("a:buNone", props)
        run = node("a:r", paragraph)
        rp = node("a:rPr", run, lang=lang, sz=size * 100, b=int(bold))
        fill = node("a:solidFill", rp)
        node("a:srgbClr", fill, val=color)
        for face in ("latin", "ea", "cs"):
            node(f"a:{face}", rp, typeface=FONT)
        node("a:t", run).text = "".join(char for char in line if char in "\t\n" or ord(char) >= 32)
        node("a:endParaRPr", paragraph, sz=size * 100)


class Deck:
    def __init__(self, timeout_seconds, locale):
        self.deadline = time.monotonic() + timeout_seconds
        self.lang = {"ru": "ru-RU", "kk": "kk-KZ", "en": "en-US"}[locale]
        self.slides = []
        self.charts = []

    def slide(self, heading):
        if time.monotonic() > self.deadline or len(self.slides) >= 250:
            raise HTTPException(422, "Presentation is too large. Shorten the selected text.")
        root = node("p:sld")
        common = node("p:cSld", root)
        bg = node("p:bgPr", node("p:bg", common))
        node("a:srgbClr", node("a:solidFill", bg), val="FFFFFF")
        tree = node("p:spTree", common)
        nv = node("p:nvGrpSpPr", tree)
        node("p:cNvPr", nv, id=1, name="")
        node("p:cNvGrpSpPr", nv)
        node("p:nvPr", nv)
        node("p:grpSpPr", tree)
        slide = {"root": root, "tree": tree, "rels": node("rel:Relationships"), "ids": 1}
        node("rel:Relationship", slide["rels"], Id="layout", Type=NS["r"] + "/slideLayout", Target="../slideLayouts/slideLayout6.xml")
        self.slides.append(slide)
        self.text(slide, lines(heading, size=28)[:2], 60, 36, 1160, 106, size=28, bold=True)
        self.text(slide, [f"PracticeFlow  ·  {len(self.slides)}"], 60, 667, 1160, 28, size=12, color="667A8A")
        return slide

    def transform(self, parent, x, y, width, height, tag="a:xfrm"):
        transform = node(tag, parent)
        node("a:off", transform, x=round(x * EMU), y=round(y * EMU))
        node("a:ext", transform, cx=round(width * EMU), cy=round(height * EMU))

    def text(self, slide, value, x, y, width, height, size=20, bold=False, color="18334A"):
        slide["ids"] += 1
        shape = node("p:sp", slide["tree"])
        nv = node("p:nvSpPr", shape)
        node("p:cNvPr", nv, id=slide["ids"], name=f"Text {slide['ids']}")
        node("p:cNvSpPr", nv, txBox=1)
        node("p:nvPr", nv)
        props = node("p:spPr", shape)
        self.transform(props, x, y, width, height)
        node("a:avLst", node("a:prstGeom", props, prst="rect"))
        node("a:noFill", props)
        node("a:noFill", node("a:ln", props))
        body = node("p:txBody", shape)
        body_props = node("a:bodyPr", body, wrap="square", lIns=0, rIns=0, tIns=0, bIns=0)
        node("a:noAutofit", body_props)
        node("a:lstStyle", body)
        paragraphs(body, value, size, color, bold, self.lang)

    def text_pages(self, heading, text):
        wrapped = lines(text)
        for offset in range(0, len(wrapped), 11):
            slide = self.slide(heading)
            self.text(slide, wrapped[offset:offset + 11], 60, 160, 1160, 480)

    def frame(self, slide, x, y, width, height):
        slide["ids"] += 1
        frame = node("p:graphicFrame", slide["tree"])
        nv = node("p:nvGraphicFramePr", frame)
        node("p:cNvPr", nv, id=slide["ids"], name=f"Data {slide['ids']}")
        node("p:cNvGraphicFramePr", nv)
        node("p:nvPr", nv)
        self.transform(frame, x, y, width, height, "p:xfrm")
        return node("a:graphic", frame)

    def table(self, heading, rows, widths):
        slide = self.slide(heading)
        wrapped = [[lines(str(value), width - 28, size=16, break_words=False)
                    for width, value in zip(widths, values, strict=True)] for values in rows]
        heights = [max(68, 16 + max(map(len, values)) * 32) for values in wrapped]
        data = node("a:graphicData", self.frame(slide, 60, 170, 1160, sum(heights)), uri=NS["a"] + "/table")
        table = node("a:tbl", data)
        node("a:tblPr", table, firstRow=1, bandRow=1)
        grid = node("a:tblGrid", table)
        for width in widths:
            node("a:gridCol", grid, w=round(width * EMU))
        for row_number, (values, height) in enumerate(zip(wrapped, heights, strict=True)):
            row = node("a:tr", table, h=height * EMU)
            for value in values:
                cell = node("a:tc", row)
                body = node("a:txBody", cell)
                node("a:bodyPr", body)
                node("a:lstStyle", body)
                paragraphs(body, value, size=16,
                           color="FFFFFF" if row_number == 0 else "18334A", bold=row_number == 0, lang=self.lang)
                props = node("a:tcPr", cell, marL=14 * EMU, marR=14 * EMU, marT=8 * EMU, marB=8 * EMU)
                node("a:srgbClr", node("a:solidFill", props), val="205B79" if row_number == 0 else ("EDF4F7" if row_number % 2 else "FFFFFF"))

    def chart(self, heading, categories, values, series_name):
        slide = self.slide(heading)
        self.text(slide, [series_name], 60, 122, 1160, 32, size=16)
        chart_id = len(self.charts) + 1
        self.charts.append((categories, values, series_name))
        data = node("a:graphicData", self.frame(slide, 60, 158, 1160, 480), uri=NS["c"])
        node("c:chart", data, **{f"{{{NS['r']}}}id": "chart"})
        node("rel:Relationship", slide["rels"], Id="chart", Type=NS["r"] + "/chart", Target=f"../charts/chart{chart_id}.xml")

    def export(self):
        template = Path(__file__).parents[1] / "documents/templates/group_review_base.pptx"
        with zipfile.ZipFile(template) as source:
            files = {name: source.read(name) for name in source.namelist()
                     if not name.startswith(("ppt/slides/", "ppt/notesSlides/"))}
        types = ET.fromstring(files["[Content_Types].xml"])
        for entry in list(types):
            if entry.get("PartName", "").startswith(("/ppt/slides/", "/ppt/notesSlides/")):
                types.remove(entry)
        def override(part, content_type):
            node("ct:Override", types, PartName="/" + part, ContentType=content_type)
        presentation = ET.fromstring(files["ppt/presentation.xml"])
        slide_list = presentation.find("p:sldIdLst", NS)
        slide_list.clear()
        rels = ET.fromstring(files["ppt/_rels/presentation.xml.rels"])
        for rel in list(rels):
            if rel.get("Type") == NS["r"] + "/slide":
                rels.remove(rel)
        for number, slide in enumerate(self.slides, 1):
            slide_id = f"slide{number}"
            node("p:sldId", slide_list, id=255 + number, **{f"{{{NS['r']}}}id": slide_id})
            node("rel:Relationship", rels, Id=slide_id, Type=NS["r"] + "/slide", Target=f"slides/slide{number}.xml")
            part = f"ppt/slides/slide{number}.xml"
            files[part] = xml(slide["root"])
            files[f"ppt/slides/_rels/slide{number}.xml.rels"] = xml(slide["rels"])
            override(part, "application/vnd.openxmlformats-officedocument.presentationml.slide+xml")
        if self.charts:
            node("ct:Default", types, Extension="xlsx", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        for number, (categories, values, name) in enumerate(self.charts, 1):
            files[f"ppt/charts/chart{number}.xml"] = xml(chart_xml(categories, values, name, self.lang))
            chart_rels = node("rel:Relationships")
            node("rel:Relationship", chart_rels, Id="workbook", Type=NS["r"] + "/package", Target=f"../embeddings/data{number}.xlsx")
            files[f"ppt/charts/_rels/chart{number}.xml.rels"] = xml(chart_rels)
            files[f"ppt/embeddings/data{number}.xlsx"] = workbook(categories, values, name)
            override(f"ppt/charts/chart{number}.xml", "application/vnd.openxmlformats-officedocument.drawingml.chart+xml")
        files["ppt/presentation.xml"] = xml(presentation)
        files["ppt/_rels/presentation.xml.rels"] = xml(rels)
        files["[Content_Types].xml"] = xml(types)
        # Remove authoring-tool metadata; only intentionally selected report
        # content is present in the downloadable package.
        files["docProps/core.xml"] = b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"/>'
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in files.items():
                archive.writestr(name, payload)
        return output.getvalue()


def chart_xml(categories, values, name, lang):
    root = node("c:chartSpace")
    node("c:lang", root, val=lang)
    chart = node("c:chart", root)
    node("c:autoTitleDeleted", chart, val=1)
    plot = node("c:plotArea", chart)
    node("c:layout", plot)
    bar = node("c:barChart", plot)
    node("c:barDir", bar, val="bar")
    node("c:grouping", bar, val="clustered")
    series = node("c:ser", bar)
    node("c:idx", series, val=0)
    node("c:order", series, val=0)
    tx = node("c:tx", series)
    node("c:v", tx).text = name
    node("a:srgbClr", node("a:solidFill", node("c:spPr", series)), val="28799A")
    for tag, data, column, cache_tag in (("cat", categories, "A", "strCache"), ("val", values, "B", "numCache")):
        ref = node("c:strRef" if tag == "cat" else "c:numRef", node(f"c:{tag}", series))
        node("c:f", ref).text = f"Sheet1!${column}$2:${column}${len(data) + 1}"
        cache = node(f"c:{cache_tag}", ref)
        if tag == "val":
            node("c:formatCode", cache).text = "0"
        node("c:ptCount", cache, val=len(data))
        for index, value in enumerate(data):
            node("c:v", node("c:pt", cache, idx=index)).text = str(value)
    labels = node("c:dLbls", bar)
    chart_text(labels)
    node("c:dLblPos", labels, val="outEnd")
    node("c:showVal", labels, val=1)
    node("c:gapWidth", bar, val=90)
    for axis_id in (1, 2):
        node("c:axId", bar, val=axis_id)
    for kind, axis_id, cross_id, position in (("catAx", 1, 2, "l"), ("valAx", 2, 1, "b")):
        axis = node(f"c:{kind}", plot)
        node("c:axId", axis, val=axis_id)
        scale = node("c:scaling", axis)
        node("c:orientation", scale, val="minMax")
        if kind == "valAx":
            node("c:min", scale, val=0)
            node("c:max", scale, val=max(1, math.ceil(max(values, default=0) * 1.2)))
        node("c:delete", axis, val=0)
        node("c:axPos", axis, val=position)
        if kind == "valAx":
            node("c:numFmt", axis, formatCode="0", sourceLinked=0)
        node("c:tickLblPos", axis, val="nextTo")
        chart_text(axis)
        node("c:crossAx", axis, val=cross_id)
        node("c:crosses", axis, val="autoZero")
        if kind == "valAx":
            node("c:crossBetween", axis, val="between")
            node("c:majorUnit", axis, val=max(1, math.ceil(max(values, default=0) / 5)))
    node("c:plotVisOnly", chart, val=1)
    chart_text(root)
    node("c:autoUpdate", node("c:externalData", root, **{f"{{{NS['r']}}}id": "workbook"}), val=0)
    return root


def chart_text(parent):
    body = node("c:txPr", parent)
    node("a:bodyPr", body)
    node("a:lstStyle", body)
    paragraph = node("a:p", body)
    default = node("a:defRPr", node("a:pPr", paragraph), sz=1600)
    node("a:srgbClr", node("a:solidFill", default), val="18334A")
    for face in ("latin", "ea", "cs"):
        node(f"a:{face}", default, typeface=FONT)
    node("a:endParaRPr", paragraph, sz=1600)


def workbook(categories, values, name):
    types = node("ct:Types")
    node("ct:Default", types, Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    node("ct:Default", types, Extension="xml", ContentType="application/xml")
    for part, suffix in (("workbook.xml", "sheet.main+xml"), ("worksheets/sheet1.xml", "worksheet+xml")):
        node("ct:Override", types, PartName="/xl/" + part, ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml." + suffix)
    root_rels = node("rel:Relationships")
    node("rel:Relationship", root_rels, Id="office", Type=NS["r"] + "/officeDocument", Target="xl/workbook.xml")
    book = node("s:workbook")
    node("s:sheet", node("s:sheets", book), name="Sheet1", sheetId=1, **{f"{{{NS['r']}}}id": "sheet"})
    rels = node("rel:Relationships")
    node("rel:Relationship", rels, Id="sheet", Type=NS["r"] + "/worksheet", Target="worksheets/sheet1.xml")
    sheet = node("s:worksheet")
    data = node("s:sheetData", sheet)
    for row_number, (label, value) in enumerate([("", name), *zip(categories, values, strict=True)], 1):
        row = node("s:row", data, r=row_number)
        for column, text in (("A", label), ("B", value)):
            cell = node("s:c", row, r=f"{column}{row_number}", t="n" if isinstance(text, int) else "inlineStr")
            if isinstance(text, int):
                node("s:v", cell).text = str(text)
            else:
                node("s:t", node("s:is", cell)).text = text
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for part, root in (("[Content_Types].xml", types), ("_rels/.rels", root_rels), ("xl/workbook.xml", book),
                           ("xl/_rels/workbook.xml.rels", rels), ("xl/worksheets/sheet1.xml", sheet)):
            archive.writestr(part, xml(root))
    return output.getvalue()


def format_metric(value, text):
    def scalar(item):
        if item is None:
            return text["unknown"]
        if isinstance(item, bool):
            return text["yes"] if item else text["no"]
        return text["values"].get(str(item), str(item))
    unit = text["units"].get(value.get("unit"), value.get("unit") or "")
    if "allowed" in value:
        return ", ".join(scalar(item) for item in value["allowed"]) or text["unknown"]
    if "width_mm" in value or "height_mm" in value:
        return f"{scalar(value.get('width_mm'))} × {scalar(value.get('height_mm'))} {text['units']['mm']}"
    if "min" in value or "max" in value:
        return f"{scalar(value.get('min'))}–{scalar(value.get('max'))} {unit}".strip()
    if "value" in value:
        return f"{scalar(value['value'])} {unit}".strip()
    return text["unknown"]


def render_group_report(snapshot, content, locale, *, timeout_seconds=60):
    text = REPORT_TEXT[locale]
    deck = Deck(timeout_seconds, locale)
    names = dict(zip(RULE_TYPES, text["rule_types"], strict=True))
    # Keep the group and date on the first slide even when a long title needs
    # continuation slides. The title remains complete and editable.
    deck.text_pages(text["cover"], snapshot["group_name"] + "\n" + text["date"] + ": " +
                    snapshot["captured_at"][:10] + "\n\n" + content["title"])
    summary = snapshot["summary"]
    deck.table(text["scope"], [[text["scope"], ""], *[[text[label], summary[key]] for label, key in
               (("total", "total_works"), ("reviewed", "reviewed_works"), ("pending", "pending_works"), ("included", "included_works"))]], [850, 310])
    warnings = [text["limits"]]
    if summary["reviewed_works"] < summary["total_works"]:
        warnings.insert(0, text["partial"].format(reviewed=summary["reviewed_works"], total=summary["total_works"], included=summary["included_works"]))
    if summary["included_works"] < summary["reviewed_works"]:
        warnings.append(text["missing"].format(included=summary["included_works"], reviewed=summary["reviewed_works"]))
    if summary["truncated_works"]:
        warnings.append(text["truncated"].format(count=summary["truncated_works"]))
    if snapshot.get("skipped_works"):
        warnings.append(text["skipped"].format(count=snapshot["skipped_works"]))
    deck.text_pages(text["warnings"], "\n\n".join(warnings))
    deck.text_pages(text["introduction"], content["introduction"] or text["empty_text"])
    rows = [row for row in summary["violations"] if row["rule_type"] in content["selected_rule_types"]]
    if not rows:
        message = text["no_findings"] if not summary["violations"] else text["no_selection"]
        deck.text_pages(text["problems"], message)
        deck.text_pages(text["statistics"], message)
    for offset in range(0, len(rows), 5):
        subset = rows[offset:offset + 5]
        deck.chart(text["problems"], ["\n".join(lines(names[row["rule_type"]], 650, 18)) for row in subset],
                   [row["works_count"] for row in subset], text["works"])
        deck.table(text["statistics"], [[text["type"], text["violations"], text["works"]],
                   *[[names[row["rule_type"]], row["violations_count"], row["works_count"]] for row in subset]], [560, 260, 340])
    if not content["examples"]:
        deck.text_pages(text["examples"], text["no_examples"])
    for number, example in enumerate(content["examples"], 1):
        location = ", ".join(f"{text[key]} {value}" for key, value in example["location"].items()) or text["unknown"]
        body = "\n\n".join([names[example["rule_type"]], text["location"] + ": " + location,
                             text["actual"] + ": " + format_metric(example["actual"], text),
                             text["expected"] + ": " + format_metric(example["expected"], text)])
        deck.text_pages(text["example"].format(number=number), body)
    for remark in content["remarks"]:
        deck.text_pages(text["remarks"], remark)
    deck.text_pages(text["conclusions"], content["conclusions"] or text["empty_text"])
    return deck.export()
