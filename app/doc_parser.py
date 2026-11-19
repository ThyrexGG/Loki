"""Local, offline text extraction for .pdf and .docx files (zero network calls).

Used both when a user drops/attaches a .pdf or .docx in Chat (ephemeral, never saved to disk)
and when a folder containing .pdf or .docx files is indexed in the Local Document Indexer.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

MAX_DOC_BYTES = 16 * 1024 * 1024  # 16 MB cap for binary .pdf / .docx files
MAX_DOCX_XML_BYTES = 25 * 1024 * 1024  # zip-bomb guard on uncompressed XML


class DocumentParseError(Exception):
    """Raised when a .pdf or .docx cannot be parsed locally."""


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _extract_paragraph_text(p_elem: ET.Element) -> str:
    parts: list[str] = []
    for node in p_elem.iter():
        t = _local_tag(node.tag)
        if t == "t" and node.text:
            parts.append(node.text)
        elif t == "tab":
            parts.append("\t")
        elif t in ("br", "cr"):
            parts.append("\n")
    return "".join(parts).strip()


def extract_docx_bytes(raw: bytes, max_chars: int = 200_000) -> dict[str, Any]:
    """Extract readable paragraphs and Markdown-style table rows from a .docx archive."""
    if not raw:
        raise DocumentParseError("The .docx file is empty.")
    if len(raw) > MAX_DOC_BYTES:
        raise DocumentParseError("The .docx file exceeds the 16 MB local size limit.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile as exc:
        raise DocumentParseError("Not a valid .docx archive.") from exc

    with zf:
        if "word/document.xml" not in zf.namelist():
            raise DocumentParseError("Missing word/document.xml inside .docx file.")
        info = zf.getinfo("word/document.xml")
        if info.file_size > MAX_DOCX_XML_BYTES:
            raise DocumentParseError("Uncompressed .docx XML exceeds safety limit.")
        xml_bytes = zf.read("word/document.xml")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DocumentParseError("Could not parse .docx XML structure.") from exc

    body = next((el for el in root if _local_tag(el.tag) == "body"), root)
    blocks: list[str] = []
    para_count = 0
    table_count = 0

    for child in body:
        ctag = _local_tag(child.tag)
        if ctag == "p":
            txt = _extract_paragraph_text(child)
            if txt:
                blocks.append(txt)
                para_count += 1
        elif ctag == "tbl":
            table_rows: list[str] = []
            for row in child:
                if _local_tag(row.tag) != "tr":
                    continue
                cells: list[str] = []
                for cell in row:
                    if _local_tag(cell.tag) != "tc":
                        continue
                    cell_paras = [
                        _extract_paragraph_text(p)
                        for p in cell
                        if _local_tag(p.tag) == "p"
                    ]
                    cells.append(" ".join(x for x in cell_paras if x).replace("|", "\\|"))
                if any(cells):
                    table_rows.append("| " + " | ".join(cells) + " |")
            if table_rows:
                blocks.append("\n".join(table_rows))
                table_count += 1

    full_text = "\n\n".join(blocks).strip()
    if not full_text:
        raise DocumentParseError("No readable text was found inside this .docx file.")
    truncated = len(full_text) > max_chars
    if truncated:
        full_text = full_text[:max_chars] + "\n\n... [document truncated to fit context budget]"
    lines = len(full_text.splitlines())
    return {
        "text": full_text,
        "lines": lines,
        "pages": None,
        "paragraphs": para_count,
        "tables": table_count,
        "truncated": truncated,
        "summary_label": f"{lines} line{'s' if lines != 1 else ''}",
    }


def extract_pdf_bytes(raw: bytes, max_pages: int = 150, max_chars: int = 200_000) -> dict[str, Any]:
    """Extract text page-by-page from a .pdf file using pypdf (100% offline)."""
    if not raw:
        raise DocumentParseError("The PDF file is empty.")
    if len(raw) > MAX_DOC_BYTES:
        raise DocumentParseError("The PDF file exceeds the 16 MB local size limit.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParseError("Local PDF reader (pypdf) is not installed.") from exc

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:
        raise DocumentParseError(f"Could not read PDF structure: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise DocumentParseError("This PDF is password-protected and cannot be read.") from exc

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise DocumentParseError("This PDF has 0 pages.")

    page_blocks: list[str] = []
    used_chars = 0
    truncated = total_pages > max_pages
    limit = min(total_pages, max_pages)

    for idx in range(limit):
        try:
            page_txt = (reader.pages[idx].extract_text() or "").strip()
        except Exception:
            page_txt = ""
        if not page_txt:
            continue
        block = f"--- Page {idx + 1} of {total_pages} ---\n{page_txt}"
        if used_chars + len(block) > max_chars:
            remain = max(0, max_chars - used_chars)
            if remain > 120:
                page_blocks.append(block[:remain] + "\n... [PDF text truncated to fit context budget]")
            truncated = True
            break
        page_blocks.append(block)
        used_chars += len(block) + 2

    full_text = "\n\n".join(page_blocks).strip()
    if not full_text:
        raise DocumentParseError(
            "This PDF appears to be a scanned image with no selectable text. "
            "Use the screenshot button or paste a page image so Loki's vision model (Qwen3-VL) can read it."
        )
    lines = len(full_text.splitlines())
    return {
        "text": full_text,
        "lines": lines,
        "pages": total_pages,
        "truncated": truncated,
        "summary_label": f"{total_pages} page{'s' if total_pages != 1 else ''} · {lines} lines",
    }


def extract_document_bytes(filename: str, raw: bytes, max_chars: int = 96_000) -> dict[str, Any]:
    """Extract text from a .pdf or .docx byte buffer by filename extension."""
    low = (filename or "").strip().lower()
    if low.endswith(".pdf"):
        return extract_pdf_bytes(raw, max_chars=max_chars)
    if low.endswith(".docx"):
        return extract_docx_bytes(raw, max_chars=max_chars)
    raise DocumentParseError(f"Unsupported binary document type for '{filename}'. Expected .pdf or .docx.")


def read_file_for_index(path: Path, max_text_bytes: int = 2 * 1024 * 1024) -> str | None:
    """Read an indexable file from disk, supporting plain text/code as well as .pdf and .docx."""
    ext = path.suffix.lower()
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None
    if ext in (".pdf", ".docx"):
        if size > MAX_DOC_BYTES:
            return None
        try:
            raw = path.read_bytes()
            res = extract_document_bytes(path.name, raw, max_chars=300_000)
            return res["text"]
        except Exception:
            return None
    if size > max_text_bytes:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
