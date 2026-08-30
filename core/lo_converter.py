"""
Fylorra - LibreOffice Converter
Office conversion via headless LibreOffice (soffice).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import re
import os

from core.tool_manager import ToolManager


class LibreOfficeConverter:
    """
    Converts office files using LibreOffice headless.

    Supported formats depend on LibreOffice.
    """

    def __init__(self, soffice_path: Optional[str] = None):
        self._tools = ToolManager()
        self.soffice_path = soffice_path or self._tools.soffice_path()

    def is_available(self) -> bool:
        return bool(self.soffice_path) and Path(self.soffice_path).exists()

    def convert_to_pdf(self, input_path: Path, *, out_dir: Path) -> Optional[Path]:
        input_path = Path(input_path)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not self.is_available():
            return None

        # LibreOffice writes output to out_dir with same basename.
        cmd = [
            str(self.soffice_path),
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--nodefault",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(input_path),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        except Exception:
            return None

        out_pdf = out_dir / (input_path.stem + ".pdf")
        if out_pdf.exists():
            return out_pdf
        return None

    def convert_to_format(self, input_path: Path, *, out_dir: Path, output_format: str) -> Optional[Path]:
        """
        Convert an input document to the given output format (e.g. pdf, docx, odt, xlsx, ods, csv, pptx, odp, txt, html).
        Returns the output path if created.
        """
        input_path = Path(input_path)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not self.is_available():
            return None

        fmt = (output_format or "").strip().lower().lstrip(".")
        if not fmt:
            return None

        out_path, _ = self.convert_to_format_verbose(input_path, out_dir=out_dir, output_format=fmt)
        return out_path

    def convert_to_format_verbose(self, input_path: Path, *, out_dir: Path, output_format: str) -> tuple[Optional[Path], Optional[str]]:
        """
        Same as convert_to_format, but returns (output_path, error_message).
        """
        input_path = Path(input_path)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not self.is_available():
            return None, "LibreOffice (soffice) not available."

        fmt = (output_format or "").strip().lower().lstrip(".")
        if not fmt:
            return None, "Missing output format."

        convert_to = fmt
        # Improve DOCX export stability for LO by specifying a filter name.
        if fmt == "docx":
            convert_to = 'docx:"MS Word 2007 XML"'
        elif fmt == "xlsx":
            convert_to = 'xlsx:"Calc MS Excel 2007 XML"'
        elif fmt == "pptx":
            convert_to = 'pptx:"Impress MS PowerPoint 2007 XML"'

        # For PDF input, hint the import filter when exporting to text/doc formats.
        cmd = [
            str(self.soffice_path),
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--nodefault",
            "--norestore",
        ]
        if input_path.suffix.lower() == ".pdf" and fmt in {"docx", "odt", "txt", "html"}:
            cmd.append('--infilter=writer_pdf_import')

        cmd += [
            "--convert-to",
            convert_to,
            "--outdir",
            str(out_dir),
            str(input_path),
        ]

        # LibreOffice embeds its own Python and can break if the parent process has PYTHONHOME/PYTHONPATH set.
        env = dict(os.environ)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONNOUSERSITE", None)

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                env=env,
            )
        except Exception as e:
            return None, str(e)

        # Some LO builds may return 0 even if conversion failed; check filesystem.
        expected = out_dir / (input_path.stem + "." + fmt)
        if expected.exists():
            return expected, None

        # Best-effort: return first file matching the stem.
        try:
            matches = sorted(out_dir.glob(input_path.stem + ".*"), key=lambda p: p.stat().st_mtime, reverse=True)
            for m in matches[:8]:
                if m.is_file():
                    return m, None
        except Exception:
            pass

        err = (proc.stderr or "") + "\n" + (proc.stdout or "")
        err = err.strip()
        if not err:
            err = f"LibreOffice failed (exit code {proc.returncode})."
        # Trim and clean noise a bit
        err = re.sub(r"\s+", " ", err)[:600]
        return None, err
