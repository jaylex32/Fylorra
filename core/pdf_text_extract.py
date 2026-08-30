"""
Fylorra - PDF Text Extraction
Used as a fallback when LibreOffice export produces empty text outputs.
"""

from __future__ import annotations

from pathlib import Path


def extract_pdf_text(pdf_path: Path) -> str:
    pdf_path = Path(pdf_path)
    pages: list[str] = []

    # Prefer PyMuPDF (best extraction quality).
    try:
        import fitz  # type: ignore

        with fitz.open(pdf_path) as pdf:
            for i in range(len(pdf)):
                pages.append(pdf[i].get_text("text") or "")
        text = "\n\n".join(pages).strip()
        return text
    except Exception:
        pass

    # Fallback: pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        text = "\n\n".join(pages).strip()
        return text
    except Exception:
        return ""


def pdf_to_txt(pdf_path: Path, *, output_path: Path) -> Path:
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = extract_pdf_text(pdf_path)
    if not text.strip():
        text = "[No extractable text found in this PDF. If this is a scanned PDF, enable OCR indexing/search or use an OCR tool.]"
    output_path.write_text(text, encoding="utf-8", errors="replace")
    return output_path

