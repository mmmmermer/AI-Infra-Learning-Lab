import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZIP_STORED, ZipFile

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from rag_reference.ingestion import TrustedCollectionPolicy
from rag_reference.lifecycle import ArtifactKind, LifecycleIndex, LifecycleStatus, SourceRecord
from rag_reference.parsing import (
    AdapterExtraction,
    ParseLimits,
    ParseStatus,
    _pypdf_page_has_images,
    parse_source,
    pypdf_extraction_adapter,
)
from rag_reference.security import Principal
from rag_reference.service import RagQueryRequest, RetrievalCache


FIXTURES = Path(__file__).parent / "fixtures"
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SHEET_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CONTENT_TYPES_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
PACKAGE_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
DOCUMENT_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def principal() -> Principal:
    return Principal(
        tenant_id="tenant-demo",
        user_id="multiformat-private-user",
        scopes=frozenset({"rag:ingest", "rag:delete", "rag:query"}),
        effective_permission_groups=frozenset({"public"}),
        acl_version="acl-v1",
    )


def policy() -> TrustedCollectionPolicy:
    return TrustedCollectionPolicy(
        tenant_id="tenant-demo",
        collection_id="demo",
        permission_group="public",
        source_id="multiformat-fixture",
        source_version="server-policy-v1",
    )


def _fixture() -> dict:
    return json.loads(
        (FIXTURES / "multiformat_ingestion_cases.json").read_text(
            encoding="utf-8"
        )
    )


def _docx_bytes(
    case: dict, *, document_xml: bytes | str | None = None
) -> bytes:
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(value)}</w:t></w:r></w:p>"
        for value in case["paragraphs"]
    )
    table_rows = "".join(
        "<w:tr>"
        + "".join(
            f"<w:tc><w:p><w:r><w:t>{escape(cell)}</w:t></w:r></w:p></w:tc>"
            for cell in row
        )
        + "</w:tr>"
        for row in case["table"]
    )
    document = (
        f'<w:document xmlns:w="{WORD_NAMESPACE}"><w:body>'
        f"{paragraphs}<w:tbl>{table_rows}</w:tbl>"
        "</w:body></w:document>"
    )
    if document_xml is not None:
        document = document_xml
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Types xmlns="{CONTENT_TYPES_NAMESPACE}">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    root_relationships = (
        f'<Relationships xmlns="{PACKAGE_RELATIONSHIPS_NAMESPACE}">'
        '<Relationship Id="rId1" '
        f'Type="{DOCUMENT_RELATIONSHIPS_NAMESPACE}/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _xlsx_bytes(
    case: dict,
    *,
    orphan_marker: str | None = None,
    first_shared_string_index: int | None = None,
    shared_strings_root_tag: str = "sst",
    worksheet_root_tag: str = "worksheet",
) -> bytes:
    values = [cell for row in case["rows"] for cell in row]
    shared_strings = (
        f'<{shared_strings_root_tag} xmlns="{SHEET_NAMESPACE}" count="{len(values)}" '
        f'uniqueCount="{len(values)}">'
        + "".join(f"<si><t>{escape(value)}</t></si>" for value in values)
        + f"</{shared_strings_root_tag}>"
    )
    index = 0
    rows: list[str] = []
    for row_number, row in enumerate(case["rows"], start=1):
        cells = []
        for column_number, _ in enumerate(row, start=1):
            column = chr(64 + column_number)
            serialized_index = (
                first_shared_string_index
                if index == 0 and first_shared_string_index is not None
                else index
            )
            cells.append(
                f'<c r="{column}{row_number}" t="s"><v>{serialized_index}</v></c>'
            )
            index += 1
        rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    worksheet = (
        f'<{worksheet_root_tag} xmlns="{SHEET_NAMESPACE}"><sheetData>'
        + "".join(rows)
        + f"</sheetData></{worksheet_root_tag}>"
    )
    workbook = (
        f'<workbook xmlns="{SHEET_NAMESPACE}" '
        f'xmlns:r="{DOCUMENT_RELATIONSHIPS_NAMESPACE}">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    root_relationships = (
        f'<Relationships xmlns="{PACKAGE_RELATIONSHIPS_NAMESPACE}">'
        '<Relationship Id="rId1" '
        f'Type="{DOCUMENT_RELATIONSHIPS_NAMESPACE}/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_relationships = (
        f'<Relationships xmlns="{PACKAGE_RELATIONSHIPS_NAMESPACE}">'
        '<Relationship Id="rId1" '
        f'Type="{DOCUMENT_RELATIONSHIPS_NAMESPACE}/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        f'Type="{DOCUMENT_RELATIONSHIPS_NAMESPACE}/sharedStrings" '
        'Target="sharedStrings.xml"/>'
        "</Relationships>"
    )
    orphan_override = (
        '<Override PartName="/xl/worksheets/orphan.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        if orphan_marker is not None
        else ""
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Types xmlns="{CONTENT_TYPES_NAMESPACE}">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        f"{orphan_override}"
        "</Types>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_STORED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        if orphan_marker is not None:
            orphan = (
                f'<worksheet xmlns="{SHEET_NAMESPACE}"><sheetData>'
                f'<row r="1"><c r="A1" t="inlineStr"><is><t>{escape(orphan_marker)}</t></is></c></row>'
                "</sheetData></worksheet>"
            )
            archive.writestr("xl/worksheets/orphan.xml", orphan)
    return buffer.getvalue()


def _pdf_bytes(
    marker: str,
    *,
    scan_only: bool = False,
    pages: int = 1,
    inline_scan_page_numbers: frozenset[int] = frozenset(),
    mixed_inline_image_page_numbers: frozenset[int] = frozenset(),
    nested_form_scan_page_numbers: frozenset[int] = frozenset(),
    scan_page_numbers: frozenset[int] = frozenset(),
    unused_image_page_numbers: frozenset[int] = frozenset(),
    unused_form_image_page_numbers: frozenset[int] = frozenset(),
) -> bytes:
    writer = PdfWriter()
    for page_number in range(1, pages + 1):
        page = writer.add_blank_page(width=612, height=792)
        if page_number in nested_form_scan_page_numbers:
            image = DecodedStreamObject()
            image.set_data(b"\x00")
            image.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Image"),
                    NameObject("/Width"): NumberObject(1),
                    NameObject("/Height"): NumberObject(1),
                    NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                    NameObject("/BitsPerComponent"): NumberObject(8),
                }
            )
            image_reference = writer._add_object(image)
            form = DecodedStreamObject()
            form.set_data(b"q /Im1 Do Q")
            form.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Form"),
                    NameObject("/BBox"): ArrayObject(
                        [NumberObject(0), NumberObject(0), NumberObject(1), NumberObject(1)]
                    ),
                    NameObject("/Resources"): DictionaryObject(
                        {
                            NameObject("/XObject"): DictionaryObject(
                                {NameObject("/Im1"): image_reference}
                            )
                        }
                    ),
                }
            )
            form_reference = writer._add_object(form)
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/XObject"): DictionaryObject(
                        {NameObject("/Fm1"): form_reference}
                    )
                }
            )
            commands = b"q /Fm1 Do Q"
        elif page_number in inline_scan_page_numbers:
            commands = b"q BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI Q"
        elif scan_only or page_number in scan_page_numbers:
            image = DecodedStreamObject()
            image.set_data(b"\x00")
            image.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Image"),
                    NameObject("/Width"): NumberObject(1),
                    NameObject("/Height"): NumberObject(1),
                    NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                    NameObject("/BitsPerComponent"): NumberObject(8),
                }
            )
            image_reference = writer._add_object(image)
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/XObject"): DictionaryObject(
                        {NameObject("/Im1"): image_reference}
                    )
                }
            )
            commands = b"q 1 0 0 1 72 720 cm /Im1 Do Q"
        elif marker:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            font_reference = writer._add_object(font)
            resources = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): font_reference}
                    )
                }
            )
            if page_number in unused_image_page_numbers:
                unused_image = DecodedStreamObject()
                unused_image.set_data(b"\x00")
                unused_image.update(
                    {
                        NameObject("/Type"): NameObject("/XObject"),
                        NameObject("/Subtype"): NameObject("/Image"),
                        NameObject("/Width"): NumberObject(1),
                        NameObject("/Height"): NumberObject(1),
                        NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                        NameObject("/BitsPerComponent"): NumberObject(8),
                    }
                )
                resources[NameObject("/XObject")] = DictionaryObject(
                    {NameObject("/UnusedImage"): writer._add_object(unused_image)}
                )
            elif page_number in unused_form_image_page_numbers:
                unused_image = DecodedStreamObject()
                unused_image.set_data(b"\x00")
                unused_image.update(
                    {
                        NameObject("/Type"): NameObject("/XObject"),
                        NameObject("/Subtype"): NameObject("/Image"),
                        NameObject("/Width"): NumberObject(1),
                        NameObject("/Height"): NumberObject(1),
                        NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                        NameObject("/BitsPerComponent"): NumberObject(8),
                    }
                )
                unused_form = DecodedStreamObject()
                unused_form.set_data(b"q /NestedImage Do Q")
                unused_form.update(
                    {
                        NameObject("/Type"): NameObject("/XObject"),
                        NameObject("/Subtype"): NameObject("/Form"),
                        NameObject("/BBox"): ArrayObject(
                            [
                                NumberObject(0),
                                NumberObject(0),
                                NumberObject(1),
                                NumberObject(1),
                            ]
                        ),
                        NameObject("/Resources"): DictionaryObject(
                            {
                                NameObject("/XObject"): DictionaryObject(
                                    {
                                        NameObject("/NestedImage"): writer._add_object(
                                            unused_image
                                        )
                                    }
                                )
                            }
                        ),
                    }
                )
                resources[NameObject("/XObject")] = DictionaryObject(
                    {NameObject("/UnusedForm"): writer._add_object(unused_form)}
                )
            page[NameObject("/Resources")] = resources
            escaped_marker = (
                marker.replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
            )
            commands = f"BT /F1 12 Tf 72 720 Td ({escaped_marker}) Tj ET".encode(
                "ascii"
            )
            if page_number in mixed_inline_image_page_numbers:
                commands += b" q BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI Q"
        else:
            continue
        stream = DecodedStreamObject()
        stream.set_data(commands)
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _xobject_resources(**entries) -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject(f"/{name}"): reference for name, reference in entries.items()}
            )
        }
    )


def _form_reference(
    writer: PdfWriter,
    data: bytes,
    resources: DictionaryObject | None = None,
):
    form = DecodedStreamObject()
    form.set_data(data)
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject(
                [NumberObject(0), NumberObject(0), NumberObject(1), NumberObject(1)]
            ),
        }
    )
    if resources is not None:
        form[NameObject("/Resources")] = resources
    return writer._add_object(form)


def _image_reference(writer: PdfWriter, *, indirect_subtype: bool = False):
    image = DecodedStreamObject()
    image.set_data(b"\x00")
    subtype = NameObject("/Image")
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): (
                writer._add_object(subtype) if indirect_subtype else subtype
            ),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    return writer._add_object(image)


def _pdf_shared_inherited_form_bytes() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)

    image = DecodedStreamObject()
    image.set_data(b"\x00")
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    image_reference = writer._add_object(image)
    dummy_reference = _form_reference(writer, b"")
    shared_reference = _form_reference(writer, b"/Im1 Do")
    outer_without_image = _form_reference(
        writer,
        b"/Shared Do",
        _xobject_resources(Shared=shared_reference, Im1=dummy_reference),
    )
    outer_with_image = _form_reference(
        writer,
        b"/Shared Do",
        _xobject_resources(Shared=shared_reference, Im1=image_reference),
    )
    page[NameObject("/Resources")] = _xobject_resources(
        F1=outer_without_image,
        F2=outer_with_image,
    )
    contents = DecodedStreamObject()
    contents.set_data(b"/F1 Do /F2 Do")
    page[NameObject("/Contents")] = writer._add_object(contents)

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _pdf_cyclic_form_bytes(*, include_image: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    loop = DecodedStreamObject()
    loop.set_data(b"/Self Do /Im1 Do" if include_image else b"/Self Do")
    loop.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject(
                [NumberObject(0), NumberObject(0), NumberObject(1), NumberObject(1)]
            ),
        }
    )
    loop_reference = writer._add_object(loop)
    loop_resources = {"Self": loop_reference}
    if include_image:
        image = DecodedStreamObject()
        image.set_data(b"\x00")
        image.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(1),
                NameObject("/Height"): NumberObject(1),
                NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                NameObject("/BitsPerComponent"): NumberObject(8),
            }
        )
        loop_resources["Im1"] = writer._add_object(image)
    loop[NameObject("/Resources")] = _xobject_resources(**loop_resources)
    page[NameObject("/Resources")] = _xobject_resources(Loop=loop_reference)
    contents = DecodedStreamObject()
    contents.set_data(b"/Loop Do")
    page[NameObject("/Contents")] = writer._add_object(contents)

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _pdf_indirect_subtype_bytes(subtype: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    if subtype == "Image":
        target_reference = _image_reference(writer, indirect_subtype=True)
    elif subtype == "Form":
        form = DecodedStreamObject()
        form.set_data(b"/Im1 Do")
        form.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): writer._add_object(NameObject("/Form")),
                NameObject("/BBox"): ArrayObject(
                    [NumberObject(0), NumberObject(0), NumberObject(1), NumberObject(1)]
                ),
                NameObject("/Resources"): _xobject_resources(
                    Im1=_image_reference(writer)
                ),
            }
        )
        target_reference = writer._add_object(form)
    else:
        raise AssertionError(f"unsupported indirect subtype fixture: {subtype}")

    page[NameObject("/Resources")] = _xobject_resources(Target=target_reference)
    contents = DecodedStreamObject()
    contents.set_data(b"/Target Do")
    page[NameObject("/Contents")] = writer._add_object(contents)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _case_content(case: dict) -> bytes:
    kind = case["payload_kind"]
    if kind == "utf8":
        return case["content"].encode("utf-8")
    if kind == "base64":
        return base64.b64decode(case["content"])
    if kind == "docx":
        return _docx_bytes(case)
    if kind == "xlsx":
        return _xlsx_bytes(case)
    if kind == "pdf_text":
        return _pdf_bytes(case["content"])
    if kind == "pdf_scan":
        return _pdf_bytes("", scan_only=True)
    if kind == "pdf_blank":
        return _pdf_bytes("")
    if kind == "png":
        return PNG_1X1
    if kind == "zip_prefix_only":
        return b"PK-not-a-valid-archive"
    raise AssertionError(f"unknown fixture payload kind: {kind}")


def _ocr_adapter(case: dict):
    def extract(content: bytes, limits: ParseLimits) -> AdapterExtraction:
        assert content
        assert limits.max_input_bytes > 0
        return AdapterExtraction(
            text=case["adapter_text"],
            block_count=1,
            page_count=1,
            warning_codes=(
                "layout_not_preserved",
                "PRIVATE-ADAPTER-WARNING-MUST-BE-REDACTED",
            ),
        )

    return extract


def _case_adapters(case: dict):
    if case.get("use_pypdf_provider"):
        return {case["media_type"]: pypdf_extraction_adapter}
    if case.get("use_adapter"):
        return {case["media_type"]: _ocr_adapter(case)}
    return {}


@pytest.mark.parametrize("case", _fixture()["cases"], ids=lambda case: case["case_id"])
def test_multiformat_fixture_has_stable_status_and_content_free_quality_report(case):
    fixture = _fixture()
    content = _case_content(case)
    adapters = _case_adapters(case)

    result = parse_source(
        content,
        case["media_type"],
        adapters=adapters,
        source_version=fixture["source_version"],
        source_locator=fixture["source_locator"],
        expected_markers=tuple(case["expected_markers"]),
    )

    assert result.report.status.value == case["expected_status"]
    assert result.report.detail_code == case["expected_detail"]
    assert result.report.raw_sha256 == sha256(content).hexdigest()
    assert result.report.source_version == fixture["source_version"]
    assert result.report.parser_version == "1.0"
    assert result.report.expected_marker_count == len(case["expected_markers"])
    assert result.report.block_count >= case.get("minimum_blocks", 0)
    assert result.report.table_count >= case.get("minimum_tables", 0)
    assert result.report.row_count >= case.get("minimum_rows", 0)
    assert result.report.table_cell_count >= case.get("minimum_cells", 0)
    assert result.report.page_count >= case.get("minimum_pages", 0)
    assert result.report.archive_entry_count >= case.get(
        "minimum_archive_entries", 0
    )

    if result.accepted:
        assert case["expected_contains"] in result.text
        if "expected_not_contains" in case:
            assert case["expected_not_contains"] not in result.text
        assert result.report.parsed_sha256 == sha256(
            result.text.encode("utf-8")
        ).hexdigest()
        assert result.report.marker_recall == 1.0
    else:
        assert result.text == ""
        assert result.report.parsed_sha256 is None

    audit_json = json.dumps(
        result.report.to_audit_dict(), ensure_ascii=True, sort_keys=True
    )
    assert fixture["source_locator"] not in audit_json
    assert "PRIVATE-ADAPTER-WARNING-MUST-BE-REDACTED" not in audit_json
    for marker in case["expected_markers"]:
        assert marker not in audit_json
    assert "text" not in result.report.to_audit_dict()


@pytest.mark.parametrize(
    "tag",
    ("iframe", "noembed", "noframes", "noscript", "script", "style", "template"),
)
def test_html_hidden_elements_suppress_content(tag: str):
    hidden_marker = f"HIDDEN-{tag.upper()}-1"
    payload = (
        f"<p>VISIBLE-BEFORE-{tag}</p>"
        f"<{tag}>{hidden_marker}</{tag}>"
        f"<p>VISIBLE-AFTER-{tag}</p>"
    )

    result = parse_source(payload.encode("utf-8"), "text/html")

    assert result.report.status == ParseStatus.PARSED
    assert f"VISIBLE-BEFORE-{tag}" in result.text
    assert f"VISIBLE-AFTER-{tag}" in result.text
    assert hidden_marker not in result.text


def test_html_nested_hidden_elements_suppress_all_nested_content():
    payload = (
        "<template>TEMPLATE-HIDDEN-1"
        "<script>SCRIPT-HIDDEN-1</script>"
        "<style>STYLE-HIDDEN-1</style>"
        "<noscript>NOSCRIPT-HIDDEN-1</noscript>"
        "</template><p>VISIBLE-NESTED-1</p>"
    )

    result = parse_source(payload.encode("utf-8"), "text/html")

    assert result.report.status == ParseStatus.PARSED
    assert "VISIBLE-NESTED-1" in result.text
    for marker in (
        "TEMPLATE-HIDDEN-1",
        "SCRIPT-HIDDEN-1",
        "STYLE-HIDDEN-1",
        "NOSCRIPT-HIDDEN-1",
    ):
        assert marker not in result.text


@pytest.mark.parametrize("tag", ("noscript", "script", "style", "template"))
def test_html_self_closing_non_void_hidden_elements_are_rejected(tag: str):
    result = parse_source(
        f"<{tag}/><p>VISIBLE-SELF-CLOSING-{tag}</p>".encode("utf-8"),
        "text/html",
    )

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "malformed_html_hidden_nesting"
    assert result.text == ""


def test_html_boolean_hidden_attribute_suppresses_the_complete_subtree():
    result = parse_source(
        (
            "<p>VISIBLE-BEFORE-HIDDEN-ATTR</p>"
            "<div hidden='false'>HIDDEN-ATTR-OUTER"
            "<div>HIDDEN-ATTR-INNER</div>HIDDEN-ATTR-AFTER-INNER</div>"
            "<p>VISIBLE-AFTER-HIDDEN-ATTR</p>"
        ).encode("utf-8"),
        "text/html",
    )

    assert result.report.status == ParseStatus.PARSED
    assert "VISIBLE-BEFORE-HIDDEN-ATTR" in result.text
    assert "VISIBLE-AFTER-HIDDEN-ATTR" in result.text
    for marker in (
        "HIDDEN-ATTR-OUTER",
        "HIDDEN-ATTR-INNER",
        "HIDDEN-ATTR-AFTER-INNER",
    ):
        assert marker not in result.text


@pytest.mark.parametrize("payload", ("<img hidden>", "<input hidden/>"))
def test_html_hidden_attribute_on_void_element_does_not_hide_following_text(
    payload: str,
):
    result = parse_source(
        f"{payload}<p>VISIBLE-AFTER-HIDDEN-VOID</p>".encode("utf-8"),
        "text/html",
    )

    assert result.report.status == ParseStatus.PARSED
    assert "VISIBLE-AFTER-HIDDEN-VOID" in result.text


def test_html_self_closing_non_void_hidden_attribute_is_rejected():
    result = parse_source(
        b"<div hidden/>HIDDEN-SELF-CLOSE-CANARY</div>",
        "text/html",
    )

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "malformed_html_hidden_nesting"
    assert result.text == ""


def test_html_stray_hidden_end_tag_does_not_change_visibility():
    result = parse_source(
        b"<p>VISIBLE-BEFORE-STRAY</p></style><p>VISIBLE-AFTER-STRAY</p>",
        "text/html",
    )

    assert result.report.status == ParseStatus.PARSED
    assert "VISIBLE-BEFORE-STRAY" in result.text
    assert "VISIBLE-AFTER-STRAY" in result.text


@pytest.mark.parametrize(
    "payload",
    (
        "<template><div></style>HIDDEN-MISMATCH</div></template>",
        "<template><noscript>HIDDEN-CROSS</template>TAIL</noscript>",
        "<template><style>HIDDEN-CDATA</template>TAIL</style>",
    ),
    ids=("mismatched-close", "crossed-close", "crossed-cdata-close"),
)
def test_html_mismatched_hidden_nesting_is_rejected(payload: str):
    result = parse_source(payload.encode("utf-8"), "text/html")

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "malformed_html_hidden_nesting"
    assert result.text == ""


@pytest.mark.parametrize("tag", ("noscript", "script", "style", "template"))
def test_html_unclosed_hidden_element_is_rejected(tag: str):
    result = parse_source(
        f"<p>VISIBLE-BEFORE-EOF</p><{tag}>HIDDEN-EOF-{tag}".encode("utf-8"),
        "text/html",
    )

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "malformed_html_hidden_nesting"
    assert result.text == ""


def test_html_unclosed_hidden_attribute_element_is_rejected():
    result = parse_source(
        b"<p>VISIBLE-BEFORE-EOF</p><div hidden>HIDDEN-ATTR-EOF",
        "text/html",
    )

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "malformed_html_hidden_nesting"
    assert result.text == ""


@pytest.mark.parametrize(
    "payload",
    (
        "<html><body hidden></body><p>HIDDEN-AFTER-BODY</p></html>",
        "<html hidden></html><p>HIDDEN-AFTER-HTML</p>",
    ),
    ids=("hidden-body", "hidden-html"),
)
def test_html_hidden_document_container_suppresses_trailing_markup(payload: str):
    result = parse_source(payload.encode("utf-8"), "text/html")

    assert result.report.status == ParseStatus.REJECTED_BLANK
    assert result.report.detail_code == "blank_after_parse"
    assert result.text == ""


@pytest.mark.parametrize(
    "payload",
    (
        "<p>VISIBLE-BEFORE-PLAINTEXT</p><plaintext>VISIBLE-AS-RAW-TEXT",
        (
            "<div hidden><plaintext>HIDDEN-PLAINTEXT</plaintext></div>"
            "<p>HIDDEN-PLAINTEXT-TAIL</p>"
        ),
    ),
    ids=("ordinary-plaintext", "plaintext-inside-hidden-subtree"),
)
def test_html_plaintext_tokenization_state_is_rejected(payload: str):
    result = parse_source(payload.encode("utf-8"), "text/html")

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "unsupported_html_tokenization_state"
    assert result.text == ""


def test_xhtml_namespace_hidden_elements_and_hidden_attribute_are_suppressed():
    payload = """<?xml version="1.0" encoding="UTF-8"?>
<x:html xmlns:x="http://www.w3.org/1999/xhtml">
  <x:body>
    <x:p>VISIBLE-XHTML-1</x:p>
    <x:script>HIDDEN-XHTML-SCRIPT</x:script>
    <x:div hidden="hidden">HIDDEN-XHTML-ATTR</x:div>
  </x:body>
</x:html>""".encode("utf-8")

    result = parse_source(payload, "application/xhtml+xml")

    assert result.report.status == ParseStatus.PARSED
    assert result.report.parser_id == "builtin-xhtml-xml-v1"
    assert "VISIBLE-XHTML-1" in result.text
    assert "HIDDEN-XHTML" not in result.text


def test_xhtml_self_closing_hidden_element_is_valid_xml():
    payload = (
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        "<body><script/><p>VISIBLE-AFTER-XHTML-SELF-CLOSE</p></body></html>"
    ).encode("utf-8")

    result = parse_source(payload, "application/xhtml+xml")

    assert result.report.status == ParseStatus.PARSED
    assert "VISIBLE-AFTER-XHTML-SELF-CLOSE" in result.text


@pytest.mark.parametrize(
    ("payload", "detail_code"),
    (
        (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>broken</body></html>',
            "malformed_xhtml",
        ),
        (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>&undefined;</body></html>',
            "malformed_xhtml",
        ),
        (
            '<!DOCTYPE html [<!ENTITY injected "HIDDEN-ENTITY">]>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>&injected;</body></html>',
            "unsafe_xhtml_declaration",
        ),
        (
            '<html xmlns="urn:not-xhtml"><body>WRONG-ROOT</body></html>',
            "invalid_xhtml_root",
        ),
    ),
    ids=(
        "mismatched-tag",
        "undefined-entity",
        "declared-entity",
        "wrong-root-qname",
    ),
)
def test_xhtml_malformed_or_unsafe_xml_is_rejected(payload: str, detail_code: str):
    result = parse_source(payload.encode("utf-8"), "application/xhtml+xml")

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == detail_code
    assert result.text == ""


@pytest.mark.parametrize(
    ("content_factory", "member_name", "marker", "media_type", "detail_code"),
    [
        (
            _docx_bytes,
            "word/document.xml",
            "DOCX-MARKER-55",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "invalid_docx_archive_member",
        ),
        (
            _xlsx_bytes,
            "xl/sharedStrings.xml",
            "XLSX-MARKER-66",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "invalid_xlsx_archive_member",
        ),
    ],
)
def test_office_crc_failures_map_to_stable_corrupt_status(
    content_factory, member_name, marker, media_type, detail_code
):
    case = next(
        item
        for item in _fixture()["cases"]
        if marker in json.dumps(item, ensure_ascii=True)
    )
    valid = content_factory(case)
    marker_bytes = marker.encode("ascii")
    marker_offset = valid.find(marker_bytes)
    assert marker_offset >= 0
    corrupted = bytearray(valid)
    corrupted[marker_offset] ^= 1
    corrupted_bytes = bytes(corrupted)

    with ZipFile(BytesIO(corrupted_bytes)) as archive:
        with pytest.raises(BadZipFile, match="CRC"):
            archive.read(member_name)

    result = parse_source(corrupted_bytes, media_type)
    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == detail_code


def test_xlsx_ignores_unreferenced_orphan_worksheet_content():
    case = next(
        item for item in _fixture()["cases"] if item["payload_kind"] == "xlsx"
    )
    orphan_marker = "ORPHAN-WORKSHEET-INJECTION-991"

    result = parse_source(
        _xlsx_bytes(case, orphan_marker=orphan_marker), case["media_type"]
    )

    assert result.accepted
    assert case["expected_contains"] in result.text
    assert orphan_marker not in result.text
    assert result.report.table_count == 1


def test_xlsx_negative_shared_string_index_is_rejected_as_corrupt():
    case = next(
        item for item in _fixture()["cases"] if item["payload_kind"] == "xlsx"
    )
    result = parse_source(
        _xlsx_bytes(case, first_shared_string_index=-1), case["media_type"]
    )

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "invalid_xlsx_shared_string_index"


def test_office_xml_rejects_utf16_doctype_and_entity_via_public_parser():
    case = next(
        item for item in _fixture()["cases"] if item["payload_kind"] == "docx"
    )
    unsafe_document = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE w:document [<!ENTITY injected "EXPANDED-ENTITY">]>'
        f'<w:document xmlns:w="{WORD_NAMESPACE}"><w:body>'
        "<w:p><w:r><w:t>&injected;</w:t></w:r></w:p>"
        "</w:body></w:document>"
    ).encode("utf-16")
    result = parse_source(
        _docx_bytes(case, document_xml=unsafe_document), case["media_type"]
    )

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == "unsafe_office_xml_declaration"


@pytest.mark.parametrize(
    ("content_factory", "expected_detail"),
    [
        (
            lambda case: _docx_bytes(
                case,
                document_xml=(
                    f'<w:notDocument xmlns:w="{WORD_NAMESPACE}">'
                    "<w:body><w:p><w:r><w:t>hidden</w:t></w:r></w:p></w:body>"
                    "</w:notDocument>"
                ),
            ),
            "invalid_docx_document_root",
        ),
        (
            lambda case: _xlsx_bytes(case, worksheet_root_tag="notWorksheet"),
            "invalid_xlsx_worksheet_root",
        ),
        (
            lambda case: _xlsx_bytes(case, shared_strings_root_tag="notSst"),
            "invalid_xlsx_shared_strings_root",
        ),
    ],
)
def test_office_payload_roots_must_match_the_declared_part(
    content_factory, expected_detail
):
    payload_kind = "docx" if "docx" in expected_detail else "xlsx"
    case = next(
        item
        for item in _fixture()["cases"]
        if item["payload_kind"] == payload_kind
    )
    result = parse_source(content_factory(case), case["media_type"])

    assert result.report.status == ParseStatus.REJECTED_CORRUPT
    assert result.report.detail_code == expected_detail


def test_mixed_pdf_reports_image_only_page_as_partial_extraction():
    result = parse_source(
        _pdf_bytes(
            "MIXED-PDF-TEXT-611",
            pages=2,
            scan_page_numbers=frozenset({2}),
        ),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
    )

    assert result.accepted
    assert "MIXED-PDF-TEXT-611" in result.text
    assert result.report.page_count == 2
    assert result.report.warning_codes == (
        "layout_not_preserved",
        "partial_page",
    )


def test_text_and_inline_image_on_same_pdf_page_reports_partial_extraction():
    result = parse_source(
        _pdf_bytes(
            "MIXED-SAME-PAGE-712",
            mixed_inline_image_page_numbers=frozenset({1}),
        ),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
    )

    assert result.accepted
    assert "MIXED-SAME-PAGE-712" in result.text
    assert result.report.warning_codes == (
        "layout_not_preserved",
        "partial_page",
    )


def test_inline_image_only_pdf_routes_to_ocr_instead_of_blank():
    result = parse_source(
        _pdf_bytes("", inline_scan_page_numbers=frozenset({1})),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
    )

    assert result.report.status == ParseStatus.REJECTED_OCR_REQUIRED
    assert result.report.detail_code == "adapter_requires_ocr"


def test_image_nested_in_pdf_form_xobject_routes_to_ocr():
    result = parse_source(
        _pdf_bytes("", nested_form_scan_page_numbers=frozenset({1})),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
    )

    assert result.report.status == ParseStatus.REJECTED_OCR_REQUIRED
    assert result.report.detail_code == "adapter_requires_ocr"


def test_shared_pdf_form_is_checked_per_inherited_resource_context():
    result = parse_source(
        _pdf_shared_inherited_form_bytes(),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
    )

    assert result.report.status == ParseStatus.REJECTED_OCR_REQUIRED
    assert result.report.detail_code == "adapter_requires_ocr"


@pytest.mark.parametrize("include_image", (False, True), ids=("no-image", "image"))
def test_cyclic_pdf_form_resource_graph_terminates_and_keeps_scanning(
    include_image: bool,
):
    reader = PdfReader(
        BytesIO(_pdf_cyclic_form_bytes(include_image=include_image)), strict=True
    )

    assert _pypdf_page_has_images(reader.pages[0]) is include_image


@pytest.mark.parametrize("subtype", ("Image", "Form"), ids=("image", "form"))
def test_pdf_indirect_xobject_subtype_is_resolved_before_image_routing(
    subtype: str,
):
    result = parse_source(
        _pdf_indirect_subtype_bytes(subtype),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
    )

    assert result.report.status == ParseStatus.REJECTED_OCR_REQUIRED
    assert result.report.detail_code == "adapter_requires_ocr"


@pytest.mark.parametrize(
    ("unused_images", "unused_forms"),
    [
        (frozenset({1}), frozenset()),
        (frozenset(), frozenset({1})),
    ],
)
def test_unused_pdf_xobjects_do_not_report_partial_extraction(
    unused_images: frozenset[int], unused_forms: frozenset[int]
):
    result = parse_source(
        _pdf_bytes(
            "VISIBLE-TEXT-WITH-UNUSED-RESOURCE",
            unused_image_page_numbers=unused_images,
            unused_form_image_page_numbers=unused_forms,
        ),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
    )

    assert result.accepted
    assert "partial_page" not in result.report.warning_codes


def test_pdf_page_limit_uses_provider_count_not_content_literal():
    result = parse_source(
        _pdf_bytes("VISIBLE /Type /Page LITERAL"),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
        limits=ParseLimits(max_pages=1),
    )

    assert result.accepted
    assert result.report.page_count == 1


def test_parser_resource_limits_and_adapter_failures_have_stable_codes():
    too_large = parse_source(
        b"123456",
        "text/plain",
        limits=ParseLimits(max_input_bytes=5),
    )
    assert too_large.report.status == ParseStatus.REJECTED_RESOURCE_LIMIT
    assert too_large.report.detail_code == "input_byte_limit_exceeded"

    too_many_cells = parse_source(
        b"a,b,c\n1,2,3",
        "text/csv",
        limits=ParseLimits(max_table_cells=5),
    )
    assert too_many_cells.report.detail_code == "table_cell_limit_exceeded"

    docx_case = next(
        case for case in _fixture()["cases"] if case["payload_kind"] == "docx"
    )
    archive_limited = parse_source(
        _docx_bytes(docx_case),
        docx_case["media_type"],
        limits=ParseLimits(max_archive_entries=1),
    )
    assert archive_limited.report.detail_code == "archive_entry_limit_exceeded"

    page_limited = parse_source(
        _pdf_bytes("PAGE-LIMIT", pages=2),
        "application/pdf",
        adapters={"application/pdf": pypdf_extraction_adapter},
        limits=ParseLimits(max_pages=1),
    )
    assert page_limited.report.detail_code == "page_limit_exceeded"

    private_exception = "PRIVATE-ADAPTER-EXCEPTION-991"

    def failing_adapter(content: bytes, limits: ParseLimits) -> AdapterExtraction:
        del content, limits
        raise RuntimeError(private_exception)

    failed = parse_source(
        PNG_1X1,
        "image/png",
        adapters={"image/png": failing_adapter},
    )
    assert failed.report.status == ParseStatus.REJECTED_ADAPTER_FAILURE
    assert failed.report.detail_code == "adapter_exception"
    assert private_exception not in json.dumps(failed.report.to_audit_dict())

    contract_failure = parse_source(
        PNG_1X1,
        "image/png",
        adapters={"image/png": lambda content, limits: "raw text"},
    )
    assert contract_failure.report.detail_code == "adapter_contract_violation"

    adapter_limit = parse_source(
        PNG_1X1,
        "image/png",
        adapters={
            "image/png": lambda content, limits: AdapterExtraction(
                "bounded", page_count=2
            )
        },
        limits=ParseLimits(max_pages=1),
    )
    assert adapter_limit.report.detail_code == "page_limit_exceeded"


@pytest.mark.parametrize(
    "warning_codes",
    [
        ["private-warning"],
        (["unhashable-warning"],),
        ("valid-shape", 7),
    ],
)
def test_adapter_warning_contract_failures_map_to_stable_status(warning_codes):
    def invalid_adapter(content: bytes, limits: ParseLimits) -> AdapterExtraction:
        del content, limits
        return AdapterExtraction(
            "adapter content",
            warning_codes=warning_codes,
        )

    result = parse_source(
        PNG_1X1,
        "image/png",
        adapters={"image/png": invalid_adapter},
    )

    assert result.report.status == ParseStatus.REJECTED_ADAPTER_FAILURE
    assert result.report.detail_code == "adapter_exception"


def test_mutated_adapter_output_is_rejected_at_the_return_boundary():
    def mutated_adapter(content: bytes, limits: ParseLimits) -> AdapterExtraction:
        del content, limits
        output = AdapterExtraction("adapter content")
        object.__setattr__(output, "warning_codes", (["unhashable-warning"],))
        return output

    result = parse_source(
        PNG_1X1,
        "image/png",
        adapters={"image/png": mutated_adapter},
    )

    assert result.report.status == ParseStatus.REJECTED_ADAPTER_FAILURE
    assert result.report.detail_code == "adapter_contract_violation"


def test_adapter_resource_limit_precedes_ocr_routing():
    result = parse_source(
        PNG_1X1,
        "image/png",
        adapters={
            "image/png": lambda content, limits: AdapterExtraction(
                "", page_count=2, requires_ocr=True
            )
        },
        limits=ParseLimits(max_pages=1),
    )

    assert result.report.status == ParseStatus.REJECTED_RESOURCE_LIMIT
    assert result.report.detail_code == "page_limit_exceeded"


def test_lifecycle_maps_parser_states_and_preserves_quality_evidence():
    fixture = _fixture()
    now = datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)
    pdf_case = next(
        case
        for case in fixture["cases"]
        if case["case_id"] == "pdf-through-pypdf-provider"
    )
    index = LifecycleIndex(
        policy(), parser_adapters={"application/pdf": pypdf_extraction_adapter}
    )
    accepted = index.ingest(
        SourceRecord(
            document_id="doc-pdf-adapter",
            content=_case_content(pdf_case),
            media_type=pdf_case["media_type"],
            source_version=1,
            source_locator=fixture["source_locator"],
            expected_markers=tuple(pdf_case["expected_markers"]),
        ),
        principal(),
        observed_at=now,
    )
    assert accepted.status == LifecycleStatus.ACCEPTED
    assert accepted.parse_report is not None
    assert accepted.parse_report.status == ParseStatus.PARSED_VIA_ADAPTER
    assert accepted.parse_report.marker_recall == 1.0

    scan_case = next(
        case for case in fixture["cases"] if case["case_id"] == "scan-only-pdf"
    )
    no_adapter = LifecycleIndex(policy()).ingest(
        SourceRecord(
            "doc-scan-only",
            _case_content(scan_case),
            "application/pdf",
            1,
        ),
        principal(),
        observed_at=now,
    )
    assert no_adapter.status == LifecycleStatus.REJECTED_ADAPTER_REQUIRED
    assert no_adapter.detail_code == "pdf_adapter_required"


def test_tombstone_first_cascade_is_content_free_retryable_and_idempotent():
    now = datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)
    cache = RetrievalCache()
    index = LifecycleIndex(policy(), cache)
    document_id = "doc-private-cascade-991"
    raw_marker = "RAW-PRIVATE-CANARY-991"
    locator = "s3://private-bucket/raw/private-cascade-991"
    record = SourceRecord(
        document_id=document_id,
        content=f"{raw_marker} deletion lineage evidence".encode(),
        media_type="text/plain",
        source_version=1,
        source_locator=locator,
        expected_markers=(raw_marker,),
    )
    assert index.ingest(record, principal(), observed_at=now).status == LifecycleStatus.ACCEPTED

    inventory = {
        entry.artifact_kind: entry
        for entry in index.artifact_inventory(document_id, principal())
    }
    parsed_parent = inventory[ArtifactKind.PARSED].artifact_fingerprints[0]
    chunk_parent = inventory[ArtifactKind.CHUNK].artifact_fingerprints[0]
    vector = index.register_derived_artifact(
        document_id,
        ArtifactKind.VECTOR,
        b"PRIVATE-VECTOR-PAYLOAD",
        principal(),
        parent_fingerprints=(parsed_parent,),
    )
    assert vector

    request = RagQueryRequest(raw_marker, "demo", 1)
    assert index.query(request, principal(), observed_at=now).retrieval.chunks
    inventory = {
        entry.artifact_kind: entry
        for entry in index.artifact_inventory(document_id, principal())
    }
    assert inventory[ArtifactKind.CACHE].active_count == 1

    prompt_text = "PRIVATE-PROMPT-CANARY-992"
    output_text = "PRIVATE-OUTPUT-CANARY-993"
    citation_text = "PRIVATE-CITATION-CANARY-994"
    prompt = index.register_derived_artifact(
        document_id,
        ArtifactKind.PROMPT,
        prompt_text,
        principal(),
        parent_fingerprints=(chunk_parent,),
    )
    output = index.register_derived_artifact(
        document_id,
        ArtifactKind.OUTPUT,
        output_text,
        principal(),
        parent_fingerprints=(prompt,),
    )
    index.register_derived_artifact(
        document_id,
        ArtifactKind.CITATION,
        citation_text,
        principal(),
        parent_fingerprints=(output, chunk_parent),
    )

    inventory = {
        entry.artifact_kind: entry
        for entry in index.artifact_inventory(document_id, principal())
    }
    assert all(inventory[kind].active_count > 0 for kind in ArtifactKind)
    with pytest.raises(ValueError, match="lineage_parent_kind_mismatch"):
        index.register_derived_artifact(
            document_id,
            ArtifactKind.OUTPUT,
            "invalid lineage",
            principal(),
            parent_fingerprints=(parsed_parent,),
        )

    version_before_delete = index.collection_version
    pending = index.delete_with_receipt(
        document_id,
        2,
        principal(),
        fail_after=ArtifactKind.CHUNK,
    )
    assert pending.outcome.status == LifecycleStatus.DELETE_PENDING
    assert pending.receipt.retryable
    assert pending.receipt.tombstone_retained
    assert pending.receipt.reference_payload_copies_remaining > 0
    assert index.collection_version != version_before_delete
    assert index.active_documents(principal()) == ()

    blocked_reingestion = index.ingest(
        SourceRecord(
            document_id,
            b"must wait for the pending cascade",
            "text/plain",
            3,
        ),
        principal(),
        observed_at=now,
    )
    assert blocked_reingestion.status == LifecycleStatus.REJECTED_DELETE_PENDING
    assert blocked_reingestion.detail_code == "delete_cascade_pending"

    # The old cache remains physically present until its cascade step, but the
    # tombstone's collection version makes it unreachable immediately.
    after_tombstone = index.query(request, principal(), observed_at=now)
    assert not after_tombstone.cache_hit
    assert after_tombstone.retrieval.chunks == ()

    completed = index.delete_with_receipt(document_id, 2, principal())
    assert completed.outcome.status == LifecycleStatus.DELETED
    assert completed.receipt.reference_payload_copies_remaining == 0
    assert not completed.receipt.retryable
    assert not completed.receipt.external_physical_erasure_verified
    assert completed.receipt.boundary_code == (
        "external_storage_and_backup_erasure_not_verified"
    )
    invalidated = {
        item.artifact_kind: item.invalidated_count
        for item in completed.receipt.invalidations
    }
    assert all(invalidated[kind] > 0 for kind in ArtifactKind)
    assert all(
        entry.active_count == 0
        for entry in index.artifact_inventory(document_id, principal())
    )
    assert cache.entry_count == 0

    receipt_json = json.dumps(
        completed.receipt.to_audit_dict(), ensure_ascii=True, sort_keys=True
    )
    for private_value in (
        document_id,
        raw_marker,
        locator,
        prompt_text,
        output_text,
        citation_text,
        principal().user_id,
    ):
        assert private_value not in receipt_json

    replay = index.delete_with_receipt(document_id, 2, principal())
    assert replay.outcome.status == LifecycleStatus.DELETED
    assert replay.receipt.operation_fingerprint == completed.receipt.operation_fingerprint
    assert replay.receipt.invalidations == completed.receipt.invalidations

    stale_delete = index.delete_with_receipt(document_id, 1, principal())
    assert stale_delete.outcome.status == LifecycleStatus.REJECTED_VERSION_CONFLICT
    assert not stale_delete.receipt.tombstone_retained

    stale = index.ingest(record, principal(), observed_at=now)
    assert stale.status == LifecycleStatus.REJECTED_VERSION_CONFLICT
    fresh = index.ingest(
        SourceRecord(
            document_id,
            b"fresh version after a deliberate tombstone",
            "text/plain",
            3,
        ),
        principal(),
        observed_at=now,
    )
    assert fresh.status == LifecycleStatus.ACCEPTED


def test_retention_removes_every_reference_payload_copy():
    now = datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc)
    document_id = "doc-retention-cascade"
    index = LifecycleIndex(policy())
    index.ingest(
        SourceRecord(
            document_id,
            b"RETENTION-CASCADE-551 evidence",
            "text/plain",
            1,
            expires_at=now + timedelta(minutes=1),
        ),
        principal(),
        observed_at=now,
    )
    assert any(
        entry.active_count
        for entry in index.artifact_inventory(document_id, principal())
    )

    expired = index.expire_documents(
        principal(), observed_at=now + timedelta(minutes=2)
    )

    assert [outcome.status for outcome in expired] == [LifecycleStatus.EXPIRED]
    assert all(
        entry.active_count == 0
        for entry in index.artifact_inventory(document_id, principal())
    )
