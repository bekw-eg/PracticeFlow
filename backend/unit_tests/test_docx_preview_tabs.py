import io
import re
import zipfile

from app.services.document_analyzer import W
from app.services.docx_html_preview import render_docx_html

TOC_STYLES = f'''<w:styles xmlns:w="{W}">
  <w:style w:type="paragraph" w:styleId="TOC2"><w:name w:val="toc 2"/>
    <w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9345"/></w:tabs>
    <w:ind w:left="567" w:hanging="567"/></w:pPr></w:style>
</w:styles>'''


def package(body: str, styles: str = TOC_STYLES, settings: str | None = None) -> io.BytesIO:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        cover = '<w:p><w:r><w:t>Title</w:t><w:br w:type="page"/></w:r></w:p>'
        archive.writestr("word/document.xml",
                         f'<w:document xmlns:w="{W}"><w:body>{cover}{body}<w:sectPr/></w:body></w:document>')
        archive.writestr("word/styles.xml", styles)
        if settings is not None:
            archive.writestr("word/settings.xml", f'<w:settings xmlns:w="{W}">{settings}</w:settings>')
    result.seek(0)
    return result


def paragraph(html: str, index: int) -> str:
    match = re.search(rf'<p data-paragraph-index="{index}"[^>]*>.*?</p>', html)
    assert match, html
    return match.group(0)


def test_toc_line_keeps_style_tab_stops_leader_and_hanging_indent_stop():
    html = render_docx_html(package(
        '<w:p><w:pPr><w:pStyle w:val="TOC2"/></w:pPr>'
        '<w:r><w:t>1.1</w:t></w:r><w:r><w:tab/><w:t>Веб-портфолио ұғымы</w:t></w:r>'
        '<w:r><w:tab/><w:t>5</w:t></w:r></w:p>'
    )).html
    line = paragraph(html, 2)
    assert "&emsp;" not in line
    assert line.count('<span class="pf-tab">\t</span>') == 2
    # Implicit hanging-indent stop at 10 mm, then the style's right dot-leader stop at 164.84 mm.
    assert 'data-tab-stops="10 left none;164.84 right dot"' in line
    assert 'data-default-tab="12.7"' in html


def test_direct_tabs_extend_and_clear_inherited_stops_and_read_default_tab():
    html = render_docx_html(package(
        '<w:p><w:pPr><w:pStyle w:val="TOC2"/><w:tabs><w:tab w:val="clear" w:pos="9345"/>'
        '<w:tab w:val="center" w:pos="4677"/><w:tab w:val="end" w:leader="hyphen" w:pos="9000"/>'
        '<w:tab w:val="bar" w:pos="100"/></w:tabs><w:ind w:left="0" w:firstLine="0"/></w:pPr>'
        '<w:r><w:t>A</w:t><w:tab/><w:t>B</w:t></w:r></w:p>',
        settings='<w:defaultTabStop w:val="708"/>',
    )).html
    line = paragraph(html, 2)
    assert 'data-tab-stops="82.5 center none;158.75 right hyphen"' in line
    assert 'data-default-tab="12.49"' in html


def test_paragraph_without_tabs_has_no_stop_metadata_and_ptab_is_marked():
    html = render_docx_html(package(
        '<w:p><w:pPr><w:pStyle w:val="TOC2"/></w:pPr><w:r><w:t>No tabs</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Left</w:t><w:ptab w:relativeTo="margin" w:alignment="right" w:leader="dot"/>'
        '<w:t>9</w:t></w:r></w:p>'
    )).html
    assert "data-tab-stops" not in paragraph(html, 2)
    assert '<span class="pf-tab" data-ptab="right" data-ptab-leader="dot">\t</span>' in paragraph(html, 3)


def test_untrusted_tab_attributes_are_not_copied_into_html():
    html = render_docx_html(package(
        '<w:p><w:pPr><w:tabs><w:tab w:val="right&quot; onclick=&quot;x" w:pos="9000"/>'
        '<w:tab w:val="left" w:leader="&lt;script&gt;" w:pos="abc"/></w:tabs></w:pPr>'
        '<w:r><w:t>A</w:t><w:ptab w:alignment="&quot;x" w:leader="evil"/><w:tab/></w:r></w:p>'
    )).html
    line = paragraph(html, 2)
    assert "onclick" not in line and "script" not in line and "evil" not in line
    assert '<span class="pf-tab">\t</span><span class="pf-tab">\t</span>' in line


def cells(html: str) -> list[str]:
    return re.findall(r'<td colspan="\d+" rowspan="\d+" style="([^"]*)">', html)


TOC_TABLE = ('<w:tbl><w:tblPr>{props}</w:tblPr><w:tblGrid><w:gridCol w:w="812"/><w:gridCol w:w="8363"/>'
             '<w:gridCol w:w="714"/></w:tblGrid>'
             '<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>КІРІСПЕ</w:t></w:r></w:p></w:tc>'
             '<w:tc><w:p><w:r><w:t>3</w:t></w:r></w:p></w:tc></w:tr>'
             '<w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Тарау</w:t></w:r></w:p></w:tc>'
             '<w:tc>{cell}<w:p><w:r><w:t>5</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')


def test_table_of_contents_table_without_borders_is_drawn_without_borders():
    html = render_docx_html(package(TOC_TABLE.format(props="", cell=""))).html
    assert cells(html) == ["border-top:none;border-bottom:none;border-left:none;border-right:none"] * 5


def test_table_style_and_direct_borders_map_to_outer_and_inside_edges():
    styles = TOC_STYLES.replace("</w:styles>", '''<w:style w:type="table" w:styleId="TableGrid">
      <w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="auto"/><w:left w:val="single" w:sz="4"/>
      <w:bottom w:val="single" w:sz="4"/><w:right w:val="single" w:sz="4"/>
      <w:insideH w:val="single" w:sz="4"/><w:insideV w:val="single" w:sz="4"/></w:tblBorders></w:tblPr>
    </w:style></w:styles>''')
    props = ('<w:tblStyle w:val="TableGrid"/><w:tblBorders><w:insideV w:val="nil"/>'
             '<w:bottom w:val="double" w:sz="4" w:color="FF0000"/></w:tblBorders>')
    cell = ('<w:tcPr><w:tcBorders><w:top w:val="dotted" w:sz="16" w:color="00FF00"/></w:tcBorders></w:tcPr>')
    first, second, third, fourth, fifth = cells(render_docx_html(package(TOC_TABLE.format(props=props, cell=cell),
                                                                         styles=styles)).html)
    solid = "0.5pt solid #000000"
    assert first == f"border-top:{solid};border-bottom:{solid};border-left:{solid};border-right:none"
    assert second == f"border-top:{solid};border-bottom:{solid};border-left:none;border-right:{solid}"
    assert fourth == f"border-top:{solid};border-bottom:1.5pt double #FF0000;border-left:none;border-right:none"
    assert fifth == ("border-top:2.0pt dotted #00FF00;border-bottom:1.5pt double #FF0000;"
                     f"border-left:none;border-right:{solid}")
    assert third.startswith(f"border-top:{solid};border-bottom:1.5pt double #FF0000;border-left:{solid}")
