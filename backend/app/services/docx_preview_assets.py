"""Bounded embedded raster images and Word list labels for the private preview."""
import base64
import io
import posixpath
import re
from urllib.parse import unquote

from PIL import Image, UnidentifiedImageError

from app.services.document_analyzer import NS, W, _attr, _number, _xml

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V = "urn:schemas-microsoft-com:vml"


def embedded_images(package, document, scope):
    """Never fetch external relationships or embed original SVG/HTML payloads."""
    relationships = {}
    names = set(package.namelist())
    rel_part = "word/_rels/document.xml.rels"
    if rel_part in names:
        for rel in _xml(package.read(rel_part)):
            if rel.get("TargetMode", "Internal") != "Internal" or not rel.get("Type", "").endswith("/image"):
                continue
            target = unquote(rel.get("Target", ""))
            if not target or ":" in target or "\\" in target or "\x00" in target:
                continue
            path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "word/" + target)
            if path.startswith("word/media/") and path in names:
                relationships[rel.get("Id")] = path
    cache, output = {}, {}
    budget = 12 * 1024 * 1024
    html_budget = 16 * 1024 * 1024
    for drawing in document.iter(f"{{{W}}}drawing", f"{{{W}}}pict"):
        excluded = ' data-check-excluded="true"' if drawing not in scope.images else ""
        fallback = f'<span class="pf-docx-image-placeholder" data-check-image="true" data-preview-label="imageUnavailable"{excluded}>▧</span>'
        output[drawing] = fallback
        blip = drawing.find(".//a:blip", NS)
        image_data = drawing.find(f".//{{{V}}}imagedata")
        relationship = blip.get(f"{{{R}}}embed") if blip is not None else (
            image_data.get(f"{{{R}}}id") if image_data is not None else None)
        path = relationships.get(relationship)
        if not path:
            continue
        if path not in cache:
            cache[path] = None
            if package.getinfo(path).file_size > 8 * 1024 * 1024 or budget <= 0:
                continue
            try:
                with Image.open(io.BytesIO(package.read(path))) as image:
                    if image.format not in {"PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP"}:
                        continue
                    if image.width * image.height > 16_000_000:
                        continue
                    image.seek(0)
                    image.thumbnail((2048, 2048))
                    converted = image.convert("RGBA")
                    encoded = io.BytesIO()
                    converted.save(encoded, format="PNG")
                    data = encoded.getvalue()
                    if len(data) > budget:
                        continue
                    budget -= len(data)
                    cache[path] = (base64.b64encode(data).decode("ascii"), converted.width, converted.height)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                continue
        if cache[path] is None:
            continue
        payload, width, height = cache[path]
        if len(payload) > html_budget:
            continue
        html_budget -= len(payload)
        extent = drawing.find(f".//{{{WP}}}extent")
        # Explicit dimensions keep pagination stable before image decoding.
        width_px = _number(extent.get("cx") if extent is not None else None, width * 9525) / 9525
        height_px = _number(extent.get("cy") if extent is not None else None, height * 9525) / 9525
        width_px, height_px = max(1, min(2400, width_px)), max(1, min(2400, height_px))
        output[drawing] = (
            f'<img class="pf-docx-image" data-check-image="true"{excluded} '
            f'data-preview-label="embeddedImage" alt="" width="{width_px:.2f}" height="{height_px:.2f}" '
            f'style="width:{width_px:.2f}px;height:auto;max-width:100%" src="data:image/png;base64,{payload}">'
        )
    return output


def _label_number(number, kind):
    if kind in {"upperLetter", "lowerLetter"} and 0 < number <= 18278:
        value = ""
        while number:
            number, rest = divmod(number - 1, 26)
            value = chr(65 + rest) + value
        return value.lower() if kind == "lowerLetter" else value
    if kind in {"upperRoman", "lowerRoman"} and 0 < number < 4000:
        value = ""
        for amount, token in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                              (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
            count, number = divmod(number, amount)
            value += token * count
        return value.lower() if kind == "lowerRoman" else value
    return str(number).zfill(2) if kind == "decimalZero" else str(number)


def numbering_labels(package, document, styles):
    if "word/numbering.xml" not in package.namelist():
        return {}
    root = _xml(package.read("word/numbering.xml"))
    abstracts = {_attr(node, "abstractNumId"): node for node in root.findall("w:abstractNum", NS)}
    numbers = {_attr(node, "numId"): node for node in root.findall("w:num", NS)}
    counters, output = {}, {}
    for paragraph in document.findall(".//w:p", NS):
        properties = styles.paragraph_properties(paragraph)
        num_id = next((_attr(node.find("w:numPr/w:numId", NS), "val") for node in properties
                       if _attr(node.find("w:numPr/w:numId", NS), "val") is not None), None)
        if not num_id or num_id == "0" or num_id not in numbers:
            continue
        number = numbers[num_id]
        abstract = abstracts.get(_attr(number.find("w:abstractNumId", NS), "val"))
        if abstract is None:
            continue
        raw_level = next((_attr(node.find("w:numPr/w:ilvl", NS), "val") for node in properties
                          if _attr(node.find("w:numPr/w:ilvl", NS), "val") is not None), "0")
        level = max(0, min(8, int(_number(raw_level))))
        levels = {int(_number(_attr(node, "ilvl"))): node for node in abstract.findall("w:lvl", NS)}
        starts = {}
        for override in number.findall("w:lvlOverride", NS):
            index = int(_number(_attr(override, "ilvl")))
            if (node := override.find("w:lvl", NS)) is not None:
                levels[index] = node
            if (value := _attr(override.find("w:startOverride", NS), "val")) is not None:
                starts[index] = int(_number(value, 1))
        if level not in levels:
            continue
        def start(index):
            return starts.get(index, int(_number(_attr(levels[index].find("w:start", NS), "val"), 1)))
        counts = counters.setdefault(num_id, {})
        counts[level] = counts.get(level, start(level) - 1) + 1
        for deeper in list(counts):
            if deeper > level:
                restart = _attr(levels[deeper].find("w:lvlRestart", NS), "val") if deeper in levels else None
                if restart != "0" and (restart is None or level == int(_number(restart)) - 1):
                    del counts[deeper]
        node = levels[level]
        kind = _attr(node.find("w:numFmt", NS), "val") or "decimal"
        pattern = _attr(node.find("w:lvlText", NS), "val") or "%1."
        if kind == "none":
            label = ""
        elif kind == "bullet":
            label = pattern if pattern in {"•", "◦", "▪", "–", "-"} else "•"
        else:
            def replace(match):
                index = int(match[1]) - 1
                if index not in levels:
                    return ""
                fmt = _attr(levels[index].find("w:numFmt", NS), "val") or "decimal"
                return _label_number(counts.get(index, start(index)), fmt)
            label = re.sub(r"%([1-9])", replace, pattern[:100])
        output[paragraph] = label
    return output
