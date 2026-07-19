from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile
import csv
import posixpath
import re

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException
from pypdf import PdfReader
from pypdf.generic import ContentStream


PLAIN_MEDIA_TYPES = frozenset({"text/plain", "text/markdown"})
HTML_MEDIA_TYPE = "text/html"
XHTML_MEDIA_TYPE = "application/xhtml+xml"
HTML_MEDIA_TYPES = frozenset({HTML_MEDIA_TYPE, XHTML_MEDIA_TYPE})
TABLE_MEDIA_TYPES = frozenset({"text/csv", "text/tab-separated-values"})
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"
OCR_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/tiff"})
ADAPTER_MEDIA_TYPES = frozenset({PDF_MEDIA_TYPE, *OCR_MEDIA_TYPES})
SUPPORTED_MEDIA_TYPES = frozenset(
    {
        *PLAIN_MEDIA_TYPES,
        *HTML_MEDIA_TYPES,
        *TABLE_MEDIA_TYPES,
        DOCX_MEDIA_TYPE,
        XLSX_MEDIA_TYPE,
        *ADAPTER_MEDIA_TYPES,
    }
)

_SAFE_ADAPTER_WARNINGS = frozenset(
    {
        "layout_not_preserved",
        "low_ocr_confidence",
        "partial_page",
        "table_structure_lost",
    }
)
_XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
_WORD_DOCUMENT_PATH = "word/document.xml"
_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_SHEET_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CONTENT_TYPES_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
_PACKAGE_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
_DOCUMENT_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_OFFICE_DOCUMENT_RELATIONSHIP = (
    f"{_DOCUMENT_RELATIONSHIPS_NAMESPACE}/officeDocument"
)
_WORKSHEET_RELATIONSHIP = f"{_DOCUMENT_RELATIONSHIPS_NAMESPACE}/worksheet"
_SHARED_STRINGS_RELATIONSHIP = (
    f"{_DOCUMENT_RELATIONSHIPS_NAMESPACE}/sharedStrings"
)
_DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document."
    "main+xml"
)
_XLSX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)
_XLSX_WORKSHEET_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)
_XLSX_SHARED_STRINGS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"
)


class ParseStatus(StrEnum):
    PARSED = "parsed"
    PARSED_VIA_ADAPTER = "parsed_via_adapter"
    REJECTED_ADAPTER_FAILURE = "rejected_adapter_failure"
    REJECTED_ADAPTER_REQUIRED = "rejected_adapter_required"
    REJECTED_BLANK = "rejected_blank"
    REJECTED_CORRUPT = "rejected_corrupt"
    REJECTED_OCR_REQUIRED = "rejected_ocr_required"
    REJECTED_RESOURCE_LIMIT = "rejected_resource_limit"
    REJECTED_UNSUPPORTED_MEDIA = "rejected_unsupported_media"


@dataclass(frozen=True)
class ParseLimits:
    max_input_bytes: int = 2_000_000
    max_output_chars: int = 200_000
    max_archive_entries: int = 128
    max_archive_uncompressed_bytes: int = 8_000_000
    max_pages: int = 1_000
    max_table_cells: int = 50_000

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class AdapterExtraction:
    text: str = field(repr=False)
    block_count: int = 1
    table_count: int = 0
    row_count: int = 0
    page_count: int = 0
    table_cell_count: int = 0
    warning_codes: tuple[str, ...] = ()
    requires_ocr: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("adapter text must be str")
        if not isinstance(self.requires_ocr, bool):
            raise TypeError("requires_ocr must be bool")
        if not isinstance(self.warning_codes, tuple):
            raise TypeError("warning_codes must be tuple")
        if any(not isinstance(code, str) for code in self.warning_codes):
            raise TypeError("warning_codes entries must be str")
        for name in (
            "block_count",
            "table_count",
            "row_count",
            "page_count",
            "table_cell_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


ExtractionAdapter = Callable[[bytes, ParseLimits], AdapterExtraction]


def _adapter_output_contract_valid(value: object) -> bool:
    if not isinstance(value, AdapterExtraction):
        return False
    try:
        counts = (
            value.block_count,
            value.table_count,
            value.row_count,
            value.page_count,
            value.table_cell_count,
        )
        return (
            isinstance(value.text, str)
            and isinstance(value.requires_ocr, bool)
            and isinstance(value.warning_codes, tuple)
            and all(isinstance(code, str) for code in value.warning_codes)
            and all(
                not isinstance(count, bool)
                and isinstance(count, int)
                and count >= 0
                for count in counts
            )
        )
    except Exception:
        return False


def pypdf_extraction_adapter(
    content: bytes, limits: ParseLimits
) -> AdapterExtraction:
    """Extract born-digital PDF text with the pinned pypdf provider.

    This adapter is intentionally explicit. In production, third-party document
    parsers still belong in a time-, memory-, and network-restricted worker; the
    absolute limits here are a reference contract, not a process sandbox.
    """

    reader = PdfReader(BytesIO(content), strict=True)
    if reader.is_encrypted:
        raise ValueError("encrypted_pdf_not_supported")

    page_count = len(reader.pages)
    if page_count > limits.max_pages:
        # parse_source maps the reported count to its stable resource-limit code
        # before considering the intentionally empty extraction.
        return AdapterExtraction(text="", page_count=page_count)

    parts: list[str] = []
    block_count = 0
    image_page_found = False
    output_chars = 0
    for page in reader.pages:
        page_text = page.extract_text() or ""
        page_has_images = _pypdf_page_has_images(page)
        image_page_found = image_page_found or page_has_images
        if page_text.strip():
            parts.append(page_text)
            block_count += 1
            output_chars += len(page_text)
            if output_chars > limits.max_output_chars:
                return AdapterExtraction(
                    text="x" * (limits.max_output_chars + 1),
                    block_count=block_count,
                    page_count=page_count,
                    warning_codes=(
                        ("layout_not_preserved", "partial_page")
                        if image_page_found
                        else ("layout_not_preserved",)
                    ),
                )

    warning_codes: tuple[str, ...] = ()
    if parts:
        warning_codes = (
            ("layout_not_preserved", "partial_page")
            if image_page_found
            else ("layout_not_preserved",)
        )
    return AdapterExtraction(
        text="\n\n".join(parts),
        block_count=block_count,
        page_count=page_count,
        warning_codes=warning_codes,
        requires_ocr=not parts and image_page_found,
    )


def _pypdf_page_has_images(page: Any) -> bool:
    return _pdf_content_has_images(
        page.get_contents(),
        page.get("/Resources"),
        page.pdf,
        visited=set(),
    )


def _pdf_object_identity(value: Any) -> tuple[int, int, int]:
    resolved = value.get_object()
    reference = getattr(resolved, "indirect_reference", None)
    if reference is not None:
        return (
            id(reference.pdf),
            int(reference.idnum),
            int(reference.generation),
        )
    return (0, id(resolved), 0)


def _pdf_content_has_images(
    contents: Any,
    resources: Any,
    pdf: Any,
    *,
    visited: set[
        tuple[tuple[int, int, int], tuple[int, int, int]]
    ],
) -> bool:
    if contents is None:
        return False
    operations = ContentStream(contents, pdf).operations
    if any(operator == b"INLINE IMAGE" for _, operator in operations):
        return True
    if resources is None:
        return False
    resource_object = resources.get_object()
    xobjects = resource_object.get("/XObject")
    xobject_map = {} if xobjects is None else xobjects.get_object()
    for operands, operator in operations:
        if operator != b"Do" or not operands:
            continue
        reference = xobject_map.get(operands[0])
        if reference is None:
            continue
        xobject = reference.get_object()
        subtype_value = xobject.get("/Subtype")
        subtype = subtype_value.get_object() if subtype_value is not None else None
        if subtype == "/Image":
            return True
        if subtype == "/Form":
            effective_resources = xobject.get("/Resources", resource_object)
            effective_resource_object = effective_resources.get_object()
            visit_key = (
                _pdf_object_identity(xobject),
                _pdf_object_identity(effective_resource_object),
            )
            if visit_key in visited:
                continue
            visited.add(visit_key)
            if _pdf_content_has_images(
                xobject,
                effective_resource_object,
                pdf,
                visited=visited,
            ):
                return True
    return False


@dataclass(frozen=True)
class ParseQualityReport:
    status: ParseStatus
    media_type: str
    parser_id: str
    parser_version: str
    source_version: str
    source_locator_fingerprint: str
    detail_code: str
    content_fingerprint: str
    raw_sha256: str
    parsed_sha256: str | None
    input_bytes: int
    output_chars: int
    block_count: int
    table_count: int
    row_count: int
    page_count: int
    table_cell_count: int
    archive_entry_count: int
    archive_uncompressed_bytes: int
    expected_marker_count: int
    observed_marker_count: int
    marker_recall: float | None
    warning_codes: tuple[str, ...]
    adapter_used: bool

    def to_audit_dict(self) -> dict[str, Any]:
        """Return structured evidence containing metrics and fingerprints, never text."""

        payload = asdict(self)
        payload["status"] = self.status.value
        payload["warning_codes"] = list(self.warning_codes)
        return payload


@dataclass(frozen=True)
class ParseResult:
    report: ParseQualityReport
    text: str = field(default="", repr=False)

    @property
    def accepted(self) -> bool:
        return self.report.status in {
            ParseStatus.PARSED,
            ParseStatus.PARSED_VIA_ADAPTER,
        }


@dataclass(frozen=True)
class _ExtractionMetrics:
    text: str = field(repr=False)
    block_count: int = 0
    table_count: int = 0
    row_count: int = 0
    page_count: int = 0
    table_cell_count: int = 0
    archive_entry_count: int = 0
    archive_uncompressed_bytes: int = 0
    warning_codes: tuple[str, ...] = ()


class _VisibleHTMLParser(HTMLParser):
    _BLOCK_TAGS = frozenset(
        {
            "article",
            "blockquote",
            "br",
            "div",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "li",
            "main",
            "p",
            "section",
        }
    )
    _HIDDEN_TAGS = frozenset(
        {
            "iframe",
            "noembed",
            "noframes",
            "noscript",
            "script",
            "style",
            "template",
        }
    )
    _DOCUMENT_CONTAINER_TAGS = frozenset({"body", "html"})
    _VOID_TAGS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self, max_table_cells: int) -> None:
        super().__init__(convert_charrefs=True)
        self.max_table_cells = max_table_cells
        self.parts: list[str] = []
        self.hidden_stack: list[str] = []
        self.document_hidden = False
        self.block_count = 0
        self.table_count = 0
        self.row_count = 0
        self.table_cells = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        normalized = tag.lower()
        if normalized == "plaintext":
            raise _CorruptInput("unsupported_html_tokenization_state")
        has_hidden_attribute = any(name.lower() == "hidden" for name, _ in attrs)
        if self.document_hidden:
            return
        if has_hidden_attribute and normalized in self._DOCUMENT_CONTAINER_TAGS:
            self._hide_document()
            return
        if self.hidden_stack:
            if normalized not in self._VOID_TAGS:
                self.hidden_stack.append(normalized)
            return
        if normalized in self._HIDDEN_TAGS or has_hidden_attribute:
            if normalized not in self._VOID_TAGS:
                self.hidden_stack.append(normalized)
            return
        if normalized in self._BLOCK_TAGS:
            self.parts.append("\n")
            self.block_count += 1
        if normalized == "table":
            self.parts.append("\n")
            self.table_count += 1
        elif normalized == "tr":
            self.parts.append("\n")
            self.row_count += 1
        elif normalized in {"td", "th"}:
            self.parts.append("\t")
            self.table_cells += 1
            if self.table_cells > self.max_table_cells:
                raise _ResourceLimit("table_cell_limit_exceeded")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        normalized = tag.lower()
        if normalized == "plaintext":
            raise _CorruptInput("unsupported_html_tokenization_state")
        has_hidden_attribute = any(name.lower() == "hidden" for name, _ in attrs)
        if self.document_hidden:
            return
        if has_hidden_attribute and normalized in self._DOCUMENT_CONTAINER_TAGS:
            self._hide_document()
            return
        if normalized in self._VOID_TAGS:
            self.handle_starttag(tag, attrs)
            return
        if (
            self.hidden_stack
            or normalized in self._HIDDEN_TAGS
            or has_hidden_attribute
        ):
            raise _CorruptInput("malformed_html_hidden_nesting")
        super().handle_startendtag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.document_hidden:
            return
        normalized = tag.lower()
        if self.hidden_stack:
            if self.hidden_stack[-1] != normalized:
                raise _CorruptInput("malformed_html_hidden_nesting")
            self.hidden_stack.pop()
            return
        if normalized in self._HIDDEN_TAGS:
            return
        if normalized in self._BLOCK_TAGS or normalized in {"table", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.document_hidden and not self.hidden_stack:
            self.parts.append(data)

    def _hide_document(self) -> None:
        self.document_hidden = True
        self.parts.clear()
        self.hidden_stack.clear()
        self.block_count = 0
        self.table_count = 0
        self.row_count = 0
        self.table_cells = 0


class _ResourceLimit(ValueError):
    pass


class _CorruptInput(ValueError):
    pass


def parse_source(
    content: bytes,
    media_type: str,
    *,
    adapters: Mapping[str, ExtractionAdapter] | None = None,
    limits: ParseLimits | None = None,
    source_version: str = "not_provided",
    source_locator: str = "",
    expected_markers: tuple[str, ...] = (),
) -> ParseResult:
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    if not isinstance(media_type, str) or not media_type.strip():
        raise ValueError("media_type must not be empty")
    if not isinstance(source_locator, str):
        raise TypeError("source_locator must be str")
    if not isinstance(expected_markers, tuple) or any(
        not isinstance(marker, str) or not marker for marker in expected_markers
    ):
        raise ValueError("expected_markers must be a tuple of non-empty strings")

    active_limits = limits or ParseLimits()
    normalized_media_type = media_type.partition(";")[0].strip().lower()
    fingerprint = sha256(content).hexdigest()
    parser_id = _parser_id(normalized_media_type)
    adapter_used = False
    audit_context = {
        "source_version": _safe_version(source_version),
        "source_locator_fingerprint": sha256(
            source_locator.encode("utf-8")
        ).hexdigest(),
        "expected_marker_count": len(expected_markers),
    }

    if len(content) > active_limits.max_input_bytes:
        return _failure(
            ParseStatus.REJECTED_RESOURCE_LIMIT,
            normalized_media_type,
            parser_id,
            "input_byte_limit_exceeded",
            fingerprint,
            len(content),
            **audit_context,
        )
    if normalized_media_type not in SUPPORTED_MEDIA_TYPES:
        return _failure(
            ParseStatus.REJECTED_UNSUPPORTED_MEDIA,
            normalized_media_type,
            "none",
            "unsupported_media_type",
            fingerprint,
            len(content),
            **audit_context,
        )
    if not content:
        return _failure(
            ParseStatus.REJECTED_BLANK,
            normalized_media_type,
            parser_id,
            "empty_input",
            fingerprint,
            0,
            **audit_context,
        )

    signature_error = _signature_error(content, normalized_media_type)
    if signature_error is not None:
        return _failure(
            ParseStatus.REJECTED_CORRUPT,
            normalized_media_type,
            parser_id,
            signature_error,
            fingerprint,
            len(content),
            **audit_context,
        )
    try:
        if normalized_media_type in PLAIN_MEDIA_TYPES:
            extracted = _parse_plain(content)
        elif normalized_media_type == HTML_MEDIA_TYPE:
            extracted = _parse_html(content, active_limits)
        elif normalized_media_type == XHTML_MEDIA_TYPE:
            extracted = _parse_xhtml(content, active_limits)
        elif normalized_media_type in TABLE_MEDIA_TYPES:
            delimiter = "\t" if normalized_media_type == "text/tab-separated-values" else ","
            extracted = _parse_delimited(content, delimiter, active_limits)
        elif normalized_media_type == DOCX_MEDIA_TYPE:
            extracted = _parse_docx(content, active_limits)
        elif normalized_media_type == XLSX_MEDIA_TYPE:
            extracted = _parse_xlsx(content, active_limits)
        else:
            adapter = (adapters or {}).get(normalized_media_type)
            if adapter is None:
                kind = "pdf" if normalized_media_type == PDF_MEDIA_TYPE else "ocr"
                return _failure(
                    ParseStatus.REJECTED_ADAPTER_REQUIRED,
                    normalized_media_type,
                    parser_id,
                    f"{kind}_adapter_required",
                    fingerprint,
                    len(content),
                    **audit_context,
                )
            adapter_used = True
            try:
                adapter_output = adapter(content, active_limits)
            except Exception:
                return _failure(
                    ParseStatus.REJECTED_ADAPTER_FAILURE,
                    normalized_media_type,
                    parser_id,
                    "adapter_exception",
                    fingerprint,
                    len(content),
                    adapter_used=True,
                    **audit_context,
                )
            if not _adapter_output_contract_valid(adapter_output):
                return _failure(
                    ParseStatus.REJECTED_ADAPTER_FAILURE,
                    normalized_media_type,
                    parser_id,
                    "adapter_contract_violation",
                    fingerprint,
                    len(content),
                    adapter_used=True,
                    **audit_context,
                )
            if adapter_output.page_count > active_limits.max_pages:
                raise _ResourceLimit("page_limit_exceeded")
            if adapter_output.table_cell_count > active_limits.max_table_cells:
                raise _ResourceLimit("table_cell_limit_exceeded")
            if len(adapter_output.text) > active_limits.max_output_chars:
                raise _ResourceLimit("output_character_limit_exceeded")
            if adapter_output.requires_ocr:
                return _failure(
                    ParseStatus.REJECTED_OCR_REQUIRED,
                    normalized_media_type,
                    parser_id,
                    "adapter_requires_ocr",
                    fingerprint,
                    len(content),
                    adapter_used=True,
                    metrics=_ExtractionMetrics(
                        "",
                        page_count=adapter_output.page_count,
                        warning_codes=_sanitize_warning_codes(
                            adapter_output.warning_codes
                        ),
                    ),
                    **audit_context,
                )
            extracted = _ExtractionMetrics(
                text=adapter_output.text,
                block_count=adapter_output.block_count,
                table_count=adapter_output.table_count,
                row_count=adapter_output.row_count,
                page_count=adapter_output.page_count,
                table_cell_count=adapter_output.table_cell_count,
                warning_codes=_sanitize_warning_codes(adapter_output.warning_codes),
            )
    except UnicodeDecodeError:
        return _failure(
            ParseStatus.REJECTED_CORRUPT,
            normalized_media_type,
            parser_id,
            "invalid_utf8",
            fingerprint,
            len(content),
            **audit_context,
        )
    except _ResourceLimit as error:
        return _failure(
            ParseStatus.REJECTED_RESOURCE_LIMIT,
            normalized_media_type,
            parser_id,
            str(error),
            fingerprint,
            len(content),
            adapter_used=adapter_used,
            **audit_context,
        )
    except _CorruptInput as error:
        return _failure(
            ParseStatus.REJECTED_CORRUPT,
            normalized_media_type,
            parser_id,
            str(error),
            fingerprint,
            len(content),
            **audit_context,
        )

    text = _normalize_extracted_text(extracted.text)
    if not text:
        return _failure(
            ParseStatus.REJECTED_BLANK,
            normalized_media_type,
            parser_id,
            "blank_after_parse",
            fingerprint,
            len(content),
            adapter_used=adapter_used,
            metrics=extracted,
            **audit_context,
        )
    if len(text) > active_limits.max_output_chars:
        return _failure(
            ParseStatus.REJECTED_RESOURCE_LIMIT,
            normalized_media_type,
            parser_id,
            "output_character_limit_exceeded",
            fingerprint,
            len(content),
            adapter_used=adapter_used,
            metrics=extracted,
            **audit_context,
        )

    status = (
        ParseStatus.PARSED_VIA_ADAPTER if adapter_used else ParseStatus.PARSED
    )
    detail_code = (
        "parsed_via_pdf_adapter"
        if normalized_media_type == PDF_MEDIA_TYPE
        else "parsed_via_ocr_adapter"
        if normalized_media_type in OCR_MEDIA_TYPES
        else "parsed"
    )
    matched_markers = sum(marker in text for marker in expected_markers)
    marker_recall = (
        matched_markers / len(expected_markers) if expected_markers else None
    )
    parsed_fingerprint = sha256(text.encode("utf-8")).hexdigest()
    return ParseResult(
        report=ParseQualityReport(
            status=status,
            media_type=normalized_media_type,
            parser_id=parser_id,
            parser_version="1.0",
            source_version=audit_context["source_version"],
            source_locator_fingerprint=audit_context[
                "source_locator_fingerprint"
            ],
            detail_code=detail_code,
            content_fingerprint=fingerprint,
            raw_sha256=fingerprint,
            parsed_sha256=parsed_fingerprint,
            input_bytes=len(content),
            output_chars=len(text),
            block_count=extracted.block_count,
            table_count=extracted.table_count,
            row_count=extracted.row_count,
            page_count=extracted.page_count,
            table_cell_count=extracted.table_cell_count,
            archive_entry_count=extracted.archive_entry_count,
            archive_uncompressed_bytes=extracted.archive_uncompressed_bytes,
            expected_marker_count=len(expected_markers),
            observed_marker_count=matched_markers,
            marker_recall=marker_recall,
            warning_codes=extracted.warning_codes,
            adapter_used=adapter_used,
        ),
        text=text,
    )


def _parse_plain(content: bytes) -> _ExtractionMetrics:
    text = content.decode("utf-8-sig", errors="strict")
    blocks = len([part for part in re.split(r"\n\s*\n", text) if part.strip()])
    return _ExtractionMetrics(text=text, block_count=blocks)


def _parse_html(content: bytes, limits: ParseLimits) -> _ExtractionMetrics:
    text = content.decode("utf-8-sig", errors="strict")
    parser = _VisibleHTMLParser(limits.max_table_cells)
    try:
        parser.feed(text)
        parser.close()
        if parser.hidden_stack:
            raise _CorruptInput("malformed_html_hidden_nesting")
    except (_ResourceLimit, _CorruptInput):
        raise
    except Exception as error:
        raise _CorruptInput("malformed_html") from error
    return _ExtractionMetrics(
        text="".join(parser.parts),
        block_count=parser.block_count,
        table_count=parser.table_count,
        row_count=parser.row_count,
        table_cell_count=parser.table_cells,
    )


def _parse_xhtml(content: bytes, limits: ParseLimits) -> _ExtractionMetrics:
    try:
        root = SafeElementTree.fromstring(
            content,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except DefusedXmlException as error:
        raise _CorruptInput("unsafe_xhtml_declaration") from error
    except ElementTree.ParseError as error:
        raise _CorruptInput("malformed_xhtml") from error

    if root.tag != f"{{{_XHTML_NAMESPACE}}}html":
        raise _CorruptInput("invalid_xhtml_root")

    parts: list[str] = []
    block_count = 0
    table_count = 0
    row_count = 0
    table_cell_count = 0
    pending: list[tuple[str, ElementTree.Element]] = [("enter", root)]
    while pending:
        action, element = pending.pop()
        tag = _xml_local_name(element.tag).lower()
        if action == "exit":
            if tag in _VisibleHTMLParser._BLOCK_TAGS - {"br"} or tag in {
                "table",
                "tr",
            }:
                parts.append("\n")
            if element.tail:
                parts.append(element.tail)
            continue

        has_hidden_attribute = any(
            _xml_local_name(name).lower() == "hidden" for name in element.attrib
        )
        if tag in _VisibleHTMLParser._HIDDEN_TAGS or has_hidden_attribute:
            if element.tail:
                parts.append(element.tail)
            continue

        if tag in _VisibleHTMLParser._BLOCK_TAGS:
            parts.append("\n")
            block_count += 1
        if tag == "table":
            parts.append("\n")
            table_count += 1
        elif tag == "tr":
            parts.append("\n")
            row_count += 1
        elif tag in {"td", "th"}:
            parts.append("\t")
            table_cell_count += 1
            if table_cell_count > limits.max_table_cells:
                raise _ResourceLimit("table_cell_limit_exceeded")
        if element.text:
            parts.append(element.text)

        pending.append(("exit", element))
        pending.extend(("enter", child) for child in reversed(list(element)))

    return _ExtractionMetrics(
        text="".join(parts),
        block_count=block_count,
        table_count=table_count,
        row_count=row_count,
        table_cell_count=table_cell_count,
    )


def _parse_delimited(
    content: bytes, delimiter: str, limits: ParseLimits
) -> _ExtractionMetrics:
    text = content.decode("utf-8-sig", errors="strict")
    rows: list[str] = []
    cell_count = 0
    try:
        reader = csv.reader(StringIO(text, newline=""), delimiter=delimiter, strict=True)
        for row in reader:
            cell_count += len(row)
            if cell_count > limits.max_table_cells:
                raise _ResourceLimit("table_cell_limit_exceeded")
            rows.append("\t".join(_normalize_inline_text(cell) for cell in row))
    except csv.Error as error:
        raise _CorruptInput("malformed_delimited_table") from error
    return _ExtractionMetrics(
        text="\n".join(rows),
        block_count=len(rows),
        table_count=1 if rows else 0,
        row_count=len(rows),
        table_cell_count=cell_count,
    )


def _parse_docx(content: bytes, limits: ParseLimits) -> _ExtractionMetrics:
    archive = _open_office_archive(content, "docx")
    with archive:
        infos, names, total_uncompressed = _office_archive_inventory(
            archive, "docx", limits
        )
        content_types = _office_content_types(archive, names, "docx")
        root_relationships = _office_relationships(
            archive,
            names,
            relationship_part="_rels/.rels",
            source_part="",
            kind="docx",
        )
        document_name = _single_relationship_target(
            root_relationships,
            _OFFICE_DOCUMENT_RELATIONSHIP,
            "missing_docx_office_document_relationship",
        )
        _require_package_part(names, document_name, "missing_docx_document_xml")
        _require_content_type(
            content_types,
            document_name,
            _DOCX_MAIN_CONTENT_TYPE,
            "invalid_docx_document_content_type",
        )
        xml_bytes = _read_office_member(
            archive, names[document_name], "invalid_docx_archive_member"
        )

    root = _safe_xml_root(xml_bytes, "malformed_docx_xml")
    if root.tag != f"{{{_WORD_NAMESPACE}}}document":
        raise _CorruptInput("invalid_docx_document_root")

    body = root.find(f".//{{{_WORD_NAMESPACE}}}body")
    if body is None:
        raise _CorruptInput("missing_docx_body")
    parts: list[str] = []
    block_count = 0
    table_count = 0
    row_count = 0
    table_cells = 0
    for child in body:
        if child.tag == f"{{{_WORD_NAMESPACE}}}p":
            paragraph = _word_text(child)
            if paragraph.strip():
                parts.append(paragraph)
                block_count += 1
        elif child.tag == f"{{{_WORD_NAMESPACE}}}tbl":
            table_count += 1
            table_rows: list[str] = []
            for row in child.findall(f"{{{_WORD_NAMESPACE}}}tr"):
                cells = [
                    _word_text(cell)
                    for cell in row.findall(f"{{{_WORD_NAMESPACE}}}tc")
                ]
                table_cells += len(cells)
                if table_cells > limits.max_table_cells:
                    raise _ResourceLimit("table_cell_limit_exceeded")
                table_rows.append("\t".join(cells))
                row_count += 1
            if table_rows:
                parts.append("\n".join(table_rows))
                block_count += len(table_rows)
    return _ExtractionMetrics(
        text="\n".join(parts),
        block_count=block_count,
        table_count=table_count,
        row_count=row_count,
        table_cell_count=table_cells,
        archive_entry_count=len(infos),
        archive_uncompressed_bytes=total_uncompressed,
    )


def _parse_xlsx(content: bytes, limits: ParseLimits) -> _ExtractionMetrics:
    archive = _open_office_archive(content, "xlsx")
    with archive:
        infos, names, total_uncompressed = _office_archive_inventory(
            archive, "xlsx", limits
        )
        content_types = _office_content_types(archive, names, "xlsx")
        root_relationships = _office_relationships(
            archive,
            names,
            relationship_part="_rels/.rels",
            source_part="",
            kind="xlsx",
        )
        workbook_name = _single_relationship_target(
            root_relationships,
            _OFFICE_DOCUMENT_RELATIONSHIP,
            "missing_xlsx_office_document_relationship",
        )
        _require_package_part(names, workbook_name, "missing_xlsx_workbook_xml")
        _require_content_type(
            content_types,
            workbook_name,
            _XLSX_MAIN_CONTENT_TYPE,
            "invalid_xlsx_workbook_content_type",
        )
        workbook_xml = _read_office_member(
            archive, names[workbook_name], "invalid_xlsx_archive_member"
        )
        workbook_root = _safe_xml_root(workbook_xml, "malformed_xlsx_workbook")
        if workbook_root.tag != f"{{{_SHEET_NAMESPACE}}}workbook":
            raise _CorruptInput("invalid_xlsx_workbook_root")

        workbook_relationships = _office_relationships(
            archive,
            names,
            relationship_part=_relationship_part_for(workbook_name),
            source_part=workbook_name,
            kind="xlsx",
        )
        sheet_names = _xlsx_referenced_sheets(
            workbook_root, workbook_relationships, names, content_types
        )
        sheet_payloads = [
            (
                name,
                _read_office_member(
                    archive, names[name], "invalid_xlsx_archive_member"
                ),
            )
            for name in sheet_names
        ]

        shared_relationships = [
            relationship
            for relationship in workbook_relationships.values()
            if relationship[0] == _SHARED_STRINGS_RELATIONSHIP
        ]
        if len(shared_relationships) > 1:
            raise _CorruptInput("duplicate_xlsx_shared_strings_relationship")
        if shared_relationships:
            _, shared_name, external = shared_relationships[0]
            if external:
                raise _CorruptInput("external_xlsx_shared_strings_relationship")
            _require_package_part(
                names, shared_name, "missing_xlsx_shared_strings_xml"
            )
            _require_content_type(
                content_types,
                shared_name,
                _XLSX_SHARED_STRINGS_CONTENT_TYPE,
                "invalid_xlsx_shared_strings_content_type",
            )
            shared_xml = _read_office_member(
                archive, names[shared_name], "invalid_xlsx_archive_member"
            )
            shared_strings = _xlsx_shared_strings(shared_xml)
        else:
            shared_strings = ()

    rows: list[str] = []
    cell_count = 0
    row_count = 0
    for _, xml_bytes in sheet_payloads:
        root = _safe_xml_root(xml_bytes, "malformed_xlsx_xml")
        if root.tag != f"{{{_SHEET_NAMESPACE}}}worksheet":
            raise _CorruptInput("invalid_xlsx_worksheet_root")
        for row in root.iter(f"{{{_SHEET_NAMESPACE}}}row"):
            values: list[str] = []
            for cell in row.findall(f"{{{_SHEET_NAMESPACE}}}c"):
                cell_count += 1
                if cell_count > limits.max_table_cells:
                    raise _ResourceLimit("table_cell_limit_exceeded")
                values.append(_xlsx_cell_text(cell, shared_strings))
            if values:
                rows.append("\t".join(values))
                row_count += 1
    return _ExtractionMetrics(
        text="\n".join(rows),
        block_count=row_count,
        table_count=len(sheet_payloads),
        row_count=row_count,
        table_cell_count=cell_count,
        archive_entry_count=len(infos),
        archive_uncompressed_bytes=total_uncompressed,
    )


def _xlsx_shared_strings(xml_bytes: bytes) -> tuple[str, ...]:
    root = _safe_xml_root(xml_bytes, "malformed_xlsx_shared_strings")
    if root.tag != f"{{{_SHEET_NAMESPACE}}}sst":
        raise _CorruptInput("invalid_xlsx_shared_strings_root")
    return tuple(
        _normalize_inline_text(
            "".join(
                node.text or ""
                for node in item.iter(f"{{{_SHEET_NAMESPACE}}}t")
            )
        )
        for item in root.iter(f"{{{_SHEET_NAMESPACE}}}si")
    )


def _open_office_archive(content: bytes, kind: str) -> ZipFile:
    try:
        return ZipFile(BytesIO(content))
    except Exception as error:
        raise _CorruptInput(f"invalid_{kind}_archive") from error


def _office_archive_inventory(
    archive: ZipFile, kind: str, limits: ParseLimits
) -> tuple[list[Any], dict[str, str], int]:
    try:
        infos = archive.infolist()
    except Exception as error:
        raise _CorruptInput(f"invalid_{kind}_archive") from error
    if len(infos) > limits.max_archive_entries:
        raise _ResourceLimit("archive_entry_limit_exceeded")
    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > limits.max_archive_uncompressed_bytes:
        raise _ResourceLimit("archive_uncompressed_byte_limit_exceeded")
    if any(info.flag_bits & 0x1 for info in infos):
        raise _CorruptInput(f"encrypted_{kind}_not_supported")

    names: dict[str, str] = {}
    for info in infos:
        if info.is_dir():
            continue
        normalized = _normalize_package_member(info.filename)
        if normalized in names:
            raise _CorruptInput("duplicate_office_archive_member")
        names[normalized] = info.filename
    return infos, names, total_uncompressed


def _normalize_package_member(value: str) -> str:
    if not value or "\\" in value or "\x00" in value or value.startswith("/"):
        raise _CorruptInput("unsafe_office_archive_path")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise _CorruptInput("unsafe_office_archive_path")
    normalized = posixpath.normpath(value)
    if normalized in {"", "."} or normalized.startswith("../"):
        raise _CorruptInput("unsafe_office_archive_path")
    return normalized


def _read_office_member(archive: ZipFile, name: str, detail_code: str) -> bytes:
    try:
        return archive.read(name)
    except Exception as error:
        # Includes CRC, truncated-stream, unsupported-compression, and
        # decompressor failures without exposing provider exception text.
        raise _CorruptInput(detail_code) from error


def _office_content_types(
    archive: ZipFile, names: Mapping[str, str], kind: str
) -> tuple[dict[str, str], dict[str, str]]:
    content_types_name = names.get("[Content_Types].xml")
    if content_types_name is None:
        raise _CorruptInput(f"missing_{kind}_content_types")
    payload = _read_office_member(
        archive, content_types_name, f"invalid_{kind}_archive_member"
    )
    root = _safe_xml_root(payload, f"malformed_{kind}_content_types")
    if root.tag != f"{{{_CONTENT_TYPES_NAMESPACE}}}Types":
        raise _CorruptInput(f"invalid_{kind}_content_types_root")

    overrides: dict[str, str] = {}
    defaults: dict[str, str] = {}
    for element in root:
        if element.tag == f"{{{_CONTENT_TYPES_NAMESPACE}}}Override":
            part_name = element.attrib.get("PartName", "")
            content_type = element.attrib.get("ContentType", "")
            if not part_name.startswith("/") or not content_type:
                raise _CorruptInput(f"malformed_{kind}_content_type_entry")
            normalized = _normalize_package_member(part_name[1:])
            if normalized in overrides:
                raise _CorruptInput(f"duplicate_{kind}_content_type_entry")
            overrides[normalized] = content_type
        elif element.tag == f"{{{_CONTENT_TYPES_NAMESPACE}}}Default":
            extension = element.attrib.get("Extension", "").lower()
            content_type = element.attrib.get("ContentType", "")
            if not extension or not content_type or "/" in extension:
                raise _CorruptInput(f"malformed_{kind}_content_type_entry")
            if extension in defaults:
                raise _CorruptInput(f"duplicate_{kind}_content_type_entry")
            defaults[extension] = content_type
    return overrides, defaults


def _require_content_type(
    content_types: tuple[dict[str, str], dict[str, str]],
    part_name: str,
    expected: str,
    detail_code: str,
) -> None:
    overrides, defaults = content_types
    extension = PurePosixPath(part_name).suffix.lstrip(".").lower()
    observed = overrides.get(part_name, defaults.get(extension))
    if observed != expected:
        raise _CorruptInput(detail_code)


def _office_relationships(
    archive: ZipFile,
    names: Mapping[str, str],
    *,
    relationship_part: str,
    source_part: str,
    kind: str,
) -> dict[str, tuple[str, str, bool]]:
    member_name = names.get(relationship_part)
    if member_name is None:
        raise _CorruptInput(f"missing_{kind}_relationships")
    payload = _read_office_member(
        archive, member_name, f"invalid_{kind}_archive_member"
    )
    root = _safe_xml_root(payload, f"malformed_{kind}_relationships")
    if root.tag != f"{{{_PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationships":
        raise _CorruptInput(f"invalid_{kind}_relationships_root")

    relationships: dict[str, tuple[str, str, bool]] = {}
    for element in root:
        if element.tag != f"{{{_PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship":
            continue
        relationship_id = element.attrib.get("Id", "")
        relationship_type = element.attrib.get("Type", "")
        target = element.attrib.get("Target", "")
        if not relationship_id or not relationship_type or not target:
            raise _CorruptInput(f"malformed_{kind}_relationship")
        if relationship_id in relationships:
            raise _CorruptInput(f"duplicate_{kind}_relationship_id")
        external = element.attrib.get("TargetMode", "").lower() == "external"
        resolved = target if external else _resolve_relationship_target(
            source_part, target
        )
        relationships[relationship_id] = (
            relationship_type,
            resolved,
            external,
        )
    return relationships


def _resolve_relationship_target(source_part: str, target: str) -> str:
    if (
        not target
        or "\\" in target
        or "\x00" in target
        or "?" in target
        or "#" in target
    ):
        raise _CorruptInput("unsafe_office_relationship_target")
    if target.startswith("/"):
        candidate = target[1:]
    else:
        parent = str(PurePosixPath(source_part).parent) if source_part else ""
        candidate = posixpath.join("" if parent == "." else parent, target)
    return _normalize_package_member(candidate)


def _single_relationship_target(
    relationships: Mapping[str, tuple[str, str, bool]],
    relationship_type: str,
    missing_code: str,
) -> str:
    matching = [
        relationship
        for relationship in relationships.values()
        if relationship[0] == relationship_type
    ]
    if len(matching) != 1:
        raise _CorruptInput(missing_code)
    _, target, external = matching[0]
    if external:
        raise _CorruptInput("external_office_document_relationship")
    return target


def _relationship_part_for(source_part: str) -> str:
    path = PurePosixPath(source_part)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _require_package_part(
    names: Mapping[str, str], part_name: str, detail_code: str
) -> None:
    if part_name not in names:
        raise _CorruptInput(detail_code)


def _xlsx_referenced_sheets(
    workbook_root: ElementTree.Element,
    relationships: Mapping[str, tuple[str, str, bool]],
    names: Mapping[str, str],
    content_types: tuple[dict[str, str], dict[str, str]],
) -> tuple[str, ...]:
    sheet_elements = list(workbook_root.iter(f"{{{_SHEET_NAMESPACE}}}sheet"))
    if not sheet_elements:
        raise _CorruptInput("missing_xlsx_sheet_reference")

    targets: list[str] = []
    seen: set[str] = set()
    for sheet in sheet_elements:
        relationship_id = sheet.attrib.get(
            f"{{{_DOCUMENT_RELATIONSHIPS_NAMESPACE}}}id", ""
        )
        relationship = relationships.get(relationship_id)
        if relationship is None or relationship[0] != _WORKSHEET_RELATIONSHIP:
            raise _CorruptInput("invalid_xlsx_sheet_relationship")
        _, target, external = relationship
        if external:
            raise _CorruptInput("external_xlsx_sheet_relationship")
        if target in seen:
            raise _CorruptInput("duplicate_xlsx_sheet_target")
        _require_package_part(names, target, "missing_xlsx_worksheet_xml")
        _require_content_type(
            content_types,
            target,
            _XLSX_WORKSHEET_CONTENT_TYPE,
            "invalid_xlsx_worksheet_content_type",
        )
        seen.add(target)
        targets.append(target)
    return tuple(targets)


def _xlsx_cell_text(
    cell: ElementTree.Element, shared_strings: tuple[str, ...]
) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return _normalize_inline_text(
            "".join(
                node.text or ""
                for node in cell.iter(f"{{{_SHEET_NAMESPACE}}}t")
            )
        )
    value_node = cell.find(f"{{{_SHEET_NAMESPACE}}}v")
    value = "" if value_node is None else value_node.text or ""
    if cell_type == "s":
        try:
            index = int(value)
            if index < 0:
                raise ValueError("negative shared-string index")
            return shared_strings[index]
        except (ValueError, IndexError) as error:
            raise _CorruptInput("invalid_xlsx_shared_string_index") from error
    return _normalize_inline_text(value)


def _safe_xml_root(xml_bytes: bytes, detail_code: str) -> ElementTree.Element:
    try:
        return SafeElementTree.fromstring(
            xml_bytes,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except DefusedXmlException as error:
        raise _CorruptInput("unsafe_office_xml_declaration") from error
    except ElementTree.ParseError as error:
        raise _CorruptInput(detail_code) from error


def _word_text(element: ElementTree.Element) -> str:
    values = [
        node.text or ""
        for node in element.iter(f"{{{_WORD_NAMESPACE}}}t")
    ]
    return _normalize_inline_text("".join(values))


def _normalize_inline_text(value: str) -> str:
    return re.sub(r"[\t\r\n ]+", " ", value).strip()


def _xml_local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _normalize_extracted_text(value: str) -> str:
    lines = [_normalize_inline_text(line) for line in value.splitlines()]
    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        if line:
            normalized.append(line)
            previous_blank = False
        elif normalized and not previous_blank:
            normalized.append("")
            previous_blank = True
    return "\n".join(normalized).strip()


def _sanitize_warning_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    sanitized = {
        code if code in _SAFE_ADAPTER_WARNINGS else "adapter_warning_redacted"
        for code in codes
    }
    return tuple(sorted(sanitized))


def _signature_error(content: bytes, media_type: str) -> str | None:
    if media_type == PDF_MEDIA_TYPE and not content.startswith(b"%PDF-"):
        return "media_signature_mismatch"
    if media_type in {DOCX_MEDIA_TYPE, XLSX_MEDIA_TYPE} and not content.startswith(
        b"PK"
    ):
        return "media_signature_mismatch"
    if media_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "media_signature_mismatch"
    if media_type == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"):
        return "media_signature_mismatch"
    if media_type == "image/tiff" and not content.startswith(
        (b"II*\x00", b"MM\x00*")
    ):
        return "media_signature_mismatch"
    return None


def _safe_version(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("source_version must be str")
    if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value):
        return value
    return "source_version_redacted"


def _parser_id(media_type: str) -> str:
    if media_type in PLAIN_MEDIA_TYPES:
        return "builtin-text-v1"
    if media_type == HTML_MEDIA_TYPE:
        return "builtin-html-v2"
    if media_type == XHTML_MEDIA_TYPE:
        return "builtin-xhtml-xml-v1"
    if media_type in TABLE_MEDIA_TYPES:
        return "builtin-delimited-table-v1"
    if media_type == DOCX_MEDIA_TYPE:
        return "builtin-docx-xml-v1"
    if media_type == XLSX_MEDIA_TYPE:
        return "builtin-xlsx-xml-v1"
    if media_type == PDF_MEDIA_TYPE:
        return "external-pdf-adapter-v1"
    if media_type in OCR_MEDIA_TYPES:
        return "external-ocr-adapter-v1"
    return "none"


def _failure(
    status: ParseStatus,
    media_type: str,
    parser_id: str,
    detail_code: str,
    fingerprint: str,
    input_bytes: int,
    *,
    adapter_used: bool = False,
    metrics: _ExtractionMetrics | None = None,
    source_version: str = "not_provided",
    source_locator_fingerprint: str = "",
    expected_marker_count: int = 0,
) -> ParseResult:
    extracted = metrics or _ExtractionMetrics("")
    return ParseResult(
        report=ParseQualityReport(
            status=status,
            media_type=media_type,
            parser_id=parser_id,
            parser_version="1.0",
            source_version=source_version,
            source_locator_fingerprint=source_locator_fingerprint,
            detail_code=detail_code,
            content_fingerprint=fingerprint,
            raw_sha256=fingerprint,
            parsed_sha256=None,
            input_bytes=input_bytes,
            output_chars=0,
            block_count=extracted.block_count,
            table_count=extracted.table_count,
            row_count=extracted.row_count,
            page_count=extracted.page_count,
            table_cell_count=extracted.table_cell_count,
            archive_entry_count=extracted.archive_entry_count,
            archive_uncompressed_bytes=extracted.archive_uncompressed_bytes,
            expected_marker_count=expected_marker_count,
            observed_marker_count=0,
            marker_recall=None,
            warning_codes=extracted.warning_codes,
            adapter_used=adapter_used,
        )
    )
