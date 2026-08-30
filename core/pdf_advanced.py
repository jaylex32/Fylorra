"""
Fylorra - Advanced PDF Operations
Higher-level PDF editing utilities (pure Python).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.pdf_tools import PdfOpResult, _parse_page_ranges


def _require_pypdf():
    try:
        from pypdf import PdfReader, PdfWriter  # noqa: F401

        return PdfReader, PdfWriter
    except Exception as e:
        raise RuntimeError("PDF tools require 'pypdf'. Install: pip install pypdf") from e


@dataclass(frozen=True)
class PdfSearchHit:
    page_number: int  # 1-based
    snippet: str


def remove_pages(
    input_pdf: Path,
    *,
    output_pdf: Path,
    remove_ranges: str,
    overwrite: bool = False,
) -> PdfOpResult:
    PdfReader, PdfWriter = _require_pypdf()

    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")
    if output_pdf.exists() and not overwrite:
        return PdfOpResult(ok=False, message=f"Output already exists: {output_pdf.name}")

    reader = PdfReader(str(input_pdf))
    total = len(reader.pages)
    to_remove = set(_parse_page_ranges(remove_ranges, max_pages=total))
    if not to_remove:
        return PdfOpResult(ok=False, message="No pages specified for removal.")

    writer = PdfWriter()
    kept = 0
    for i in range(total):
        if i in to_remove:
            continue
        writer.add_page(reader.pages[i])
        kept += 1

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)
    return PdfOpResult(ok=True, message=f"Removed {len(to_remove)} pages (kept {kept}).", output_paths=[str(output_pdf)])


def reorder_pages(
    input_pdf: Path,
    *,
    output_pdf: Path,
    order: list[int],
    overwrite: bool = False,
) -> PdfOpResult:
    """
    Reorder pages by explicit 1-based page numbers, e.g. [2,1,3].
    """
    PdfReader, PdfWriter = _require_pypdf()

    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")
    if output_pdf.exists() and not overwrite:
        return PdfOpResult(ok=False, message=f"Output already exists: {output_pdf.name}")

    reader = PdfReader(str(input_pdf))
    total = len(reader.pages)
    if not order:
        return PdfOpResult(ok=False, message="order is empty.")

    indices: list[int] = []
    for p in order:
        try:
            p = int(p)
        except Exception:
            continue
        if 1 <= p <= total:
            indices.append(p - 1)

    if len(indices) != len(order):
        return PdfOpResult(ok=False, message="Invalid page numbers in order.")

    writer = PdfWriter()
    for idx in indices:
        writer.add_page(reader.pages[idx])

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)
    return PdfOpResult(ok=True, message="Reordered pages.", output_paths=[str(output_pdf)])


def search_pdf_text(
    input_pdf: Path,
    *,
    query: str,
    max_hits: int = 50,
    case_sensitive: bool = False,
) -> list[PdfSearchHit]:
    """
    Best-effort PDF text search using pypdf's text extraction.
    Returns page numbers + short snippets (no highlighting).
    """
    from core.pdf_tools import extract_pdf_text

    input_pdf = Path(input_pdf)
    if not input_pdf.exists():
        return []

    q = (query or "").strip()
    if not q:
        return []

    try:
        PdfReader, _ = _require_pypdf()
        reader = PdfReader(str(input_pdf))
    except Exception:
        return []

    hits: list[PdfSearchHit] = []
    q_cmp = q if case_sensitive else q.lower()

    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if not text:
            continue

        hay = text if case_sensitive else text.lower()
        pos = hay.find(q_cmp)
        if pos < 0:
            continue

        start = max(0, pos - 40)
        end = min(len(text), pos + len(q) + 80)
        snippet = text[start:end].replace("\n", " ").strip()
        hits.append(PdfSearchHit(page_number=i + 1, snippet=snippet))
        if len(hits) >= int(max_hits):
            break

    return hits


def add_text_watermark(
    input_pdf: Path,
    *,
    output_pdf: Path,
    text: str,
    overwrite: bool = False,
    opacity: float = 0.15,
    font_size: int = 44,
    rotate_degrees: int = 30,
) -> PdfOpResult:
    """
    Add a simple diagonal text watermark to each page.
    Requires 'reportlab' (pure Python).
    """
    PdfReader, PdfWriter = _require_pypdf()

    try:
        from reportlab.lib.colors import Color
        from reportlab.pdfgen import canvas
    except Exception as e:
        raise RuntimeError("Watermark requires 'reportlab'. Install: pip install reportlab") from e

    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")
    if output_pdf.exists() and not overwrite:
        return PdfOpResult(ok=False, message=f"Output already exists: {output_pdf.name}")

    text = (text or "").strip()
    if not text:
        return PdfOpResult(ok=False, message="Watermark text is empty.")

    opacity = float(opacity)
    opacity = max(0.02, min(0.6, opacity))
    font_size = int(font_size)
    rotate_degrees = int(rotate_degrees)

    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()

    # Create per-page overlay PDFs in-memory to match page size.
    import io

    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)

        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=(w, h))
        c.saveState()
        c.translate(w / 2, h / 2)
        c.rotate(rotate_degrees)
        c.setFillColor(Color(0, 0, 0, alpha=opacity))
        c.setFont("Helvetica", font_size)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.showPage()
        c.save()
        packet.seek(0)

        overlay_reader = PdfReader(packet)
        overlay_page = overlay_reader.pages[0]
        try:
            page.merge_page(overlay_page)
        except Exception:
            try:
                page.mergePage(overlay_page)  # older API fallback
            except Exception:
                pass
        writer.add_page(page)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)
    return PdfOpResult(ok=True, message="Watermark applied.", output_paths=[str(output_pdf)])

