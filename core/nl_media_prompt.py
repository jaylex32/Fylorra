"""
Natural-language media edit parsing (Audio/Video Editors).

Goal:
- Fast, offline heuristics for common phrasing.
- Optional AI enhancement (Qwen via AIManager) that returns strict JSON.

Editors use this to translate user prompts like:
  "grab track 16 - DtMF.flac and create a ringtone by cutting between 1:23 to 1:41 into DtMF_Ringtone.mp3"
into structured parameters usable by the UI + ffmpeg pipeline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.time_parse import parse_timestamp_to_seconds


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    # Best-effort: find the first {...} block.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _norm(s: str) -> str:
    return re.sub(r"\\s+", " ", (s or "").strip().lower())


def _match_file_from_phrase(files: list[Path], phrase: str) -> Path | None:
    phrase = _norm(phrase)
    if not phrase:
        return None
    best: tuple[int, Path] | None = None
    for p in files:
        name = _norm(p.name)
        score = 0
        # prefer exact substring match on filename
        if phrase in name:
            score += 200 + len(phrase)
        # try without extension
        stem = _norm(p.stem)
        if phrase in stem:
            score += 150 + len(phrase)
        # ignore punctuation differences
        simple = re.sub(r"[^a-z0-9]+", "", phrase)
        if simple and simple in re.sub(r"[^a-z0-9]+", "", name):
            score += 120 + len(simple)
        if score and (best is None or score > best[0]):
            best = (score, p)
    return best[1] if best else None


def select_media_file_from_nl(files: list[Path], instruction: str) -> Path | None:
    """
    Supports:
    - "grab track 16 - DtMF.flac"
    - "grab file 11 - TURiSTA.flac"
    - "use DtMF.flac"
    - "open TURiSTA"
    """
    text = _norm(instruction)
    if not files or not text:
        return None

    # Explicit "track/file N - name" pattern.
    m = re.search(r"\\b(?:grab|use|open|select)\\s+(?:track|file)\\s*(\\d{1,3})\\s*(?:[-:–—]\\s*([^,;]+))?", text)
    if m:
        idx = None
        try:
            idx = int(m.group(1))
        except Exception:
            idx = None
        name_part = (m.group(2) or "").strip()
        if name_part:
            hit = _match_file_from_phrase(files, name_part)
            if hit:
                return hit
        # fallback: 1-based index
        if idx is not None and 1 <= idx <= len(files):
            return files[idx - 1]

    # "track 16 - ..." without leading verb
    m = re.search(r"\\b(?:track|file)\\s*(\\d{1,3})\\s*(?:[-:–—]\\s*([^,;]+))", text)
    if m:
        name_part = (m.group(2) or "").strip()
        hit = _match_file_from_phrase(files, name_part)
        if hit:
            return hit

    # Direct filename mention
    for p in files:
        if _norm(p.name) in text or _norm(p.stem) in text:
            return p

    # Quoted name
    m = re.search(r"['\\\"]([^'\\\"]+\\.(?:mp3|wav|flac|m4a|aac|ogg|opus|mp4|mkv|mov|webm|avi|m4v))['\\\"]", text)
    if m:
        hit = _match_file_from_phrase(files, m.group(1))
        if hit:
            return hit

    return None


@dataclass
class AudioNLResult:
    select_path: Path | None = None
    trim_start: str | None = None
    trim_end: str | None = None
    fade_out_start: str | None = None
    fade_out_end: str | None = None
    fade_in_start: str | None = None
    fade_in_end: str | None = None
    out_name: str | None = None
    out_format: str | None = None
    bitrate: str | None = None
    normalize: bool | None = None
    volume_db: str | None = None


def heuristic_audio_from_nl(files: list[Path], instruction: str) -> AudioNLResult:
    text = _norm(instruction)
    out = AudioNLResult()
    out.select_path = select_media_file_from_nl(files, instruction)

    # Trim range: "between A to B" / "cut A to B"
    m = re.search(r"\\b(?:between|from|cut|trim)\\s+(\\d+[:\\d\\.]+)\\s*(?:to|-|until)\\s*(\\d+[:\\d\\.]+)", text)
    if m:
        out.trim_start = m.group(1)
        out.trim_end = m.group(2)

    # Output filename: "into NAME.ext" / "as NAME.ext" / "export as NAME.ext"
    m = re.search(r"\\b(?:into|as|export(?:ed)?\\s+as)\\s+([^,;]+?\\.(mp3|wav|flac|m4a|aac|ogg|opus))\\b", instruction, flags=re.IGNORECASE)
    if m:
        filename = m.group(1).strip().strip("\"'")
        out.out_name = Path(filename).stem
        out.out_format = Path(filename).suffix.lstrip(".").lower()

    # "exported as mp3"
    m = re.search(r"\\bexport(?:ed)?\\s+as\\s+(mp3|wav|flac|m4a|aac|ogg|opus)\\b", text)
    if m:
        out.out_format = m.group(1)

    # bitrate
    m = re.search(r"\\b(\\d{2,3})\\s*(?:kbps|k)\\b", text)
    if m:
        out.bitrate = m.group(1) + "k"

    # normalize
    if "normalize" in text or "loudnorm" in text:
        out.normalize = True

    # volume
    m = re.search(r"\\bvolume\\s*([+-]?\\d+(?:\\.\\d+)?)\\b", text)
    if m:
        out.volume_db = m.group(1)

    # fade-out: "starting from T start to fade out ... until it ends"
    m = re.search(r"\\b(?:starting\\s+from|from)\\s+(\\d+[:\\d\\.]+)\\s+start\\s+to\\s+fade\\s+out\\b", text)
    if m:
        out.fade_out_start = m.group(1)
        # end is "end" of trim or "end of file" – we resolve later in the editor using duration / Out point.

    # fade-in: "fade in starting from T" (rare but supported)
    m = re.search(r"\\b(?:starting\\s+from|from)\\s+(\\d+[:\\d\\.]+)\\s+start\\s+to\\s+fade\\s+in\\b", text)
    if m:
        out.fade_in_start = m.group(1)

    return out


def ai_audio_from_nl(ai_manager, files: list[Path], instruction: str) -> AudioNLResult | None:
    if not ai_manager or not getattr(ai_manager, "is_ready", False) or not getattr(ai_manager, "model", None):
        return None

    # Keep file list short for the model (names only).
    file_names = [p.name for p in files[:80]]
    schema = {
        "type": "object",
        "properties": {
            "select": {"type": "string", "description": "Either a filename (best) or 'index:N' 1-based."},
            "trim_start": {"type": ["string", "null"]},
            "trim_end": {"type": ["string", "null"]},
            "fade_out_start": {"type": ["string", "null"]},
            "fade_out_end": {"type": ["string", "null"], "description": "Optional end time; null means until end of selected trim."},
            "fade_in_start": {"type": ["string", "null"]},
            "fade_in_end": {"type": ["string", "null"]},
            "output_name": {"type": ["string", "null"]},
            "output_format": {"type": ["string", "null"], "enum": ["mp3", "wav", "flac", "m4a", "aac", "ogg", "opus", None]},
            "bitrate": {"type": ["string", "null"], "description": "e.g. 320k"},
            "normalize": {"type": ["boolean", "null"]},
            "volume_db": {"type": ["string", "null"], "description": "e.g. -3, +2.5"},
        },
        "required": ["select"],
        "additionalProperties": False,
    }

    examples = [
        {
            "in": "grab track 16 - DtMF.flac and create a ringtone by cutting between 1:23 to 1:41 into DtMF_Ringtone.mp3",
            "out": {
                "select": "DtMF.flac",
                "trim_start": "1:23",
                "trim_end": "1:41",
                "fade_out_start": None,
                "fade_out_end": None,
                "fade_in_start": None,
                "fade_in_end": None,
                "output_name": "DtMF_Ringtone",
                "output_format": "mp3",
                "bitrate": "320k",
                "normalize": None,
                "volume_db": None,
            },
        },
        {
            "in": "grab file 11 - TURiSTA.flac and cut it between 00:00:00 to 00:00:35.735 and starting from 00:00:25.000 start to fade out the audio until it ends and then exported as a mp3",
            "out": {
                "select": "TURiSTA.flac",
                "trim_start": "00:00:00",
                "trim_end": "00:00:35.735",
                "fade_out_start": "00:00:25.000",
                "fade_out_end": None,
                "fade_in_start": None,
                "fade_in_end": None,
                "output_name": None,
                "output_format": "mp3",
                "bitrate": None,
                "normalize": None,
                "volume_db": None,
            },
        },
        {
            "in": "use \"My Song.flac\" trim 0:10-0:40, normalize, export mp3 192k as my_song_clip",
            "out": {
                "select": "My Song.flac",
                "trim_start": "0:10",
                "trim_end": "0:40",
                "fade_out_start": None,
                "fade_out_end": None,
                "fade_in_start": None,
                "fade_in_end": None,
                "output_name": "my_song_clip",
                "output_format": "mp3",
                "bitrate": "192k",
                "normalize": True,
                "volume_db": None,
            },
        },
    ]

    prompt = (
        "You convert natural-language audio edit instructions into STRICT JSON.\n"
        "Return JSON only (no markdown, no code fences).\n"
        "Use double quotes for all strings.\n"
        "Rules:\n"
        "- 'select' must match one of the provided filenames if possible.\n"
        "- If the user references a number like 'track 16', convert it to the best filename match.\n"
        "- Times may be like 1:23, 00:01:23.456.\n"
        "- If the user says 'fade out starting from T until it ends', set fade_out_start=T and fade_out_end=null.\n"
        "- If the user says 'export as NAME.ext', set output_name and output_format.\n\n"
        f"Files: {json.dumps(file_names)}\n\n"
        f"Schema: {json.dumps(schema)}\n\n"
        f"Examples: {json.dumps(examples)}\n\n"
        f"User instruction: {instruction}\n"
    )

    try:
        resp = ai_manager.create_chat_completion_safe(
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            temperature=0.2,
            max_tokens=500,
        )
        content = resp["choices"][0]["message"]["content"]
        data = _extract_json(content)
        if not data:
            return None
        select = str(data.get("select") or "").strip()
        if not select:
            return None
        r = AudioNLResult()
        if select.lower().startswith("index:"):
            try:
                idx = int(select.split(":", 1)[1].strip())
                if 1 <= idx <= len(files):
                    r.select_path = files[idx - 1]
            except Exception:
                pass
        else:
            r.select_path = _match_file_from_phrase(files, select) or None

        for k in ["trim_start", "trim_end", "fade_out_start", "fade_out_end", "fade_in_start", "fade_in_end"]:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                setattr(r, k, v.strip())
        out_name = data.get("output_name")
        if isinstance(out_name, str) and out_name.strip():
            r.out_name = out_name.strip()
        out_fmt = data.get("output_format")
        if isinstance(out_fmt, str) and out_fmt.strip():
            r.out_format = out_fmt.strip().lower()
        bitrate = data.get("bitrate")
        if isinstance(bitrate, str) and bitrate.strip():
            r.bitrate = bitrate.strip().lower()
        norm = data.get("normalize")
        if isinstance(norm, bool):
            r.normalize = norm
        vol = data.get("volume_db")
        if isinstance(vol, str) and vol.strip():
            r.volume_db = vol.strip()
        return r
    except Exception:
        return None


def _safe_seconds(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return float(parse_timestamp_to_seconds(ts))
    except Exception:
        return None


@dataclass
class VideoNLResult:
    select_path: Path | None = None
    trim_start: str | None = None
    trim_end: str | None = None
    out_name: str | None = None
    out_format: str | None = None
    resolution: str | None = None
    codec: str | None = None
    fps: str | None = None
    crf: str | None = None
    use_gpu: bool | None = None


def heuristic_video_from_nl(files: list[Path], instruction: str) -> VideoNLResult:
    text = _norm(instruction)
    out = VideoNLResult()
    out.select_path = select_media_file_from_nl(files, instruction)

    m = re.search(r"\\b(?:between|from|cut|trim)\\s+(\\d+[:\\d\\.]+)\\s*(?:to|-|until)\\s*(\\d+[:\\d\\.]+)", text)
    if m:
        out.trim_start = m.group(1)
        out.trim_end = m.group(2)

    m = re.search(r"\\b(?:into|as|export(?:ed)?\\s+as)\\s+([^,;]+?\\.(mp4|mkv|mov|webm|avi|m4v))\\b", instruction, flags=re.IGNORECASE)
    if m:
        filename = m.group(1).strip().strip("\"'")
        out.out_name = Path(filename).stem
        out.out_format = Path(filename).suffix.lstrip(".").lower()

    for fmt in ["mp4", "mkv", "mov", "webm"]:
        if re.search(rf"\\b{fmt}\\b", text):
            out.out_format = fmt

    for res in ["360p", "480p", "720p", "1080p", "4k"]:
        if res in text:
            out.resolution = res

    if "h265" in text or "hevc" in text:
        out.codec = "h265"
    elif "vp9" in text:
        out.codec = "vp9"
    elif "h264" in text:
        out.codec = "h264"

    m = re.search(r"\\b(24|25|30|50|60|120)\\s*fps\\b", text)
    if m:
        out.fps = m.group(1)
    m = re.search(r"\\bcrf\\s*(\\d{1,2})\\b", text)
    if m:
        out.crf = m.group(1)
    if "gpu" in text or "nvenc" in text:
        out.use_gpu = True

    return out


def ai_video_from_nl(ai_manager, files: list[Path], instruction: str) -> VideoNLResult | None:
    if not ai_manager or not getattr(ai_manager, "is_ready", False) or not getattr(ai_manager, "model", None):
        return None

    file_names = [p.name for p in files[:80]]
    schema = {
        "type": "object",
        "properties": {
            "select": {"type": "string", "description": "Either a filename (best) or 'index:N' 1-based."},
            "trim_start": {"type": ["string", "null"]},
            "trim_end": {"type": ["string", "null"]},
            "output_name": {"type": ["string", "null"]},
            "output_format": {"type": ["string", "null"], "enum": ["mp4", "mkv", "mov", "webm", None]},
            "resolution": {"type": ["string", "null"], "enum": ["360p", "480p", "720p", "1080p", "4k", None]},
            "codec": {"type": ["string", "null"], "enum": ["h264", "h265", "vp9", None]},
            "fps": {"type": ["string", "null"]},
            "crf": {"type": ["string", "null"]},
            "use_gpu": {"type": ["boolean", "null"]},
        },
        "required": ["select"],
        "additionalProperties": False,
    }

    examples = [
        {
            "in": "grab clip 1 - intro.mp4 and cut between 0:10 to 0:25 and export as intro_cut.mp4 720p h265 30fps",
            "out": {
                "select": "intro.mp4",
                "trim_start": "0:10",
                "trim_end": "0:25",
                "output_name": "intro_cut",
                "output_format": "mp4",
                "resolution": "720p",
                "codec": "h265",
                "fps": "30",
                "crf": "20",
                "use_gpu": True,
            },
        },
        {
            "in": "cut 1:23-1:41 and export mkv 1080p h264 crf 18",
            "out": {
                "select": "index:1",
                "trim_start": "1:23",
                "trim_end": "1:41",
                "output_name": None,
                "output_format": "mkv",
                "resolution": "1080p",
                "codec": "h264",
                "fps": None,
                "crf": "18",
                "use_gpu": None,
            },
        },
    ]

    prompt = (
        "You convert natural-language video edit instructions into STRICT JSON.\n"
        "Return JSON only (no markdown, no code fences).\n"
        "Use double quotes for all strings.\n"
        "Rules:\n"
        "- 'select' must match one of the provided filenames if possible.\n"
        "- If user references 'clip N' or 'file N', convert to best filename match.\n"
        "- Times may be like 1:23, 00:01:23.456.\n"
        "- If user says 'export as NAME.ext', set output_name and output_format.\n\n"
        f"Files: {json.dumps(file_names)}\n\n"
        f"Schema: {json.dumps(schema)}\n\n"
        f"Examples: {json.dumps(examples)}\n\n"
        f"User instruction: {instruction}\n"
    )

    try:
        resp = ai_manager.create_chat_completion_safe(
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            temperature=0.2,
            max_tokens=500,
        )
        content = resp["choices"][0]["message"]["content"]
        data = _extract_json(content)
        if not data:
            return None
        select = str(data.get("select") or "").strip()
        if not select:
            return None
        r = VideoNLResult()
        if select.lower().startswith("index:"):
            try:
                idx = int(select.split(":", 1)[1].strip())
                if 1 <= idx <= len(files):
                    r.select_path = files[idx - 1]
            except Exception:
                pass
        else:
            r.select_path = _match_file_from_phrase(files, select) or None
        for k in ["trim_start", "trim_end", "resolution", "codec", "fps", "crf"]:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                setattr(r, k if k not in {"resolution"} else "resolution", v.strip().lower())
        out_name = data.get("output_name")
        if isinstance(out_name, str) and out_name.strip():
            r.out_name = out_name.strip()
        out_fmt = data.get("output_format")
        if isinstance(out_fmt, str) and out_fmt.strip():
            r.out_format = out_fmt.strip().lower()
        use_gpu = data.get("use_gpu")
        if isinstance(use_gpu, bool):
            r.use_gpu = use_gpu
        return r
    except Exception:
        return None
