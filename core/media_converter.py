"""
Fylorra - Media Conversion (optional)
Uses ffmpeg if available (can be bundled with the app for seamless installs).
"""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
import re

from core.ffmpeg_manager import ffmpeg_has_encoder, get_ffmpeg_exe, get_ffprobe_exe
from core.tag_tools import ensure_mp3_cover_art, extract_cover_art


@dataclass(frozen=True)
class MediaConvertResult:
    ok: bool
    message: str
    converted: int = 0
    skipped: int = 0
    output_dir: str | None = None


def convert_media_in_folder(
    folder: Path,
    *,
    source_subfolder: str | None = None,
    include_subfolders: bool = True,
    output_format: str = "mp4",
    output_subfolder: str = "Converted_Media",
    output_root: str = "source",  # "source" | "target" | "custom"
    output_directory: str | None = None,
    preserve_structure: bool = False,
    preserve_subfolders: bool | None = None,
    overwrite: bool = False,
    audio_bitrate: str | None = None,
    video_crf: str | None = None,
    input_extensions: list[str] | None = None,
    audio_bitrate_mode: str | None = None,  # "cbr" | "vbr"
    preserve_metadata: bool = True,
    preserve_cover_art: bool = True,
    progress_cb=None,  # callable(current:int,total:int, path:Path) -> None
    file_progress_cb=None,  # callable(path:Path, frac:float) -> None (0..1 within current file)
    cancel_event: threading.Event | None = None,
    use_gpu: bool = False,
    video_codec: str | None = None,  # "h264" | "h265" | "vp9" | "copy" | None
    scale_height: int | None = None,  # e.g. 720, 1080
    audio_codec: str | None = None,  # "aac" | "mp3" | "opus" | "vorbis" | "copy" | None
) -> MediaConvertResult:
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return MediaConvertResult(ok=False, message="ffmpeg not available. Install 'imageio-ffmpeg' or set FYLORRA_FFMPEG.")

    folder = Path(folder)
    if not folder.exists():
        return MediaConvertResult(ok=False, message="Folder not found.")

    folder = Path(folder)
    base_dir = folder
    if source_subfolder:
        sub = str(source_subfolder).strip().strip("\"'")
        # Prevent escaping outside the target folder
        if sub.startswith(("/", "\\")) or ":" in sub or ".." in Path(sub).parts:
            return MediaConvertResult(ok=False, message="source_subfolder must be a relative folder name under target folder.")
        base_dir = folder / sub
    if not base_dir.exists() or not base_dir.is_dir():
        return MediaConvertResult(ok=False, message="Source folder not found.")

    output_format = (output_format or "mp4").strip().lower().lstrip(".")
    output_root = (output_root or "source").strip().lower()
    preserve_structure = bool(preserve_structure)
    if output_root == "custom":
        out_base = Path(str(output_directory or "").strip())
        if not str(out_base):
            return MediaConvertResult(ok=False, message="Output destination is required.")
        if not out_base.is_absolute():
            out_base = folder / out_base
    else:
        out_base = folder if output_root == "target" else base_dir
    if preserve_structure and output_root in {"target", "custom"} and source_subfolder:
        out_dir = out_base / output_subfolder / Path(str(source_subfolder)).name
    else:
        out_dir = out_base / output_subfolder
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        out_dir_resolved = out_dir.resolve()
    except Exception:
        out_dir_resolved = out_dir
    # Safety: ensure output dir is inside the chosen base (source or target).
    try:
        base_resolved = out_base.resolve()
        out_dir_resolved.relative_to(base_resolved)
    except Exception:
        return MediaConvertResult(ok=False, message="Output folder must be inside the selected destination.")

    def norm_ext(e: str) -> str:
        e = (e or "").strip().lower()
        return e if e.startswith(".") else "." + e

    def _subprocess_kwargs() -> dict:
        if os.name != "nt":
            return {}
        kwargs: dict = {}
        try:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        except Exception:
            pass
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si
        except Exception:
            pass
        return kwargs

    # Minimal set of supported inputs unless narrowed by input_extensions.
    default_exts = {
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".wmv",
        ".flv",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
        ".wma",
        ".aiff",
        ".alac",
    }
    input_exts = default_exts
    if input_extensions:
        exts = {norm_ext(e) for e in input_extensions if (e or "").strip()}
        input_exts = exts if exts else default_exts
    # Avoid endless loops when output folder is inside input tree.
    out_ext = norm_ext(output_format)
    if out_ext in input_exts:
        input_exts = {e for e in input_exts if e != out_ext}

    audio_out = output_format in {"mp3", "wav", "m4a", "aac", "flac", "ogg", "opus", "wma", "aiff", "alac"}
    lossy_audio_out = output_format in {"mp3", "m4a", "aac", "ogg", "opus", "wma"}
    audio_bitrate_mode = (audio_bitrate_mode or "").strip().lower() or None
    video_codec = (video_codec or "").strip().lower() or None
    audio_codec = (audio_codec or "").strip().lower() or None
    video_exts = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"}

    def _audio_codec_for_format(fmt: str) -> str | None:
        fmt = (fmt or "").strip().lower()
        if fmt in {"m4a", "aac"}:
            if ffmpeg_has_encoder("aac"):
                return "aac"
            if ffmpeg_has_encoder("libfdk_aac"):
                return "libfdk_aac"
            return None
        if fmt == "flac":
            return "flac"
        if fmt == "wav":
            return "pcm_s16le"
        if fmt == "aiff":
            return "pcm_s16le"
        if fmt == "alac":
            return "alac"
        if fmt == "wma":
            return "wmav2"
        if fmt == "ogg":
            if ffmpeg_has_encoder("libvorbis"):
                return "libvorbis"
            if ffmpeg_has_encoder("vorbis"):
                return "vorbis"
            if ffmpeg_has_encoder("libopus"):
                return "libopus"
            return None
        if fmt == "opus":
            if ffmpeg_has_encoder("libopus"):
                return "libopus"
            if ffmpeg_has_encoder("opus"):
                return "opus"
            return None
        return None

    def _resolve_audio_codec(name: str | None) -> str | None:
        if not name:
            return None
        name = name.strip().lower()
        if name == "copy":
            return "copy"
        if name == "aac":
            if ffmpeg_has_encoder("aac"):
                return "aac"
            if ffmpeg_has_encoder("libfdk_aac"):
                return "libfdk_aac"
            return "aac"
        if name == "mp3":
            return "libmp3lame" if ffmpeg_has_encoder("libmp3lame") else "mp3"
        if name == "opus":
            return "libopus" if ffmpeg_has_encoder("libopus") else "opus"
        if name == "vorbis":
            return "libvorbis" if ffmpeg_has_encoder("libvorbis") else "vorbis"
        return name

    preserve_subfolders = include_subfolders if preserve_subfolders is None else bool(preserve_subfolders)
    pattern = "**/*" if include_subfolders else "*"
    # Collect candidates first to know total and avoid converting outputs created during the run.
    candidates: list[Path] = []
    converted = 0
    skipped = 0
    cover_cache: dict[str, object] = {}
    for p in base_dir.glob(pattern):
        if not p.is_file():
            continue
        if p.suffix.lower() not in input_exts:
            continue
        # Never convert files inside the output directory (prevents nesting/infinite loops).
        try:
            p.resolve().relative_to(out_dir_resolved)
            continue
        except Exception:
            pass
        try:
            if p.resolve() == out_dir_resolved:
                continue
        except Exception:
            pass
        candidates.append(p)

    total = len(candidates)

    def get_duration_seconds(media_path: Path) -> float | None:
        """
        Best-effort duration lookup for progress reporting.
        Returns seconds or None.
        """
        ffprobe = get_ffprobe_exe()
        if ffprobe:
            try:
                proc = subprocess.run(
                    [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(media_path)],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    **_subprocess_kwargs(),
                )
                out = (proc.stdout or "").strip()
                if out:
                    dur = max(0.0, float(out))
                    return dur if dur >= 1.0 else None
            except Exception:
                pass

        try:
            proc = subprocess.run(
                [str(ffmpeg), "-hide_banner", "-i", str(media_path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                **_subprocess_kwargs(),
            )
            out = proc.stdout or ""
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
            if not m:
                return None
            hh = int(m.group(1))
            mm = int(m.group(2))
            ss = float(m.group(3))
            dur = max(0.0, hh * 3600 + mm * 60 + ss)
            return dur if dur >= 1.0 else None
        except Exception:
            return None

    for i, p in enumerate(candidates, start=1):
        if cancel_event and cancel_event.is_set():
            return MediaConvertResult(ok=False, message="Cancelled.", converted=converted, skipped=skipped, output_dir=str(out_dir))

        if progress_cb:
            try:
                progress_cb(i, total, p)
            except Exception:
                pass

        rel = p.relative_to(base_dir)
        dest_dir = out_dir / rel.parent if preserve_subfolders else out_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_path = dest_dir / (p.stem + f".{output_format}")
        if out_path.exists() and not overwrite:
            skipped += 1
            continue

        cover = None
        if preserve_cover_art and output_format == "mp3":
            key = str(p)
            cover = cover_cache.get(key)
            if cover is None:
                cover = extract_cover_art(p)
                cover_cache[key] = cover if cover is not None else False
            if cover is False:
                cover = None

        cmd = [
            str(ffmpeg),
            "-y" if overwrite else "-n",
            "-i",
            str(p),
        ]
        if audio_out:
            # audio-only output
            if preserve_metadata:
                cmd += ["-map_metadata", "0"]
            cover_supported = output_format in {"m4a", "m4b", "flac", "ogg", "opus"}
            include_cover = bool(preserve_cover_art and cover_supported and p.suffix.lower() not in video_exts)
            if include_cover:
                cmd += ["-map", "0:a:0", "-map", "0:v:0?", "-c:v", "copy"]
            else:
                cmd += ["-vn", "-map", "0:a:0"]

        if audio_out and output_format == "mp3":
            cmd += ["-c:a", "libmp3lame", "-id3v2_version", "3", "-write_id3v1", "1"]
            if audio_bitrate:
                cmd += ["-b:a", str(audio_bitrate)]
                if audio_bitrate_mode in {None, "cbr"}:
                    cmd += ["-minrate", str(audio_bitrate), "-maxrate", str(audio_bitrate), "-bufsize", str(audio_bitrate)]
        elif audio_out:
            codec = _audio_codec_for_format(output_format)
            if codec:
                cmd += ["-c:a", codec]
            if audio_bitrate and lossy_audio_out:
                cmd += ["-b:a", str(audio_bitrate)]
        if not audio_out:
            # Video encode defaults (more deterministic than ffmpeg defaults)
            out_ext = "." + output_format
            if scale_height and int(scale_height) > 0 and video_codec != "copy":
                # Keep aspect ratio, ensure even dimensions.
                cmd += ["-vf", f"scale=-2:{int(scale_height)}"]

            default_audio_codec = None
            if video_codec == "copy":
                cmd += ["-c:v", "copy"]
            elif use_gpu and ffmpeg_has_encoder("h264_nvenc") and out_ext in {".mp4", ".mkv", ".mov"}:
                if video_codec in {None, "", "h264"}:
                    cmd += ["-c:v", "h264_nvenc", "-preset", "p4"]
                elif video_codec in {"h265", "hevc"} and ffmpeg_has_encoder("hevc_nvenc"):
                    cmd += ["-c:v", "hevc_nvenc", "-preset", "p4"]
                else:
                    cmd += ["-c:v", "h264_nvenc", "-preset", "p4"]
                # Map CRF to a reasonable CQ default if not provided
                cq = "23"
                try:
                    if video_crf:
                        cq = str(int(float(video_crf)))
                except Exception:
                    pass
                cmd += ["-cq", cq]
                default_audio_codec = "aac"
            elif out_ext == ".webm" or video_codec == "vp9":
                cmd += ["-c:v", "libvpx-vp9", "-crf", str(video_crf or 32), "-b:v", "0"]
                default_audio_codec = "libopus"
            else:
                if video_codec in {"h265", "hevc"}:
                    cmd += ["-c:v", "libx265", "-preset", "medium", "-crf", str(video_crf or 26)]
                else:
                    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(video_crf or 20)]
                default_audio_codec = "aac"

            resolved_audio = _resolve_audio_codec(audio_codec)
            if resolved_audio == "copy":
                cmd += ["-c:a", "copy"]
            elif resolved_audio:
                cmd += ["-c:a", resolved_audio]
            elif video_codec == "copy":
                cmd += ["-c:a", "copy"]
            elif default_audio_codec:
                cmd += ["-c:a", default_audio_codec]

            if audio_bitrate and resolved_audio != "copy":
                cmd += ["-b:a", str(audio_bitrate)]
            if preserve_metadata:
                cmd += ["-map_metadata", "0"]
        cmd += [
            str(out_path),
        ]

        def run_ffmpeg_cancelable() -> tuple[bool, str]:
            try:
                duration_s = get_duration_seconds(p) if callable(file_progress_cb) else None
                use_progress = bool(duration_s and duration_s > 0 and callable(file_progress_cb))

                cmd_run = list(cmd)
                if use_progress:
                    cmd_run = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + cmd[1:]

                stderr_buf: list[str] = []
                last_frac_box = {"v": -1.0}

                proc = subprocess.Popen(
                    cmd_run,
                    stdout=subprocess.PIPE if use_progress else subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **_subprocess_kwargs(),
                )

                def drain_stderr():
                    try:
                        if not proc.stderr:
                            return
                        for line in proc.stderr:
                            if line:
                                stderr_buf.append(line)
                                if sum(len(x) for x in stderr_buf) > 6000:
                                    stderr_buf[:] = stderr_buf[-50:]
                    except Exception:
                        pass

                def read_progress():
                    try:
                        if not (use_progress and proc.stdout):
                            return
                        for line in proc.stdout:
                            if cancel_event and cancel_event.is_set():
                                return
                            key, sep, val = line.strip().partition("=")
                            if sep != "=":
                                continue
                            if key in {"out_time_ms", "out_time_us", "out_time"}:
                                try:
                                    if key == "out_time":
                                        parts = val.split(":")
                                        if len(parts) == 3:
                                            t = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                                        else:
                                            continue
                                    else:
                                        # ffmpeg's `-progress` uses confusing names; in practice out_time_ms is microseconds.
                                        t = float(val) / (1_000_000.0 if key in {"out_time_ms", "out_time_us"} else 1_000.0)
                                    frac = 0.0 if not duration_s else max(0.0, min(1.0, t / duration_s))
                                    if proc.poll() is None and frac >= 0.999:
                                        frac = 0.99
                                    last = float(last_frac_box["v"])
                                    if frac - last >= 0.01 or frac in {0.0, 1.0}:
                                        last_frac_box["v"] = frac
                                        try:
                                            file_progress_cb(p, frac)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                    except Exception:
                        pass

                threading.Thread(target=drain_stderr, daemon=True).start()
                if use_progress:
                    threading.Thread(target=read_progress, daemon=True).start()

                while True:
                    if cancel_event and cancel_event.is_set():
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        try:
                            proc.wait(timeout=5)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                        return False, "Cancelled."

                    rc = proc.poll()
                    if rc is not None:
                        if rc == 0:
                            try:
                                if callable(file_progress_cb):
                                    file_progress_cb(p, 1.0)
                            except Exception:
                                pass
                            return True, ""
                        err = "".join(stderr_buf).strip()
                        return False, (err or f"ffmpeg failed with code {rc}")[:1200]
                    threading.Event().wait(0.15)
            except Exception as e:
                return False, str(e)

        try:
            ok_run, msg = run_ffmpeg_cancelable()
            if not ok_run:
                if msg.strip().lower().startswith("cancel"):
                    return MediaConvertResult(ok=False, message="Cancelled.", converted=converted, skipped=skipped, output_dir=str(out_dir))
                raise RuntimeError(msg)
            if preserve_cover_art and output_format == "mp3" and cover:
                ensure_mp3_cover_art(out_path, cover)
            converted += 1
        except Exception:
            skipped += 1

    return MediaConvertResult(
        ok=True,
        message=f"Converted {converted} media files (skipped {skipped}).",
        converted=converted,
        skipped=skipped,
        output_dir=str(out_dir),
    )
