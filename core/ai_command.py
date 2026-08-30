"""
Fylorra - AI Command Planner/Executor
Turns natural language into a safe, previewable multi-step local workflow.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.image_converter import convert_images_in_folder
from core.library_index import LibraryIndex
from core.lo_converter import LibreOfficeConverter
from core.media_converter import convert_media_in_folder
from core.media_tools import convert_media_file, cut_video_segment
from core.office_tools import xlsx_to_csv
from core.file_ops import copy_files, delete_files, make_subfolder, move_files
from core.audio_tag_organizer import organize_audio_by_tags
from core.pdf_tools import (
    extract_pages_to_pdf,
    merge_pdfs,
    rotate_pdf,
    split_pdf_by_bookmarks,
    split_pdf_into_chunks,
    split_pdf_to_pages,
)
from core.pdf_advanced import add_text_watermark, remove_pages, reorder_pages, search_pdf_text
from core.zip_tools import unzip_archive, zip_folder


@dataclass(frozen=True)
class CommandStep:
    tool: str
    args: dict[str, Any]
    description: str
    destructive: bool = False


@dataclass(frozen=True)
class CommandPlan:
    intent_summary: str
    steps: list[CommandStep]


ALLOWED_TOOLS = {
    "index_folder",
    "search_index",
    "convert_office_to_pdf",
    "zip_folder",
    "unzip_archive",
    "convert_images",
    "convert_media",
    "convert_media_file",
    "cut_video",
    "convert_excel_to_csv",
    "merge_pdfs",
    "extract_pdf_pages",
    "split_pdf_pages",
    "split_pdf_chunks",
    "split_pdf_bookmarks",
    "rotate_pdf",
    "remove_pdf_pages",
    "reorder_pdf_pages",
    "watermark_pdf",
    "search_pdf_text",
    "make_folder",
    "move_files",
    "copy_files",
    "delete_files",
    "organize_audio_by_tags",
    "smart_rename",
    "auto_categorize",
    "security_scan",
    "content_analysis",
}


def _strip_wrappers(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    # Remove common wrappers (code fences, tool-call tags)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = text.replace("<tool_call>", "").replace("</tool_call>", "")
    text = text.replace("<tool_response>", "").replace("</tool_response>", "")
    text = text.replace("<tools>", "").replace("</tools>", "")
    return text.strip()


def _extract_first_json_object(text: str) -> str | None:
    """
    Extract the first balanced {...} JSON object from text, honoring strings/escapes.
    """
    text = _strip_wrappers(text)
    if not text:
        return None

    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """
    Robust JSON extraction: supports markdown fences, tool-call wrappers,
    and falls back to Python literal parsing when the model returns single quotes.
    """
    text = _strip_wrappers(text)
    if not text:
        return None

    # Try direct JSON first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"intent_summary": "AI plan", "steps": obj}
    except Exception:
        pass

    # Try first balanced object
    candidate = _extract_first_json_object(text)
    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            # Fallback: python literal dict (single quotes, etc.)
            try:
                import ast

                obj = ast.literal_eval(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

    # Last-resort: try to parse a steps list if present
    try:
        import ast

        obj = ast.literal_eval(text)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"intent_summary": "AI plan", "steps": obj}
    except Exception:
        return None

    return None


def _heuristic_plan(instruction: str) -> Optional[CommandPlan]:
    """
    If the model returns non-JSON, generate a best-effort plan for common tasks.
    This prevents the UI from failing hard while keeping plans safe.
    """
    raw = (instruction or "").strip()
    if not raw:
        return None

    text = raw.lower()

    def _extract_output_folder_name(s: str) -> str | None:
        # Examples: "to a folder named MP3 Music", "into folder MP3 Music", "move ... to folder MP3 Music"
        patterns = [
            r"\bfolder\s+named\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\bto\s+(?:a\s+)?folder\s+named\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\bto\s+(?:a\s+)?folder\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\binto\s+(?:a\s+)?folder\s+named\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\binto\s+(?:a\s+)?folder\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
        ]
        for pat in patterns:
            m = re.search(pat, s, flags=re.IGNORECASE)
            if m:
                name = m.group(1).strip().strip("\"'")
                # Clean trailing conjunctions
                name = re.split(r"\s+\band\b\s+|\s+\bthen\b\s+", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                return name[:80] if name else None
        return None

    def _extract_source_subfolder(s: str) -> str | None:
        # Examples: "in Deezer", "inside Deezer folder", "in folder Deezer"
        patterns = [
            r"\bin\s+folder\s+named\s+(.+?)(?:\s+to\b|\s+into\b|\s+and\b|$)",
            r"\bin\s+folder\s+(.+?)(?:\s+to\b|\s+into\b|\s+and\b|$)",
            r"\binside\s+folder\s+named\s+(.+?)(?:\s+to\b|\s+into\b|\s+and\b|$)",
            r"\binside\s+folder\s+(.+?)(?:\s+to\b|\s+into\b|\s+and\b|$)",
            r"\bin\s+(.+?)(?:\s+folder\b|\s+directory\b|\s+to\b|\s+into\b|\s+and\b|$)",
        ]
        for pat in patterns:
            m = re.search(pat, s, flags=re.IGNORECASE)
            if m:
                name = m.group(1).strip().strip("\"'")
                name = re.split(r"\s+\band\b\s+|\s+\bthen\b\s+", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                # Use just the last path segment if a path was provided.
                name = Path(name).name
                return name[:80] if name else None
        return None

    # convert X to Y
    m = re.search(r"\bconvert\s+(.+?)\s+\bto\b\s+(.+)$", raw, flags=re.IGNORECASE)
    if m:
        src = m.group(1).strip().strip("\"'")
        dst = m.group(2).strip().strip("\"'")
        src_ext = Path(src).suffix.lower()
        dst_ext = Path(dst).suffix.lower()

        media_exts = {
            ".mp4",
            ".mkv",
            ".mov",
            ".avi",
            ".webm",
            ".mp3",
            ".wav",
            ".m4a",
            ".aac",
            ".flac",
            ".ogg",
        }
        if src_ext in media_exts or dst_ext in media_exts:
            return CommandPlan(
                intent_summary=f"Convert {Path(src).name} -> {Path(dst).name}",
                steps=[
                    CommandStep(
                        tool="convert_media_file",
                        args={"input_path": src, "output_name": dst, "overwrite": False, "audio_bitrate": "192k" if dst_ext == ".mp3" else None},
                        description="Convert media file",
                        destructive=False,
                    )
                ],
            )

        if src_ext in {".xlsx", ".xlsm", ".xltx", ".xltm"} and dst_ext == ".csv":
            return CommandPlan(
                intent_summary=f"Convert {Path(src).name} -> {Path(dst).name}",
                steps=[
                    CommandStep(
                        tool="convert_excel_to_csv",
                        args={"input_path": src, "output_name": dst, "overwrite": False},
                        description="Convert Excel to CSV",
                        destructive=False,
                    )
                ],
            )

    # Bulk conversion in folder: "convert all tracks/files in the folder to mp3 ..."
    if "convert" in text and ("all" in text or "tracks" in text or "files" in text) and ("folder" in text or "directory" in text):
        fmt = _extract_convert_format(raw)
        dest = _extract_output_folder_name(raw)
        src_sub = _extract_source_subfolder(raw)
        bitrate = None
        mrate = re.search(r"\b(\d{2,3})\s*(?:kbps|k)\b", raw, flags=re.IGNORECASE)
        if mrate:
            bitrate = f"{mrate.group(1)}k"
        # If destination not provided but request implies it, use a sensible default
        if fmt in {"mp3", "wav", "m4a", "aac", "flac", "ogg", "mp4", "mkv", "mov", "avi", "webm"}:
            out_sub = dest or ("MP3 Music" if fmt == "mp3" else "Converted_Media")
            input_exts = None
            if "track" in text or "audio" in text or fmt in {"mp3", "wav", "m4a", "aac", "flac", "ogg"}:
                input_exts = ["mp3", "wav", "m4a", "aac", "flac", "ogg"]
            return CommandPlan(
                intent_summary=f"Convert folder media to {fmt}" + (f" into {out_sub}" if out_sub else ""),
                steps=[
                    CommandStep(
                        tool="convert_media",
                        args={
                            "source_subfolder": src_sub,
                            "include_subfolders": True,
                            "output_format": fmt,
                            "output_subfolder": out_sub,
                            # Default: user expects the destination folder at the selected Target Folder root
                            "output_root": "target",
                            # If a subfolder is specified, keep its name under the output folder to avoid collisions.
                            "preserve_structure": bool(src_sub),
                            "overwrite": False,
                            "audio_bitrate": bitrate,
                            "input_extensions": input_exts,
                            "preserve_cover_art": True,
                        },
                        description="Convert media in folder",
                        destructive=False,
                    )
                ],
            )
        if fmt in {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}:
            out_sub = dest or "Converted_Images"
            return CommandPlan(
                intent_summary=f"Convert folder images to {fmt}" + (f" into {out_sub}" if out_sub else ""),
                steps=[
                    CommandStep(
                        tool="convert_images",
                        args={"include_subfolders": True, "output_format": fmt, "output_subfolder": out_sub, "overwrite": False},
                        description="Convert images in folder",
                        destructive=False,
                    )
                ],
            )

    # Move/copy files by extension into a named folder.
    m = re.search(
        r"\b(move|copy)\b\s+(?:all\s+)?(?:the\s+)?([a-z0-9]{2,6})\s+(?:files|tracks|photos|documents)\s+.*?\bto\b.*?\bfolder\b(?:\s+named)?\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        verb = m.group(1).lower()
        ext = m.group(2).lower()
        dest = m.group(3).strip().strip("\"'")
        tool = "move_files" if verb == "move" else "copy_files"
        return CommandPlan(
            intent_summary=f"{verb.title()} *.{ext} into {dest}",
            steps=[
                CommandStep(
                    tool=tool,
                    args={"dest_subfolder": dest, "include_subfolders": True, "selector": {"extensions": [ext]}, "overwrite": False},
                    description=f"{verb.title()} files",
                    destructive=True,
                )
            ],
        )

    # Delete files by extension (safe delete).
    m = re.search(r"\bdelete\b\s+(?:all\s+)?([a-z0-9]{2,6})\s+files\b", raw, flags=re.IGNORECASE)
    if m:
        ext = m.group(1).lower()
        return CommandPlan(
            intent_summary=f"Delete *.{ext} files",
            steps=[
                CommandStep(
                    tool="delete_files",
                    args={"include_subfolders": True, "selector": {"extensions": [ext]}},
                    description="Delete files safely",
                    destructive=True,
                )
            ],
        )

    # cut video patterns: "cut X at 3:47 for 00:00:30" / "cut X from 3:47 to 4:10"
    m = re.search(r"\bcut\s+(.+?)\s+\b(from|at)\b\s+([0-9:.]+)\s+(?:\bto\b\s+([0-9:.]+)|\bfor\b\s+([0-9:.]+))", raw, flags=re.IGNORECASE)
    if m:
        src = m.group(1).strip().strip("\"'")
        start = m.group(3).strip()
        end = (m.group(4) or "").strip() or None
        duration = (m.group(5) or "").strip() or None
        out_name = Path(src).stem + "_clip" + (Path(src).suffix or ".mp4")
        return CommandPlan(
            intent_summary=f"Cut {Path(src).name}",
            steps=[
                CommandStep(
                    tool="cut_video",
                    args={"input_path": src, "start": start, "end": end, "duration": duration, "output_name": out_name, "overwrite": False, "reencode": False},
                    description="Cut video segment",
                    destructive=False,
                )
            ],
        )

    # PDF: split by bookmarks
    m = re.search(r"\bsplit\s+(.+?\.pdf)\s+\bby\b\s+\bbookmarks\b", raw, flags=re.IGNORECASE)
    if m:
        src = m.group(1).strip().strip("\"'")
        return CommandPlan(
            intent_summary=f"Split {Path(src).name} by bookmarks",
            steps=[
                CommandStep(
                    tool="split_pdf_bookmarks",
                    args={"input_pdf": src, "output_subfolder": "Split_By_Bookmarks", "overwrite": False, "min_pages": 1},
                    description="Split PDF by bookmarks",
                    destructive=False,
                )
            ],
        )

    return None


def plan_from_nl(ai_manager, instruction: str, *, target_folder: Path, allowed_tools: set[str] | None = None) -> CommandPlan:
    """
    Use the local model to produce a constrained JSON plan with allowed tools only.
    """
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("Instruction is empty.")

    allowed = set(allowed_tools or ALLOWED_TOOLS)
    if not allowed:
        raise ValueError("allowed_tools is empty.")

    def _fallback_or_error(reason: str) -> CommandPlan:
        fallback = _heuristic_plan(instruction)
        if fallback:
            steps = [s for s in _sanitize_steps(list(fallback.steps), instruction) if s.tool in allowed]
            if steps:
                return CommandPlan(intent_summary=fallback.intent_summary, steps=steps)
        raise RuntimeError(reason)

    if not ai_manager or not getattr(ai_manager, "is_ready", False) or not getattr(ai_manager, "model", None):
        return _fallback_or_error(
            "AI model is not ready and this command is not covered by the built-in planner."
        )

    schema = {
        "intent_summary": "string",
        "steps": [
            {
                "tool": f"one of: {sorted(allowed)}",
                "args": "object",
                "description": "string",
                "destructive": "boolean",
            }
        ],
    }

    tools_doc = [
        {
            "tool": "index_folder",
            "args": {
                "include_subfolders": True,
                "include_hidden": False,
                "ai_summarize": False,
                "extract_images": False,
                "compute_hashes": False,
                "max_files": 0,
                "include_extensions": [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"],
                "ocr_scanned_pdfs": False,
                "ocr_pdf_pages": 1,
                "max_pdf_ocr_files": 60,
            },
            "description": "Index the target folder for AI Search (extracts text from PDFs/office where possible).",
            "destructive": False,
        },
        {
            "tool": "search_index",
            "args": {"query": "string", "limit": 50},
            "description": "Search the local index for matching files.",
            "destructive": False,
        },
        {
            "tool": "convert_office_to_pdf",
            "args": {
                "include_subfolders": True,
                "output_mode": "subfolder",
                "output_subfolder": "Converted_PDF",
                "overwrite": False,
            },
            "description": "Convert DOCX/XLSX/PPTX to PDF using LibreOffice headless.",
            "destructive": False,
        },
        {
            "tool": "zip_folder",
            "args": {
                "folder_rel": "optional subfolder under target to zip (e.g. MP3/Album)",
                "include_subfolders": True,
                "output_zip_name": "Archive.zip",
                "overwrite": False,
            },
            "description": "Create a ZIP archive from the target folder (or a subfolder).",
            "destructive": False,
        },
        {
            "tool": "unzip_archive",
            "args": {
                "archive_path": "Archive.zip (relative under target folder)",
                "output_subfolder": "Extracted",
                "overwrite": False,
            },
            "description": "Extract a ZIP archive into a subfolder inside the target folder.",
            "destructive": False,
        },
        {
            "tool": "convert_images",
            "args": {
                "include_subfolders": True,
                "output_format": "png",
                "output_subfolder": "Converted_Images",
                "overwrite": False,
            },
            "description": "Convert images in the target folder to another format (PNG/JPG/WEBP/etc).",
            "destructive": False,
        },
        {
            "tool": "convert_media",
            "args": {
                "source_subfolder": "Deezer (optional)",
                "include_subfolders": True,
                "output_format": "mp4",
                "output_subfolder": "Converted_Media",
                "output_root": "target (or source)",
                "preserve_structure": True,
                "overwrite": False,
                "audio_bitrate": "320k (optional, audio only)",
                "audio_bitrate_mode": "cbr (optional for mp3)",
                "preserve_cover_art": True,
                "video_codec": "h264/h265/vp9 (optional)",
                "scale_height": "720/1080/2160 (optional)",
                "use_gpu": "true to prefer NVENC (optional)",
            },
            "description": "Convert videos/audio using ffmpeg if available (can be bundled).",
            "destructive": False,
        },
        {
            "tool": "convert_media_file",
            "args": {
                "input_path": "relative under target folder (or absolute)",
                "output_name": "example.mp3",
                "overwrite": False,
                "audio_bitrate": "192k (optional)",
            },
            "description": "Convert one media file (e.g. FLAC→MP3) using ffmpeg (via imageio-ffmpeg).",
            "destructive": False,
        },
        {
            "tool": "cut_video",
            "args": {
                "input_path": "relative under target folder (or absolute)",
                "start": "3:47",
                "end": "4:10 (optional)",
                "duration": "00:00:30 (optional)",
                "output_name": "clip.mp4",
                "overwrite": False,
                "reencode": False,
            },
            "description": "Cut a video segment starting at a timecode; uses stream copy unless reencode=true.",
            "destructive": False,
        },
        {
            "tool": "convert_excel_to_csv",
            "args": {
                "input_path": "relative under target folder (or absolute)",
                "output_name": "example.csv",
                "sheet": "Sheet1 (optional)",
                "overwrite": False,
            },
            "description": "Convert an Excel file to CSV using openpyxl (pure Python).",
            "destructive": False,
        },
        {
            "tool": "merge_pdfs",
            "args": {
                "include_subfolders": False,
                "output_pdf_name": "Merged.pdf",
                "overwrite": False,
            },
            "description": "Merge PDFs found in the target folder into a single PDF.",
            "destructive": False,
        },
        {
            "tool": "extract_pdf_pages",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "page_ranges": "all or 1-3,5,7-9",
                "output_pdf_name": "Extracted.pdf",
                "overwrite": False,
            },
            "description": "Extract selected pages from a PDF into a new PDF.",
            "destructive": False,
        },
        {
            "tool": "split_pdf_pages",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "page_ranges": "all or 1-3,5,7-9",
                "output_subfolder": "Split_Pages",
                "overwrite": False,
            },
            "description": "Split a PDF into individual page PDFs (optionally by page ranges).",
            "destructive": False,
        },
        {
            "tool": "split_pdf_chunks",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "pages_per_file": 10,
                "output_subfolder": "Split_Chunks",
                "overwrite": False,
            },
            "description": "Split a PDF into multiple PDFs, each containing N pages.",
            "destructive": False,
        },
        {
            "tool": "split_pdf_bookmarks",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "output_subfolder": "Split_By_Bookmarks",
                "overwrite": False,
                "min_pages": 1,
            },
            "description": "Split a PDF into multiple PDFs based on its bookmarks.",
            "destructive": False,
        },
        {
            "tool": "rotate_pdf",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "rotation_degrees": 90,
                "page_ranges": "all or 1-3,5",
                "output_pdf_name": "Rotated.pdf",
                "overwrite": False,
            },
            "description": "Rotate pages in a PDF and save as a new PDF.",
            "destructive": False,
        },
        {
            "tool": "remove_pdf_pages",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "remove_ranges": "2,5-7",
                "output_pdf_name": "RemovedPages.pdf",
                "overwrite": False,
            },
            "description": "Remove pages by range from a PDF and save as a new PDF.",
            "destructive": False,
        },
        {
            "tool": "reorder_pdf_pages",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "order": [2, 1, 3],
                "output_pdf_name": "Reordered.pdf",
                "overwrite": False,
            },
            "description": "Reorder pages by explicit 1-based page list.",
            "destructive": False,
        },
        {
            "tool": "watermark_pdf",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "text": "CONFIDENTIAL",
                "output_pdf_name": "Watermarked.pdf",
                "opacity": 0.15,
                "font_size": 44,
                "rotate_degrees": 30,
                "overwrite": False,
            },
            "description": "Add a text watermark to each page (requires reportlab).",
            "destructive": False,
        },
        {
            "tool": "search_pdf_text",
            "args": {
                "input_pdf": "file.pdf (relative under target folder)",
                "query": "invoice",
                "max_hits": 50,
                "case_sensitive": False,
            },
            "description": "Search for text in a PDF and return matching page numbers/snippets.",
            "destructive": False,
        },
        {
            "tool": "make_folder",
            "args": {"subfolder": "MP3 Music"},
            "description": "Create a folder under target_folder.",
            "destructive": False,
        },
        {
            "tool": "move_files",
            "args": {
                "dest_subfolder": "MP3 Music",
                "include_subfolders": True,
                "selector": {"extensions": ["mp3"]},
                "overwrite": False,
            },
            "description": "Move matching files into a subfolder under target_folder.",
            "destructive": True,
        },
        {
            "tool": "copy_files",
            "args": {
                "dest_subfolder": "Backups",
                "include_subfolders": True,
                "selector": {"glob": "*.pdf"},
                "overwrite": False,
            },
            "description": "Copy matching files into a subfolder under target_folder.",
            "destructive": True,
        },
        {
            "tool": "delete_files",
            "args": {
                "include_subfolders": True,
                "selector": {"extensions": ["tmp", "log"]},
            },
            "description": "Delete matching files safely (Recycle Bin if available, else move to .fylorra_trash).",
            "destructive": True,
        },
        {
            "tool": "organize_audio_by_tags",
            "args": {
                "source_subfolder": "MP3 Music (optional)",
                "dest_subfolder": "Organized_Music",
                "include_subfolders": True,
                "overwrite": False,
            },
            "description": "Organize audio into Artist/Album folders using tags (mutagen).",
            "destructive": True,
        },
        {
            "tool": "smart_rename",
            "args": {},
            "description": "AI-powered bulk rename with preview and undo.",
            "destructive": True,
        },
        {
            "tool": "auto_categorize",
            "args": {},
            "description": "Auto-categorize into folders (with preview/undo).",
            "destructive": True,
        },
        {
            "tool": "security_scan",
            "args": {},
            "description": "Scan images for sensitive information.",
            "destructive": False,
        },
        {
            "tool": "content_analysis",
            "args": {},
            "description": "Bulk content analysis for documents.",
            "destructive": False,
        },
    ]

    filtered_tools_doc = [t for t in tools_doc if isinstance(t, dict) and t.get("tool") in allowed]

    prompt = (
        "You are an assistant that plans local file workflows for an office file management app.\n"
        "Return JSON only (no markdown, no code fences).\n"
        "Use double quotes for all strings. Do not use trailing commas.\n"
        "Rules:\n"
        f"- Allowed tools: {sorted(allowed)}\n"
        "- Use as few steps as possible.\n"
        "- Never invent paths outside target_folder.\n"
        "- Prefer safe defaults (overwrite=false).\n"
        "- intent_summary must describe the USER'S goal (not 'convert to JSON').\n"
        "- If a request is impossible with the allowed tools, still return a plan that does the closest safe thing.\n\n"
        f"target_folder: {str(target_folder)}\n\n"
        f"Schema: {json.dumps(schema)}\n\n"
        f"Tools: {json.dumps(filtered_tools_doc)}\n\n"
        "Important tool constraints:\n"
        "- convert_media is for BULK conversion within the folder.\n"
        "- convert_media_file is ONLY for a single file path (relative or absolute), never for 'all files'.\n"
        "- If user says 'all tracks/files in folder', use convert_media.\n\n"
        f"User instruction: {instruction}\n"
    )

    try:
        resp = ai_manager.model.create_chat_completion(
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            temperature=0.2,
            max_tokens=600,
        )
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return _fallback_or_error("AI planning failed and no built-in planner matched the request.")
    data = _extract_json(content)
    if not data:
        # Attempt a "repair" pass: ask the model to convert its last response to strict JSON.
        repair_prompt = (
            "Your previous response did not follow the required JSON format.\n"
            "Now output ONLY a valid JSON plan that matches the schema.\n"
            "Rules:\n"
            "- Output JSON only (no markdown, no code fences).\n"
            "- Use double quotes for all strings.\n"
            "- The JSON must be an object with keys: intent_summary, steps.\n"
            f"- Allowed tools: {sorted(allowed)}\n\n"
            "- intent_summary must describe the USER request (not 'convert to JSON').\n"
            f"target_folder: {str(target_folder)}\n\n"
            f"Schema: {json.dumps(schema)}\n\n"
            f"User instruction: {instruction}\n\n"
            f"Text to convert:\n{content}\n"
        )
        try:
            resp2 = ai_manager.model.create_chat_completion(
                messages=[{"role": "user", "content": [{"type": "text", "text": repair_prompt}]}],
                temperature=0.1,
                max_tokens=500,
            )
            content2 = resp2["choices"][0]["message"]["content"]
            data = _extract_json(content2)
        except Exception:
            data = None

    if not data:
        # Heuristic fallback for common commands
        return _fallback_or_error("Failed to parse AI plan JSON.")

    intent_summary = str(data.get("intent_summary") or "").strip() or "AI plan"
    # Guardrail: sometimes the model uses the repair prompt meta-task as the "intent".
    if re.search(r"\b(valid\s+json|schema|convert\s+the\s+given\s+text|json\s+structure)\b", intent_summary, flags=re.IGNORECASE):
        intent_summary = instruction.strip().replace("\n", " ")
        if len(intent_summary) > 140:
            intent_summary = intent_summary[:137].rstrip() + "..."
    steps_raw = data.get("steps") or []
    if not isinstance(steps_raw, list):
        raise RuntimeError("Invalid plan format (steps).")

    steps: list[CommandStep] = []
    for s in steps_raw:
        if not isinstance(s, dict):
            continue
        tool = str(s.get("tool") or "").strip()
        if tool not in allowed:
            continue
        args = s.get("args") if isinstance(s.get("args"), dict) else {}
        description = str(s.get("description") or tool)
        destructive = bool(s.get("destructive") or False)
        steps.append(CommandStep(tool=tool, args=args, description=description, destructive=destructive))

    if not steps:
        # Fallback: safest first tool (prefer indexing if available)
        if "index_folder" in allowed:
            steps = [
                CommandStep(
                    tool="index_folder",
                    args={"include_subfolders": True, "include_hidden": False},
                    description="Index folder",
                    destructive=False,
                )
            ]
        else:
            any_tool = sorted(allowed)[0]
            steps = [CommandStep(tool=any_tool, args={}, description=any_tool, destructive=False)]

    steps = _sanitize_steps(steps, instruction)

    return CommandPlan(intent_summary=intent_summary, steps=steps)


def _looks_like_single_file_path(value: str) -> bool:
    v = (value or "").strip().strip("\"'")
    if not v:
        return False
    # If it ends with an extension, treat as file path (relative or absolute)
    if Path(v).suffix:
        return True
    return False


def _safe_relpath(value: str) -> str | None:
    """
    Normalize a user/model-provided relative path.

    - Allows nested paths like "MP3/Album"
    - Rejects absolute paths and parent traversal.
    """
    v = (value or "").strip().strip("\"'")
    if not v:
        return None
    v = v.replace("\\", "/").strip()
    # Trim common punctuation the model often leaves at the end of clauses.
    v = v.strip(" \t\r\n,.;:")
    while v.startswith("/"):
        v = v[1:]
    if not v:
        return None
    p = Path(v)
    if p.is_absolute() or ".." in p.parts:
        return None
    # Avoid extremely long paths coming from model rambling.
    return p.as_posix()[:160]


def _extract_convert_format(text: str) -> str | None:
    """
    Extract desired output format from natural language.

    Examples: "to mp3", "into mp4", "as webp", "convert ... to .mp3".
    """
    s = (text or "").strip()
    if not s:
        return None

    # normalize common punctuation
    s2 = s.replace("\\", "/")

    # "to .mp3" / "to mp3"
    m = re.search(r"(?:\bto\b|\binto\b|\bas\b)\s+\.?([a-z0-9]{2,6})\b", s2, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()

    # "mp3 320kbps" (implicit)
    m = re.search(r"\b(mp3|wav|m4a|flac|aac|ogg|opus|mp4|mkv|avi|mov|webm|pdf|png|jpg|jpeg|webp)\b", s2, flags=re.IGNORECASE)
    if m:
        fmt = m.group(1).lower()
        return "jpg" if fmt == "jpeg" else fmt

    return None


def _sanitize_steps(steps: list[CommandStep], instruction: str) -> list[CommandStep]:
    """
    Fix common model mistakes (e.g. using convert_media_file for bulk conversion).
    """
    inst = (instruction or "")
    inst_l = inst.lower()

    def extract_bitrate() -> str | None:
        m = re.search(r"\b(\d{2,3})\s*(?:kbps|k)\b", inst, flags=re.IGNORECASE)
        return f"{m.group(1)}k" if m else None

    def extract_resolution_height() -> int | None:
        m = re.search(r"\b(480|720|1080|1440|2160)\s*p\b", inst, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
        if "4k" in inst_l:
            return 2160
        return None

    def extract_video_codec() -> str | None:
        if any(k in inst_l for k in ["h.265", "h265", "hevc", "x265"]):
            return "h265"
        if any(k in inst_l for k in ["h.264", "h264", "avc", "x264"]):
            return "h264"
        if "vp9" in inst_l:
            return "vp9"
        return None

    def wants_gpu() -> bool:
        return any(k in inst_l for k in ["gpu", "nvenc", "cuda"])

    def extract_time_range() -> tuple[str | None, str | None, str | None]:
        # Supports: from 1:23 to 1:41, between 1:23 and 1:41, at 1:23 for 0:20
        m = re.search(r"\b(from|between)\s+([0-9:.]+)\s+(?:to|and)\s+([0-9:.]+)\b", inst, flags=re.IGNORECASE)
        if m:
            return m.group(2).strip(), m.group(3).strip(), None
        m = re.search(r"\bat\s+([0-9:.]+)\s+\bfor\b\s+([0-9:.]+)\b", inst, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(), None, m.group(2).strip()
        return None, None, None

    def extract_output_name() -> str | None:
        # "into X.mp3" / "to X.mp3" / "save as X.mp3"
        pats = [
            r"\binto\s+([^\s]+?\.[a-z0-9]{2,5})\b",
            r"\bto\s+([^\s]+?\.[a-z0-9]{2,5})\b",
            r"\bsave\s+as\s+([^\s]+?\.[a-z0-9]{2,5})\b",
        ]
        for pat in pats:
            m = re.search(pat, inst, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip().strip("\"'")
        return None

    def extract_media_filename() -> str | None:
        # Best-effort: find the first filename-like span ending in a known media extension.
        # We intentionally support unicode dashes commonly found in track names.
        exts = r"(mp3|wav|m4a|flac|aac|ogg|opus|mp4|mkv|avi|mov|webm)"

        def allowed_char(ch: str) -> bool:
            if ch.isalnum():
                return True
            return ch in " _-–—.()[]{}'&+/,\\\""

        m2 = re.search(rf"\.(?:{exts})\b", inst, flags=re.IGNORECASE)
        if not m2:
            return None
        end = m2.end()
        i = m2.start() - 1
        while i >= 0 and allowed_char(inst[i]):
            i -= 1
        start = i + 1
        cand = inst[start:end].strip().strip(" ,.;:")
        cand = cand.strip("\"'")
        return cand or None

    def extract_source_subfolder() -> str | None:
        # Use last path segment if a folder/path is mentioned.
        patterns = [
            r"\bin\s+folder\s+named\s+(.+?)(?:\s+to\b|\s+into\b|\s+and\b|$)",
            r"\bin\s+folder\s+(.+?)(?:\s+to\b|\s+into\b|\s+and\b|$)",
            r"\binside\s+folder\s+(.+?)(?:\s+to\b|\s+into\b|\s+and\b|$)",
            r"\bin\s+(.+?)(?:\s+folder\b|\s+directory\b|\s+to\b|\s+into\b|\s+and\b|$)",
        ]
        for pat in patterns:
            m = re.search(pat, inst, flags=re.IGNORECASE)
            if m:
                name = m.group(1).strip().strip("\"'")
                rel = _safe_relpath(name)
                if not rel:
                    # fall back to last segment when user provided something path-like but invalid
                    rel = Path(name).name
                return rel[:160] if rel else None
        return None

    def extract_output_subfolder() -> str | None:
        patterns = [
            r"\bfolder\s+named\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\binto\s+(?:a\s+)?folder\s+named\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\binto\s+(?:a\s+)?folder\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\bto\s+(?:a\s+)?folder\s+named\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
            r"\bto\s+(?:a\s+)?folder\s+(.+?)(?:\s+\band\b|\s+\bthen\b|$)",
        ]
        for pat in patterns:
            m = re.search(pat, inst, flags=re.IGNORECASE)
            if m:
                name = m.group(1).strip().strip("\"'")
                name = re.split(r"\s+\band\b\s+|\s+\bthen\b\s+", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                rel = _safe_relpath(name)
                if rel:
                    return rel
                # fallback: last segment
                last = Path(name).name
                return last[:80] if last else None
        return None

    out: list[CommandStep] = []
    inferred_src = extract_source_subfolder()
    inferred_out = extract_output_subfolder()
    wants_zip = "zip" in inst_l or "archive" in inst_l
    wants_invoices = any(k in inst_l for k in ["invoice", "invoices", "receipt", "statement", "bill"])
    wants_cut = "cut" in inst_l or "ringtone" in inst_l or "clip" in inst_l
    src_media = extract_media_filename()
    desired_out_name = extract_output_name()

    for s in steps:
        # Don't allow broad destructive ops unless explicitly requested.
        if s.tool in {"move_files", "copy_files"} and "move" not in inst_l and "copy" not in inst_l and "transfer" not in inst_l:
            continue
        if s.tool == "delete_files" and "delete" not in inst_l and "remove" not in inst_l:
            continue

        # Ensure bitrate is not dropped for bulk conversions when requested.
        if s.tool == "convert_media":
            # Guardrail: if the user asked to cut a segment, convert_media is the wrong tool.
            if wants_cut:
                start, end, duration = extract_time_range()
                if start and (end or duration):
                    q = src_media
                    if not q:
                        m = re.search(
                            r"\b(track|song|audio)\b\s+([^\n\r]+?)(?:\s+\bfrom\b|\s+\bbetween\b|\s+\bat\b|\s+\bcut\b|$)",
                            inst,
                            flags=re.IGNORECASE,
                        )
                        if m:
                            q = m.group(2).strip().strip("\"'")
                    # If nothing obvious, fall back to output stem as a hint.
                    if not q and desired_out_name:
                        q = Path(desired_out_name).stem
                    q = q or "input"

                    bitrate = extract_bitrate()
                    cut_args = {
                        "input_path": q,
                        "start": start,
                        "end": end,
                        "duration": duration,
                        "output_name": desired_out_name
                        or (f"{Path(q).stem}_clip.mp3" if ("mp3" in inst_l or "ringtone" in inst_l) else f"{Path(q).stem}_clip"),
                        "overwrite": bool((s.args or {}).get("overwrite", False)),
                        "reencode": True if (desired_out_name and desired_out_name.lower().endswith(".mp3")) or "ringtone" in inst_l else False,
                    }
                    if bitrate:
                        cut_args["audio_bitrate"] = bitrate
                    out.append(CommandStep(tool="cut_video", args=cut_args, description="Cut segment", destructive=False))
                    continue

            args = dict(s.args or {})
            fmt = str(args.get("output_format") or "").lower().strip()
            bitrate = extract_bitrate()
            desired_out = extract_output_subfolder()
            desired_src = extract_source_subfolder()
            res_h = extract_resolution_height()
            vcodec = extract_video_codec()

            # If user said "audio", constrain to audio types to avoid converting everything.
            if ("audio" in inst_l or "track" in inst_l or "songs" in inst_l) and not args.get("input_extensions"):
                args["input_extensions"] = ["wav", "m4a", "aac", "flac", "ogg", "wma", "mp3"]
            if "video" in inst_l and not args.get("input_extensions"):
                args["input_extensions"] = ["mp4", "mkv", "avi", "mov", "webm", "wmv", "m4v"]

            if fmt == "mp3" and bitrate and not args.get("audio_bitrate"):
                args["audio_bitrate"] = bitrate
            if fmt == "mp3" and args.get("audio_bitrate") and not args.get("audio_bitrate_mode"):
                args["audio_bitrate_mode"] = "cbr"
            if args.get("preserve_cover_art") is None:
                args["preserve_cover_art"] = True

            if res_h and not args.get("scale_height"):
                args["scale_height"] = int(res_h)
            if vcodec and not args.get("video_codec"):
                args["video_codec"] = vcodec
            if wants_gpu() and "use_gpu" not in args:
                args["use_gpu"] = True

            # If user clearly mentions a source subfolder, enforce it (avoid converting the whole target).
            if desired_src:
                current_src = str(args.get("source_subfolder") or "").strip()
                if not current_src or current_src.lower() != desired_src.lower():
                    args["source_subfolder"] = desired_src

            # If user did not explicitly ask to put output inside the source subfolder, default output_root=target.
            out_root = str(args.get("output_root") or "").strip().lower()
            if not out_root:
                out_root = "target"
            # Guardrail: unless user explicitly requests "same folder"/"source", keep outputs in target.
            if out_root == "source" and not any(k in inst_l for k in ["same folder", "same directory", "source folder", "next to", "beside"]):
                out_root = "target"
            args["output_root"] = out_root
            # If user specified output folder name, honor it (model often defaults to Converted_Media).
            if desired_out:
                current_out = str(args.get("output_subfolder") or "").strip()
                if not current_out or current_out.lower() != desired_out.lower():
                    args["output_subfolder"] = desired_out
            # If we have a source_subfolder and output_root is target, default preserve_structure=true to avoid collisions.
            if args.get("source_subfolder") and str(args.get("output_root")).lower() == "target" and "preserve_structure" not in args:
                args["preserve_structure"] = True
            out.append(CommandStep(tool=s.tool, args=args, description=s.description, destructive=s.destructive))
            continue

        if s.tool == "index_folder":
            args = dict(s.args or {})
            if "include_subfolders" not in args:
                args["include_subfolders"] = True
            if "include_hidden" not in args:
                args["include_hidden"] = False
            # Default to document-focused indexing (fast + relevant).
            if not args.get("include_extensions"):
                args["include_extensions"] = [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"]
            # For invoice-like queries, OCR scanned PDFs is crucial; keep it capped.
            if wants_invoices:
                args["ocr_scanned_pdfs"] = bool(args.get("ocr_scanned_pdfs", True))
                args["ocr_pdf_pages"] = int(args.get("ocr_pdf_pages") or 1)
                args["max_pdf_ocr_files"] = int(args.get("max_pdf_ocr_files") or 60)
                # AI summaries improve semantic matching; keep it capped.
                args["ai_summarize"] = bool(args.get("ai_summarize", True))
                args["max_ai_files"] = int(args.get("max_ai_files") or 80)
            # Never compute hashes during search indexing unless explicitly asked.
            if "hash" not in inst_l and "dedupe" not in inst_l and "duplicate" not in inst_l:
                args["compute_hashes"] = False
            out.append(CommandStep(tool=s.tool, args=args, description=s.description, destructive=s.destructive))
            continue

        if s.tool == "cut_video":
            args = dict(s.args or {})
            start, end, duration = extract_time_range()
            if start and not args.get("start"):
                args["start"] = start
            if end and not args.get("end"):
                args["end"] = end
            if duration and not args.get("duration"):
                args["duration"] = duration
            out_name = extract_output_name()
            if out_name:
                args["output_name"] = out_name
            if args.get("input_path"):
                args["input_path"] = _clean_media_query(str(args.get("input_path") or ""))
            # Ensure we never pass both end and duration (ffmpeg tool rejects it).
            if args.get("end") and args.get("duration"):
                if " to " in inst_l or "between" in inst_l:
                    args.pop("duration", None)
                else:
                    args.pop("end", None)
            # If the model mistakenly uses the output as the input, prefer the source media from the instruction.
            if src_media:
                inp = str(args.get("input_path") or "").strip()
                outn = str(args.get("output_name") or "").strip()
                if inp.lower() in {"input", "file", "track", "song", "audio"}:
                    args["input_path"] = src_media
                if inp and outn and inp.lower() == outn.lower():
                    args["input_path"] = src_media
                if not inp:
                    args["input_path"] = src_media
            if (args.get("output_name") or "").lower().endswith(".mp3") or "ringtone" in inst_l:
                args["reencode"] = True
                br = extract_bitrate()
                if br and not args.get("audio_bitrate"):
                    args["audio_bitrate"] = br
            out.append(CommandStep(tool=s.tool, args=args, description=s.description, destructive=s.destructive))
            continue

        if s.tool == "convert_media_file":
            # If the user intent is cutting a segment, a separate convert step is unnecessary and often wrong.
            if wants_cut:
                continue
            args = dict(s.args or {})
            inp = str(args.get("input_path") or "").strip()
            if inp and not _looks_like_single_file_path(inp):
                # try extracting a real filename from the instruction
                token = extract_media_filename()
                if token:
                    args["input_path"] = token
            out.append(CommandStep(tool=s.tool, args=args, description=s.description, destructive=s.destructive))
            continue

        if s.tool == "convert_images":
            args = dict(s.args or {})
            desired_fmt = _extract_convert_format(inst)  # webp/png/jpg...
            if desired_fmt and desired_fmt in {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}:
                args["output_format"] = "jpg" if desired_fmt == "jpeg" else desired_fmt
            if inferred_out:
                args["output_subfolder"] = inferred_out
            if "include_subfolders" not in args:
                args["include_subfolders"] = True
            if "overwrite" not in args:
                args["overwrite"] = False
            out.append(CommandStep(tool=s.tool, args=args, description=s.description, destructive=s.destructive))
            continue

        if s.tool == "zip_folder":
            args = dict(s.args or {})
            # If user says "zip the folder" after conversion, zip the inferred output folder instead of the entire target.
            if not args.get("folder_rel"):
                folder_rel = inferred_out or inferred_src
                if folder_rel:
                    args["folder_rel"] = folder_rel

            # If no explicit zip name, derive a stable name from the folder being zipped.
            if not str(args.get("output_zip_name") or "").strip():
                base = Path(str(args.get("folder_rel") or "Archive")).name or "Archive"
                args["output_zip_name"] = f"{base}.zip"

            out.append(CommandStep(tool=s.tool, args=args, description=s.description, destructive=s.destructive))
            continue

        if s.tool == "convert_media_file":
            inp = str((s.args or {}).get("input_path") or "").strip()
            out_name = str((s.args or {}).get("output_name") or "").strip()
            bulk_words = any(w in inp.lower() for w in ["all ", "files", "tracks", "folder"]) or "all" in inst_l
            if (bulk_words and not _looks_like_single_file_path(inp)) or (inp and not _looks_like_single_file_path(inp)):
                fmt = Path(out_name).suffix.lower().lstrip(".") if out_name and Path(out_name).suffix else None
                if not fmt:
                    fmt = _extract_convert_format(inst) or ("mp3" if "mp3" in inst_l else "mp4")
                dest = None
                if "folder named" in inst_l or "into folder" in inst_l or "to folder" in inst_l:
                    dest = re.search(r"\bfolder\s+(?:named\s+)?(.+)$", inst, flags=re.IGNORECASE)
                    dest = dest.group(1).strip() if dest else None
                out_sub = dest or ("MP3 Music" if fmt == "mp3" else "Converted_Media")
                bitrate = extract_bitrate()
                input_exts = ["mp3", "wav", "m4a", "aac", "flac", "ogg"] if ("track" in inst_l or "audio" in inst_l or fmt in {"mp3", "wav", "m4a", "aac", "flac", "ogg"}) else None
                out.append(
                    CommandStep(
                        tool="convert_media",
                        args={
                            "include_subfolders": True,
                            "output_format": fmt,
                            "output_subfolder": out_sub,
                            "overwrite": bool((s.args or {}).get("overwrite", False)),
                            "audio_bitrate": bitrate,
                            "input_extensions": input_exts,
                        },
                        description="Convert media in folder",
                        destructive=False,
                    )
                )
                continue

        out.append(s)

    # If the user asked to zip but the model omitted it, add a safe zip step.
    if wants_zip and not any(step.tool == "zip_folder" for step in out):
        folder_rel = inferred_out or inferred_src
        args: dict[str, Any] = {"include_subfolders": True, "overwrite": False}
        if folder_rel:
            args["folder_rel"] = folder_rel
            base = (Path(folder_rel).name or "Archive").strip(" ,.;:")
            args["output_zip_name"] = f"{base}.zip"
        else:
            args["output_zip_name"] = "Archive.zip"
        out.append(CommandStep(tool="zip_folder", args=args, description="Create a ZIP archive", destructive=False))

    # If the user asked to cut but the model omitted it, add a safe cut step.
    if wants_cut and not any(step.tool == "cut_video" for step in out):
        start, end, duration = extract_time_range()
        if start and (end or duration):
            cut_args = {
                "input_path": src_media or "input",
                "start": start,
                "end": end,
                "duration": duration,
                "output_name": desired_out_name or "clip.mp3",
                "overwrite": False,
                "reencode": True,
            }
            br = extract_bitrate()
            if br:
                cut_args["audio_bitrate"] = br
            out.append(CommandStep(tool="cut_video", args=cut_args, description="Cut segment", destructive=False))

    return out


def _resolve_under_target(target_folder: Path, rel_path: str) -> Path | None:
    rel_path = (rel_path or "").strip().strip("\"'")
    if not rel_path:
        return None
    p = Path(target_folder) / rel_path
    try:
        p.resolve().relative_to(Path(target_folder).resolve())
        return p
    except Exception:
        return None


def _resolve_any_path(target_folder: Path, value: str) -> Path | None:
    value = (value or "").strip().strip("\"'")
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return p
    return _resolve_under_target(target_folder, value)


def _fuzzy_find_under_target(target_folder: Path, query: str, *, exts: set[str]) -> Path | None:
    """
    Find a file by partial name under the target folder (case-insensitive).
    Useful for prompts like "cut track DtMF ..." without a full filename.
    """
    q = (query or "").strip().strip("\"'")
    if not q:
        return None

    def norm(s: str) -> str:
        s = (s or "").lower()
        s = s.replace("–", "-").replace("—", "-").replace("_", " ")
        s = " ".join(s.split())
        return s.strip()

    ql = norm(q)
    candidates: list[Path] = []
    for p in Path(target_folder).glob("**/*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        name = norm(p.name)
        stem = norm(p.stem)
        if ql == stem or ql == name:
            return p
        if ql and (ql in name or ql in stem):
            candidates.append(p)
    if not candidates:
        return None
    # prefer shortest (usually the closest match), then stable by path
    candidates.sort(key=lambda x: (len(x.name), str(x).lower()))
    return candidates[0]


def _clean_media_query(text: str) -> str:
    """
    Non-destructively clean common prompt prefixes (e.g. 'grab track ...').
    Keeps the original filename if present.
    """
    s = (text or "").strip().strip("\"'")
    if not s:
        return ""
    s = s.strip(" ,.;:")
    # If it contains a filename, prefer extracting that.
    try:
        m = re.search(r"\.[A-Za-z0-9]{2,5}\b", s)
        if m:
            # try to extract full filename span near extension
            ext_end = m.end()
            i = m.start() - 1
            while i >= 0 and (s[i].isalnum() or s[i] in " _-–—.()[]{}'&+/,\\\""):
                i -= 1
            cand = s[i + 1 : ext_end].strip().strip(" ,.;:").strip("\"'")
            if cand:
                s = cand
    except Exception:
        pass

    # Strip leading verbs/nouns that the model sometimes prepends.
    s = re.sub(
        r"^(?:please\s+)?(?:grab|get|take|extract|use|find|locate|open)\s+(?:the\s+)?(?:track|song|audio|file)?\s*",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    s = re.sub(r"^(?:track|song|audio|file)\s+", "", s, flags=re.IGNORECASE).strip()
    return s.strip(" ,.;:")


def _scan_files(folder: Path, *, include_subfolders: bool, exts: set[str]) -> list[Path]:
    pattern = "**/*" if include_subfolders else "*"
    out: list[Path] = []
    for p in Path(folder).glob(pattern):
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
    out.sort(key=lambda x: str(x).lower())
    return out


def run_plan(plan: CommandPlan, *, target_folder: Path, ai_manager=None, progress=None) -> dict[str, Any]:
    """
    Execute a plan. Returns a structured run report.
    """
    library = LibraryIndex()
    converter = LibreOfficeConverter()
    results: list[dict[str, Any]] = []
    steps_total = max(1, len(plan.steps))
    last_search_paths: list[Path] = []

    def norm_bitrate(v):
        if not v:
            return None
        s = str(v).strip().lower().replace("kbps", "k").replace(" ", "")
        m = re.match(r"^(\d{2,3})k$", s)
        if m:
            return f"{m.group(1)}k"
        if re.match(r"^\d{2,3}$", s):
            return f"{s}k"
        return str(v).strip()

    for step_index, step in enumerate(plan.steps):
        tool = step.tool
        args = step.args or {}

        def emit(msg: str, frac: float) -> None:
            if not progress:
                return
            try:
                overall = (step_index + max(0.0, min(1.0, float(frac)))) / steps_total
                progress(msg, overall)
            except Exception:
                pass

        try:
            emit(f"{tool}: starting", 0.0)
            if tool == "index_folder":
                include_subfolders = bool(args.get("include_subfolders", True))
                include_hidden = bool(args.get("include_hidden", False))
                max_files = args.get("max_files", None)
                max_files = int(max_files) if isinstance(max_files, (int, float, str)) and str(max_files).isdigit() else None
                ai_summarize = bool(args.get("ai_summarize", False))
                extract_images = bool(args.get("extract_images", False))
                compute_hashes = bool(args.get("compute_hashes", False))
                include_extensions = args.get("include_extensions", None)
                include_extensions = include_extensions if isinstance(include_extensions, list) else None
                ocr_scanned_pdfs = bool(args.get("ocr_scanned_pdfs", False))
                ocr_pdf_pages = int(args.get("ocr_pdf_pages") or 1)
                max_pdf_ocr_files = int(args.get("max_pdf_ocr_files") or 60)
                count = library.index_folder(
                    Path(target_folder),
                    include_subfolders=include_subfolders,
                    include_hidden=include_hidden,
                    ai_manager=ai_manager,
                    max_files=max_files,
                    ai_summarize=ai_summarize,
                    extract_images=extract_images,
                    compute_hashes=compute_hashes,
                    include_extensions=include_extensions,
                    ocr_scanned_pdfs=ocr_scanned_pdfs,
                    ocr_pdf_pages=ocr_pdf_pages,
                    max_pdf_ocr_files=max_pdf_ocr_files,
                    progress_cb=lambda msg, frac: emit(msg, frac),
                )
                results.append({"tool": tool, "ok": True, "indexed": count})
                emit(f"{tool}: done", 1.0)

            elif tool == "search_index":
                query = str(args.get("query") or "").strip()
                limit = int(args.get("limit") or 50)
                items = library.search(query, limit=limit)
                try:
                    last_search_paths = [Path(i.path) for i in items if getattr(i, "path", None)]
                    last_search_paths = [p for p in last_search_paths if p.exists()]
                except Exception:
                    last_search_paths = []
                results.append({"tool": tool, "ok": True, "query": query, "count": len(items), "items": [i.path for i in items]})
                emit(f"{tool}: done", 1.0)

            elif tool == "convert_office_to_pdf":
                if not converter.is_available():
                    results.append({"tool": tool, "ok": False, "error": "LibreOffice (soffice) not found. Install LibreOffice to enable conversions."})
                    continue
                include_subfolders = bool(args.get("include_subfolders", True))
                output_mode = str(args.get("output_mode") or "subfolder")
                output_subfolder = str(args.get("output_subfolder") or "Converted_PDF")
                overwrite = bool(args.get("overwrite", False))

                files = _scan_office_files(Path(target_folder), include_subfolders=include_subfolders)
                out_dir = Path(target_folder) / output_subfolder if output_mode == "subfolder" else Path(target_folder)
                out_dir.mkdir(parents=True, exist_ok=True)

                converted = []
                skipped = []
                for f in files:
                    out_pdf = out_dir / (f.stem + ".pdf")
                    if out_pdf.exists() and not overwrite:
                        skipped.append(str(f))
                        continue
                    pdf_path = converter.convert_to_pdf(f, out_dir=out_dir)
                    if pdf_path:
                        converted.append(str(pdf_path))
                results.append({"tool": tool, "ok": True, "converted": len(converted), "skipped": len(skipped), "output_dir": str(out_dir)})
                emit(f"{tool}: done", 1.0)

            elif tool == "zip_folder":
                include_subfolders = bool(args.get("include_subfolders", True))
                folder_rel = str(args.get("folder_rel") or "").strip()
                output_zip_name = str(args.get("output_zip_name") or "Archive.zip")
                overwrite = bool(args.get("overwrite", False))

                folder_to_zip = Path(target_folder)
                if folder_rel:
                    resolved = _resolve_under_target(Path(target_folder), folder_rel)
                    if not resolved:
                        results.append({"tool": tool, "ok": False, "error": "folder_rel must be a relative path under target folder"})
                        continue
                    folder_to_zip = resolved

                # output_zip_name may include subfolders, but must remain under target
                out_zip = _resolve_under_target(Path(target_folder), output_zip_name) or (Path(target_folder) / Path(output_zip_name).name)
                out_zip.parent.mkdir(parents=True, exist_ok=True)
                created = zip_folder(folder_to_zip, zip_path=out_zip, include_subfolders=include_subfolders, overwrite=overwrite)
                results.append({"tool": tool, "ok": created.ok, "zip": created.output_path, "message": created.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "unzip_archive":
                archive_rel = str(args.get("archive_path") or "").strip()
                overwrite = bool(args.get("overwrite", False))
                output_subfolder = str(args.get("output_subfolder") or "Extracted")

                archive_path = _resolve_under_target(Path(target_folder), archive_rel)
                if not archive_path:
                    results.append({"tool": tool, "ok": False, "error": "archive_path must be a relative path under target folder"})
                    continue
                out_dir = Path(target_folder) / output_subfolder
                r = unzip_archive(archive_path, output_dir=out_dir, overwrite=overwrite)
                results.append({"tool": tool, "ok": r.ok, "output_dir": r.output_path, "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "convert_images":
                include_subfolders = bool(args.get("include_subfolders", True))
                output_format = str(args.get("output_format") or "png")
                output_subfolder = str(args.get("output_subfolder") or "Converted_Images")
                overwrite = bool(args.get("overwrite", False))

                def per(cur, total, path):
                    # 0..1 within this tool
                    frac = 0.0 if total <= 0 else float(cur) / float(total)
                    emit(f"{tool}: {cur}/{total} {Path(path).name}", frac)

                r = convert_images_in_folder(
                    Path(target_folder),
                    include_subfolders=include_subfolders,
                    output_format=output_format,
                    output_subfolder=output_subfolder,
                    overwrite=overwrite,
                    progress_cb=per,
                )
                results.append(
                    {
                        "tool": tool,
                        "ok": r.ok,
                        "converted": r.converted,
                        "skipped": r.skipped,
                        "output_dir": r.output_dir,
                        "message": r.message,
                    }
                )
                emit(f"{tool}: done", 1.0)

            elif tool == "convert_media":
                include_subfolders = bool(args.get("include_subfolders", True))
                source_subfolder = args.get("source_subfolder", None)
                output_format = str(args.get("output_format") or "mp4")
                output_subfolder = str(args.get("output_subfolder") or "Converted_Media")
                output_root = str(args.get("output_root") or "target").strip().lower()
                overwrite = bool(args.get("overwrite", False))
                audio_bitrate = args.get("audio_bitrate", None)
                audio_bitrate_mode = args.get("audio_bitrate_mode", None)
                video_crf = args.get("video_crf", None)
                video_codec = args.get("video_codec", None)
                scale_height = args.get("scale_height", None)
                use_gpu = bool(args.get("use_gpu", False))
                input_extensions = args.get("input_extensions", None)
                input_extensions = input_extensions if isinstance(input_extensions, list) else None
                preserve_metadata = bool(args.get("preserve_metadata", True))
                preserve_cover_art = bool(args.get("preserve_cover_art", True))
                def per_file(cur: int, total: int, path: Path) -> None:
                    if total <= 0:
                        return
                    emit(f"Converting {path.name}", cur / total)

                r = convert_media_in_folder(
                    Path(target_folder),
                    source_subfolder=str(source_subfolder) if source_subfolder else None,
                    include_subfolders=include_subfolders,
                    output_format=output_format,
                    output_subfolder=output_subfolder,
                    output_root="source" if output_root == "source" else "target",
                    preserve_structure=bool(args.get("preserve_structure", False)),
                    overwrite=overwrite,
                    audio_bitrate=norm_bitrate(audio_bitrate),
                    audio_bitrate_mode=str(audio_bitrate_mode) if audio_bitrate_mode else None,
                    video_crf=str(video_crf) if video_crf else None,
                    input_extensions=input_extensions,
                    preserve_metadata=preserve_metadata,
                    preserve_cover_art=preserve_cover_art,
                    progress_cb=per_file,
                    use_gpu=use_gpu,
                    video_codec=str(video_codec).strip().lower() if video_codec else None,
                    scale_height=int(scale_height) if str(scale_height).isdigit() else None,
                )
                results.append(
                    {
                        "tool": tool,
                        "ok": r.ok,
                        "converted": r.converted,
                        "skipped": r.skipped,
                        "output_dir": r.output_dir,
                        "message": r.message,
                    }
                )
                emit(f"{tool}: done", 1.0)

            elif tool == "convert_media_file":
                raw_inp = str(args.get("input_path") or "").strip()
                raw_inp = _clean_media_query(raw_inp)
                inp = _resolve_any_path(Path(target_folder), raw_inp)
                if inp and not inp.exists():
                    inp = None
                if not inp:
                    inp = _fuzzy_find_under_target(
                        Path(target_folder),
                        raw_inp,
                        exts={".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".mp4", ".mkv", ".avi", ".mov", ".webm"},
                    )
                if not inp:
                    results.append({"tool": tool, "ok": False, "error": "input_path is required"})
                    continue
                output_name = str(args.get("output_name") or (inp.stem + ".mp4")).strip()
                out_path = Path(target_folder) / output_name
                overwrite = bool(args.get("overwrite", False))
                audio_bitrate = args.get("audio_bitrate", None)
                preserve_metadata = bool(args.get("preserve_metadata", True))
                preserve_cover_art = bool(args.get("preserve_cover_art", True))
                r = convert_media_file(
                    inp,
                    output_path=out_path,
                    overwrite=overwrite,
                    audio_bitrate=norm_bitrate(audio_bitrate),
                    preserve_metadata=preserve_metadata,
                    preserve_cover_art=preserve_cover_art,
                )
                results.append({"tool": tool, "ok": r.ok, "output": r.output_path, "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "cut_video":
                raw_inp = str(args.get("input_path") or "").strip()
                raw_inp = _clean_media_query(raw_inp)
                if raw_inp.lower() in {"input", "file", "track", "song", "audio"}:
                    # Use output_name stem as a hint for fuzzy matching.
                    hint = str(args.get("output_name") or "").strip()
                    raw_inp = Path(hint).stem if hint else raw_inp
                inp = _resolve_any_path(Path(target_folder), raw_inp)
                if inp and not inp.exists():
                    inp = None
                if not inp:
                    inp = _fuzzy_find_under_target(
                        Path(target_folder),
                        raw_inp,
                        exts={".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".mp4", ".mkv", ".avi", ".mov", ".webm"},
                    )
                if not inp and last_search_paths:
                    # Use the most recent search results to resolve the file.
                    media_exts = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".mp4", ".mkv", ".avi", ".mov", ".webm"}
                    candidates = [p for p in last_search_paths if p.suffix.lower() in media_exts]
                    inp = candidates[0] if candidates else last_search_paths[0]
                if not inp:
                    results.append(
                        {
                            "tool": tool,
                            "ok": False,
                            "error": f"No matching input file found for '{raw_inp}'. Tip: include the full filename or run Index first.",
                        }
                    )
                    continue
                start = str(args.get("start") or "").strip()
                if not start:
                    results.append({"tool": tool, "ok": False, "error": "start time is required (e.g. 3:47)"})
                    continue
                end = str(args.get("end") or "").strip() or None
                duration = str(args.get("duration") or "").strip() or None
                output_name = str(args.get("output_name") or (inp.stem + "_clip" + inp.suffix)).strip()
                out_path = Path(target_folder) / output_name
                overwrite = bool(args.get("overwrite", False))
                reencode = bool(args.get("reencode", False))
                audio_bitrate = args.get("audio_bitrate", None)
                r = cut_video_segment(
                    inp,
                    output_path=out_path,
                    start=start,
                    end=end,
                    duration=duration,
                    overwrite=overwrite,
                    reencode=reencode,
                    audio_bitrate=norm_bitrate(audio_bitrate),
                )
                results.append({"tool": tool, "ok": r.ok, "output": r.output_path, "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "convert_excel_to_csv":
                inp = _resolve_any_path(Path(target_folder), str(args.get("input_path") or ""))
                if not inp:
                    results.append({"tool": tool, "ok": False, "error": "input_path is required"})
                    continue
                output_name = str(args.get("output_name") or (inp.stem + ".csv")).strip()
                out_path = Path(target_folder) / output_name
                overwrite = bool(args.get("overwrite", False))
                sheet = args.get("sheet", None)
                r = xlsx_to_csv(inp, output_path=out_path, sheet=sheet, overwrite=overwrite)
                results.append({"tool": tool, "ok": r.ok, "output": r.output_path, "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "merge_pdfs":
                include_subfolders = bool(args.get("include_subfolders", False))
                output_pdf_name = str(args.get("output_pdf_name") or "Merged.pdf")
                overwrite = bool(args.get("overwrite", False))
                pdfs = _scan_files(Path(target_folder), include_subfolders=include_subfolders, exts={".pdf"})
                out_pdf = Path(target_folder) / output_pdf_name
                r = merge_pdfs(pdfs, output_pdf=out_pdf, overwrite=overwrite)
                results.append({"tool": tool, "ok": r.ok, "output": (r.output_paths or [None])[0], "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "extract_pdf_pages":
                input_rel = str(args.get("input_pdf") or "").strip()
                overwrite = bool(args.get("overwrite", False))
                page_ranges = str(args.get("page_ranges") or "all")
                output_pdf_name = str(args.get("output_pdf_name") or "Extracted.pdf")

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue

                out_pdf = Path(target_folder) / output_pdf_name
                r = extract_pages_to_pdf(input_pdf, output_pdf=out_pdf, overwrite=overwrite, page_ranges=page_ranges)
                results.append({"tool": tool, "ok": r.ok, "output": (r.output_paths or [None])[0], "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "split_pdf_pages":
                input_rel = str(args.get("input_pdf") or "").strip()
                output_subfolder = str(args.get("output_subfolder") or "Split_Pages")
                overwrite = bool(args.get("overwrite", False))
                page_ranges = str(args.get("page_ranges") or "all")

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue
                out_dir = Path(target_folder) / output_subfolder
                r = split_pdf_to_pages(input_pdf, output_dir=out_dir, overwrite=overwrite, page_ranges=page_ranges)
                results.append({"tool": tool, "ok": r.ok, "output_dir": str(out_dir), "count": len(r.output_paths or []), "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "split_pdf_chunks":
                input_rel = str(args.get("input_pdf") or "").strip()
                output_subfolder = str(args.get("output_subfolder") or "Split_Chunks")
                overwrite = bool(args.get("overwrite", False))
                pages_per_file = int(args.get("pages_per_file") or 10)

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue

                out_dir = Path(target_folder) / output_subfolder
                r = split_pdf_into_chunks(input_pdf, output_dir=out_dir, pages_per_file=pages_per_file, overwrite=overwrite)
                results.append({"tool": tool, "ok": r.ok, "output_dir": str(out_dir), "count": len(r.output_paths or []), "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "split_pdf_bookmarks":
                input_rel = str(args.get("input_pdf") or "").strip()
                output_subfolder = str(args.get("output_subfolder") or "Split_By_Bookmarks")
                overwrite = bool(args.get("overwrite", False))
                min_pages = int(args.get("min_pages") or 1)

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue

                out_dir = Path(target_folder) / output_subfolder
                r = split_pdf_by_bookmarks(input_pdf, output_dir=out_dir, overwrite=overwrite, min_pages=min_pages)
                results.append({"tool": tool, "ok": r.ok, "output_dir": str(out_dir), "count": len(r.output_paths or []), "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "rotate_pdf":
                input_rel = str(args.get("input_pdf") or "").strip()
                overwrite = bool(args.get("overwrite", False))
                output_pdf_name = str(args.get("output_pdf_name") or "Rotated.pdf")
                rotation_degrees = int(args.get("rotation_degrees") or 90)
                page_ranges = str(args.get("page_ranges") or "all")

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue
                out_pdf = Path(target_folder) / output_pdf_name
                r = rotate_pdf(
                    input_pdf,
                    output_pdf=out_pdf,
                    rotation_degrees=rotation_degrees,
                    page_ranges=page_ranges,
                    overwrite=overwrite,
                )
                results.append({"tool": tool, "ok": r.ok, "output": (r.output_paths or [None])[0], "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "remove_pdf_pages":
                input_rel = str(args.get("input_pdf") or "").strip()
                remove_ranges = str(args.get("remove_ranges") or "").strip()
                overwrite = bool(args.get("overwrite", False))
                output_pdf_name = str(args.get("output_pdf_name") or "RemovedPages.pdf")

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue
                if not remove_ranges:
                    results.append({"tool": tool, "ok": False, "error": "remove_ranges is required (e.g. 2,5-7)"})
                    continue

                out_pdf = Path(target_folder) / output_pdf_name
                r = remove_pages(input_pdf, output_pdf=out_pdf, remove_ranges=remove_ranges, overwrite=overwrite)
                results.append({"tool": tool, "ok": r.ok, "output": (r.output_paths or [None])[0], "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "reorder_pdf_pages":
                input_rel = str(args.get("input_pdf") or "").strip()
                overwrite = bool(args.get("overwrite", False))
                output_pdf_name = str(args.get("output_pdf_name") or "Reordered.pdf")
                order = args.get("order", None)

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue
                if not isinstance(order, list) or not order:
                    results.append({"tool": tool, "ok": False, "error": "order must be a non-empty list (e.g. [2,1,3])"})
                    continue

                out_pdf = Path(target_folder) / output_pdf_name
                r = reorder_pages(input_pdf, output_pdf=out_pdf, order=order, overwrite=overwrite)
                results.append({"tool": tool, "ok": r.ok, "output": (r.output_paths or [None])[0], "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "watermark_pdf":
                input_rel = str(args.get("input_pdf") or "").strip()
                overwrite = bool(args.get("overwrite", False))
                output_pdf_name = str(args.get("output_pdf_name") or "Watermarked.pdf")
                text = str(args.get("text") or "").strip()
                opacity = args.get("opacity", 0.15)
                font_size = args.get("font_size", 44)
                rotate_degrees = args.get("rotate_degrees", 30)

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue
                if not text:
                    results.append({"tool": tool, "ok": False, "error": "text is required"})
                    continue

                out_pdf = Path(target_folder) / output_pdf_name
                r = add_text_watermark(
                    input_pdf,
                    output_pdf=out_pdf,
                    text=text,
                    overwrite=overwrite,
                    opacity=float(opacity),
                    font_size=int(font_size),
                    rotate_degrees=int(rotate_degrees),
                )
                results.append({"tool": tool, "ok": r.ok, "output": (r.output_paths or [None])[0], "message": r.message})
                emit(f"{tool}: done", 1.0)

            elif tool == "search_pdf_text":
                input_rel = str(args.get("input_pdf") or "").strip()
                query = str(args.get("query") or "").strip()
                max_hits = int(args.get("max_hits") or 50)
                case_sensitive = bool(args.get("case_sensitive", False))

                input_pdf = _resolve_under_target(Path(target_folder), input_rel) if input_rel else None
                if not input_pdf:
                    pdfs = _scan_files(Path(target_folder), include_subfolders=False, exts={".pdf"})
                    if len(pdfs) == 1:
                        input_pdf = pdfs[0]
                if not input_pdf:
                    results.append({"tool": tool, "ok": False, "error": "input_pdf required (or place a single PDF in target folder)."})
                    continue
                if not query:
                    results.append({"tool": tool, "ok": False, "error": "query is required"})
                    continue

                hits = search_pdf_text(input_pdf, query=query, max_hits=max_hits, case_sensitive=case_sensitive)
                results.append(
                    {
                        "tool": tool,
                        "ok": True,
                        "count": len(hits),
                        "hits": [{"page": h.page_number, "snippet": h.snippet} for h in hits],
                    }
                )
                emit(f"{tool}: done", 1.0)

            elif tool == "make_folder":
                subfolder = str(args.get("subfolder") or "").strip()
                if not subfolder:
                    results.append({"tool": tool, "ok": False, "error": "subfolder is required"})
                    continue
                dest = make_subfolder(Path(target_folder), subfolder)
                results.append({"tool": tool, "ok": True, "folder": str(dest)})
                emit(f"{tool}: done", 1.0)

            elif tool == "move_files":
                dest_subfolder = str(args.get("dest_subfolder") or "").strip()
                if not dest_subfolder:
                    results.append({"tool": tool, "ok": False, "error": "dest_subfolder is required"})
                    continue
                r = move_files(
                    Path(target_folder),
                    dest_subfolder=dest_subfolder,
                    include_subfolders=bool(args.get("include_subfolders", True)),
                    include_hidden=bool(args.get("include_hidden", False)),
                    selector=args.get("selector") if isinstance(args.get("selector"), dict) else None,
                    overwrite=bool(args.get("overwrite", False)),
                )
                results.append({"tool": tool, "ok": r.ok, "moved": r.affected, "message": r.message, "details": r.details})
                emit(f"{tool}: done", 1.0)

            elif tool == "copy_files":
                dest_subfolder = str(args.get("dest_subfolder") or "").strip()
                if not dest_subfolder:
                    results.append({"tool": tool, "ok": False, "error": "dest_subfolder is required"})
                    continue
                r = copy_files(
                    Path(target_folder),
                    dest_subfolder=dest_subfolder,
                    include_subfolders=bool(args.get("include_subfolders", True)),
                    include_hidden=bool(args.get("include_hidden", False)),
                    selector=args.get("selector") if isinstance(args.get("selector"), dict) else None,
                    overwrite=bool(args.get("overwrite", False)),
                )
                results.append({"tool": tool, "ok": r.ok, "copied": r.affected, "message": r.message, "details": r.details})
                emit(f"{tool}: done", 1.0)

            elif tool == "delete_files":
                r = delete_files(
                    Path(target_folder),
                    include_subfolders=bool(args.get("include_subfolders", True)),
                    include_hidden=bool(args.get("include_hidden", False)),
                    selector=args.get("selector") if isinstance(args.get("selector"), dict) else None,
                )
                results.append({"tool": tool, "ok": r.ok, "deleted": r.affected, "message": r.message, "details": r.details})
                emit(f"{tool}: done", 1.0)

            elif tool == "organize_audio_by_tags":
                source_subfolder = str(args.get("source_subfolder") or "").strip() or None
                dest_subfolder = str(args.get("dest_subfolder") or "Organized_Music")
                include_subfolders = bool(args.get("include_subfolders", True))
                overwrite = bool(args.get("overwrite", False))

                def per(cur, total, path, dest):
                    if total <= 0:
                        return
                    emit(f"Organizing {path.name}", cur / total)

                r = organize_audio_by_tags(
                    Path(target_folder),
                    source_subfolder=source_subfolder,
                    dest_subfolder=dest_subfolder,
                    include_subfolders=include_subfolders,
                    overwrite=overwrite,
                    progress_cb=per,
                )
                results.append({"tool": tool, "ok": r.ok, "moved": r.moved, "skipped": r.skipped, "dest_root": r.dest_root, "message": r.message})
                emit(f"{tool}: done", 1.0)

            else:
                results.append({"tool": tool, "ok": False, "error": "Unknown tool"})
                emit(f"{tool}: failed", 1.0)

        except Exception as e:
            results.append({"tool": tool, "ok": False, "error": str(e)})
            emit(f"{tool}: error", 1.0)

    ok = all(r.get("ok") for r in results if "ok" in r)
    return {"ok": ok, "intent_summary": plan.intent_summary, "steps": [s.__dict__ for s in plan.steps], "results": results}


def _scan_office_files(folder: Path, *, include_subfolders: bool) -> list[Path]:
    exts = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".odp", ".ods"}
    pattern = "**/*" if include_subfolders else "*"
    files: list[Path] = []
    for p in folder.glob(pattern):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
    return files
