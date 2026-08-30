"""
Fylorra - PDF Tools (built-in)
Pure-Python PDF operations using pypdf (no external apps required).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfOpResult:
    ok: bool
    message: str
    output_paths: list[str] | None = None


def _require_pypdf():
    try:
        from pypdf import PdfReader, PdfWriter  # noqa: F401

        return PdfReader, PdfWriter
    except Exception as e:
        raise RuntimeError("PDF tools require 'pypdf'. Install: pip install pypdf") from e


def _safe_filename(name: str, *, max_len: int = 120) -> str:
    name = (name or "").strip()
    if not name:
        return "untitled"
    bad = '<>:"/\\|?*'
    for ch in bad:
        name = name.replace(ch, "_")
    name = " ".join(name.split())
    return name[:max_len].rstrip(" ._")


def _parse_page_ranges(spec: str, *, max_pages: int) -> list[int]:
    """
    Parse '1-3,5,7-9' into 0-based page indices.
    """
    spec = (spec or "").strip()
    if not spec or spec.lower() in {"all", "*"}:
        return list(range(max_pages))

    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a_str, b_str = part.split("-", 1)
            a = int(a_str.strip())
            b = int(b_str.strip())
            if a <= 0 or b <= 0:
                continue
            lo, hi = (a, b) if a <= b else (b, a)
            for p in range(lo, hi + 1):
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
        else:
            p = int(part)
            if 1 <= p <= max_pages:
                pages.add(p - 1)
    return sorted(pages)


def merge_pdfs(pdf_paths: list[Path], *, output_pdf: Path, overwrite: bool = False) -> PdfOpResult:
    PdfReader, PdfWriter = _require_pypdf()

    output_pdf = Path(output_pdf)
    if output_pdf.exists() and not overwrite:
        return PdfOpResult(ok=False, message=f"Output already exists: {output_pdf.name}")

    writer = PdfWriter()
    added_files = 0
    added_pages = 0
    for p in pdf_paths:
        p = Path(p)
        if not p.exists() or not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        try:
            reader = PdfReader(str(p))
        except Exception:
            continue
        for page in reader.pages:
            writer.add_page(page)
            added_pages += 1
        added_files += 1

    if added_files == 0 or added_pages == 0:
        return PdfOpResult(ok=False, message="No PDFs to merge.")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)
    return PdfOpResult(ok=True, message=f"Merged {added_files} PDFs ({added_pages} pages).", output_paths=[str(output_pdf)])


def list_pdf_bookmarks(input_pdf: Path) -> list[dict[str, int | str]]:
    """
    Returns a flat list of bookmarks: [{title, page_index}, ...]
    """
    PdfReader, _ = _require_pypdf()
    input_pdf = Path(input_pdf)
    if not input_pdf.exists():
        return []

    try:
        reader = PdfReader(str(input_pdf))
    except Exception:
        return []

    outline = getattr(reader, "outline", None)
    if not outline:
        return []

    def page_index_for(item) -> int | None:
        try:
            if hasattr(reader, "get_destination_page_number"):
                return int(reader.get_destination_page_number(item))
        except Exception:
            return None
        return None

    items: list[tuple[str, int]] = []

    def walk(node):
        if isinstance(node, list):
            for x in node:
                walk(x)
            return
        title = None
        try:
            title = getattr(node, "title", None) or getattr(node, "Title", None)
        except Exception:
            title = None
        idx = page_index_for(node)
        if title and idx is not None and idx >= 0:
            items.append((str(title), int(idx)))

    walk(outline)
    items.sort(key=lambda t: t[1])

    dedup: list[dict[str, int | str]] = []
    seen = set()
    for title, idx in items:
        key = (title, idx)
        if key in seen:
            continue
        seen.add(key)
        dedup.append({"title": title, "page_index": idx})
    return dedup


def split_pdf_to_pages(
    input_pdf: Path,
    *,
    output_dir: Path,
    overwrite: bool = False,
    page_ranges: str = "all",
) -> PdfOpResult:
    PdfReader, PdfWriter = _require_pypdf()

    input_pdf = Path(input_pdf)
    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")

    reader = PdfReader(str(input_pdf))
    indices = _parse_page_ranges(page_ranges, max_pages=len(reader.pages))
    if not indices:
        return PdfOpResult(ok=False, message="No matching pages to split.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[str] = []
    for idx in indices:
        out_path = output_dir / f"{input_pdf.stem}_page_{idx + 1}.pdf"
        if out_path.exists() and not overwrite:
            continue
        writer = PdfWriter()
        writer.add_page(reader.pages[idx])
        with out_path.open("wb") as f:
            writer.write(f)
        outputs.append(str(out_path))

    return PdfOpResult(ok=True, message=f"Split {len(outputs)} pages.", output_paths=outputs)


def extract_pages_to_pdf(
    input_pdf: Path,
    *,
    output_pdf: Path,
    page_ranges: str = "all",
    overwrite: bool = False,
) -> PdfOpResult:
    """
    Extract a subset of pages into a new PDF (keeps them together).
    """
    PdfReader, PdfWriter = _require_pypdf()
    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)

    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")
    if output_pdf.exists() and not overwrite:
        return PdfOpResult(ok=False, message=f"Output already exists: {output_pdf.name}")

    reader = PdfReader(str(input_pdf))
    indices = _parse_page_ranges(page_ranges, max_pages=len(reader.pages))
    if not indices:
        return PdfOpResult(ok=False, message="No matching pages.")

    writer = PdfWriter()
    for idx in indices:
        writer.add_page(reader.pages[idx])

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)
    return PdfOpResult(ok=True, message=f"Extracted {len(indices)} pages.", output_paths=[str(output_pdf)])


def split_pdf_into_chunks(
    input_pdf: Path,
    *,
    output_dir: Path,
    pages_per_file: int = 10,
    overwrite: bool = False,
) -> PdfOpResult:
    """
    Split a PDF into multiple PDFs, each containing N pages.
    """
    PdfReader, PdfWriter = _require_pypdf()
    input_pdf = Path(input_pdf)
    output_dir = Path(output_dir)

    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")
    pages_per_file = int(pages_per_file)
    if pages_per_file <= 0:
        return PdfOpResult(ok=False, message="pages_per_file must be > 0.")

    reader = PdfReader(str(input_pdf))
    total = len(reader.pages)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[str] = []
    part = 1
    for start in range(0, total, pages_per_file):
        end = min(total, start + pages_per_file)
        out_path = output_dir / f"{input_pdf.stem}_part_{part}.pdf"
        if out_path.exists() and not overwrite:
            part += 1
            continue
        writer = PdfWriter()
        for idx in range(start, end):
            writer.add_page(reader.pages[idx])
        with out_path.open("wb") as f:
            writer.write(f)
        outputs.append(str(out_path))
        part += 1

    return PdfOpResult(ok=True, message=f"Split into {len(outputs)} files.", output_paths=outputs)


def split_pdf_by_bookmarks(
    input_pdf: Path,
    *,
    output_dir: Path,
    overwrite: bool = False,
    min_pages: int = 1,
) -> PdfOpResult:
    """
    Split a PDF into separate PDFs based on top-level bookmarks.
    If there are no bookmarks, returns ok=False.
    """
    PdfReader, PdfWriter = _require_pypdf()
    input_pdf = Path(input_pdf)
    output_dir = Path(output_dir)
    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")

    bookmarks = list_pdf_bookmarks(input_pdf)
    if not bookmarks:
        return PdfOpResult(ok=False, message="No bookmarks found in PDF.")

    try:
        reader = PdfReader(str(input_pdf))
    except Exception:
        return PdfOpResult(ok=False, message="Failed to read PDF.")

    starts = []
    for bm in bookmarks:
        try:
            starts.append((str(bm["title"]), int(bm["page_index"])))
        except Exception:
            continue
    starts = [(t, p) for t, p in starts if p >= 0]
    starts.sort(key=lambda x: x[1])

    # Dedup by page_index keeping first title
    dedup_starts: list[tuple[str, int]] = []
    seen_pages = set()
    for t, p in starts:
        if p in seen_pages:
            continue
        seen_pages.add(p)
        dedup_starts.append((t, p))
    starts = dedup_starts

    total_pages = len(reader.pages)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[str] = []
    used_names: dict[str, int] = {}
    min_pages = max(1, int(min_pages))

    for i, (title, start_idx) in enumerate(starts):
        end_idx = starts[i + 1][1] if i + 1 < len(starts) else total_pages
        if end_idx <= start_idx:
            continue
        if (end_idx - start_idx) < min_pages:
            continue

        base = _safe_filename(title)
        count = used_names.get(base, 0) + 1
        used_names[base] = count
        name = f"{base}.pdf" if count == 1 else f"{base}_{count}.pdf"
        out_path = output_dir / name
        if out_path.exists() and not overwrite:
            continue

        writer = PdfWriter()
        for idx in range(start_idx, end_idx):
            writer.add_page(reader.pages[idx])
        with out_path.open("wb") as f:
            writer.write(f)
        outputs.append(str(out_path))

    if not outputs:
        return PdfOpResult(ok=False, message="No outputs created (maybe overwrite=false or tiny sections).")
    return PdfOpResult(ok=True, message=f"Split into {len(outputs)} bookmark files.", output_paths=outputs)


def rotate_pdf(
    input_pdf: Path,
    *,
    output_pdf: Path,
    rotation_degrees: int = 90,
    page_ranges: str = "all",
    overwrite: bool = False,
) -> PdfOpResult:
    PdfReader, PdfWriter = _require_pypdf()

    rotation_degrees = int(rotation_degrees)
    if rotation_degrees % 90 != 0:
        return PdfOpResult(ok=False, message="Rotation must be a multiple of 90 degrees.")

    input_pdf = Path(input_pdf)
    if not input_pdf.exists():
        return PdfOpResult(ok=False, message="Input PDF not found.")

    output_pdf = Path(output_pdf)
    if output_pdf.exists() and not overwrite:
        return PdfOpResult(ok=False, message=f"Output already exists: {output_pdf.name}")

    reader = PdfReader(str(input_pdf))
    indices = set(_parse_page_ranges(page_ranges, max_pages=len(reader.pages)))

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in indices:
            try:
                page = page.rotate(rotation_degrees)
            except Exception:
                page.rotate_clockwise(rotation_degrees)
        writer.add_page(page)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)

    return PdfOpResult(ok=True, message="Rotation complete.", output_paths=[str(output_pdf)])


def extract_pdf_text(
    input_pdf: Path,
    *,
    max_pages: int = 20,
    max_chars: int = 150_000,
) -> str:
    """
    Best-effort text extraction using pypdf.
    """
    PdfReader, _ = _require_pypdf()

    input_pdf = Path(input_pdf)
    if not input_pdf.exists():
        return ""

    try:
        reader = PdfReader(str(input_pdf))
    except Exception:
        return ""

    parts: list[str] = []
    for i, page in enumerate(reader.pages[: max(0, int(max_pages))]):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            parts.append(text)
        if sum(len(p) for p in parts) >= max_chars:
            break

    out = "\n".join(parts).strip()
    return out[:max_chars]
