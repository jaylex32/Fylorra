"""
Fylorra - Media Tools (ffmpeg)
Single-file conversions and simple editing operations.
"""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re

from core.ffmpeg_manager import ffmpeg_has_encoder, get_ffmpeg_exe, get_ffprobe_exe
from core.time_parse import parse_timestamp_to_seconds
from core.tag_tools import ensure_mp3_cover_art, extract_cover_art


@dataclass(frozen=True)
class MediaOpResult:
    ok: bool
    message: str
    output_path: Optional[str] = None


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


def convert_media_file(
    input_path: Path,
    *,
    output_path: Path,
    overwrite: bool = False,
    audio_bitrate: str | None = None,
    video_crf: str | None = None,
    video_codec: str | None = None,
    scale_height: int | None = None,
    audio_codec: str | None = None,
    use_gpu: bool = False,
    preserve_metadata: bool = True,
    preserve_cover_art: bool = True,
    cancel_event=None,
    progress_cb=None,  # callable(frac: float) -> None (0..1)
) -> MediaOpResult:
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return MediaOpResult(ok=False, message="ffmpeg not available. Install 'imageio-ffmpeg' or set FYLORRA_FFMPEG.")

    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        return MediaOpResult(ok=False, message="Input file not found.")
    if output_path.exists() and not overwrite:
        return MediaOpResult(ok=False, message=f"Output already exists: {output_path.name}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    def get_duration_seconds(media_path: Path) -> float | None:
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

    cmd = [str(ffmpeg), "-y" if overwrite else "-n", "-i", str(input_path)]
    # If output is mp3 and bitrate requested, force libmp3lame and CBR to match user expectation.
    out_ext = output_path.suffix.lower()
    in_ext = input_path.suffix.lower()
    is_video_input = in_ext in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"}
    video_codec = (video_codec or "").strip().lower() or None

    if (
        scale_height
        and int(scale_height) > 0
        and (is_video_input or out_ext in {".mp4", ".mkv", ".mov", ".webm", ".avi", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"})
        and video_codec != "copy"
    ):
        cmd += ["-vf", f"scale=-2:{int(scale_height)}"]

    audio_only_out = out_ext in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".alac"}
    lossy_audio_out = out_ext in {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
    audio_codec = (audio_codec or "").strip().lower() or None

    def _audio_codec_for_format(ext: str) -> str | None:
        ext = (ext or "").strip().lower()
        if ext in {".m4a", ".aac"}:
            if ffmpeg_has_encoder("aac"):
                return "aac"
            if ffmpeg_has_encoder("libfdk_aac"):
                return "libfdk_aac"
            return None
        if ext == ".flac":
            return "flac"
        if ext == ".wav":
            return "pcm_s16le"
        if ext == ".aiff":
            return "pcm_s16le"
        if ext == ".alac":
            return "alac"
        if ext == ".wma":
            return "wmav2"
        if ext == ".ogg":
            if ffmpeg_has_encoder("libvorbis"):
                return "libvorbis"
            if ffmpeg_has_encoder("vorbis"):
                return "vorbis"
            if ffmpeg_has_encoder("libopus"):
                return "libopus"
            return None
        if ext == ".opus":
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

    if out_ext == ".mp3":
        cover = extract_cover_art(input_path) if preserve_cover_art else None
        if preserve_metadata:
            cmd += ["-map_metadata", "0"]
        cmd += ["-map", "0:a:0"]

        cmd += ["-c:a", "libmp3lame", "-id3v2_version", "3", "-write_id3v1", "1"]
        if audio_bitrate:
            cmd += ["-b:a", str(audio_bitrate), "-minrate", str(audio_bitrate), "-maxrate", str(audio_bitrate), "-bufsize", str(audio_bitrate)]
        cmd.append(str(output_path))
        try:
            duration_s = get_duration_seconds(input_path) if callable(progress_cb) else None
            use_progress = bool(duration_s and duration_s > 0 and callable(progress_cb))
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
                        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
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
                                # Avoid showing 100% while ffmpeg is still running.
                                if proc.poll() is None and frac >= 0.999:
                                    frac = 0.99
                                last = float(last_frac_box["v"])
                                if frac - last >= 0.01 or frac in {0.0, 1.0}:
                                    last_frac_box["v"] = frac
                                    try:
                                        progress_cb(frac)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                except Exception:
                    pass

            t_err = threading.Thread(target=drain_stderr, daemon=True)
            t_err.start()
            t_prog = threading.Thread(target=read_progress, daemon=True) if use_progress else None
            if t_prog:
                t_prog.start()

            while True:
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    return MediaOpResult(ok=False, message="Cancelled.")
                rc = proc.poll()
                if rc is not None:
                    if rc == 0:
                        try:
                            if callable(progress_cb):
                                progress_cb(1.0)
                        except Exception:
                            pass
                        break
                    err = "".join(stderr_buf).strip()
                    return MediaOpResult(ok=False, message=(err or f"ffmpeg failed with code {rc}")[:1200])
                threading.Event().wait(0.15)

            if cover:
                ensure_mp3_cover_art(output_path, cover)
            return MediaOpResult(ok=True, message="Converted.", output_path=str(output_path))
        except Exception as e:
            return MediaOpResult(ok=False, message=str(e))
    else:
        if audio_only_out:
            if preserve_metadata:
                cmd += ["-map_metadata", "0"]
            cover_supported = out_ext in {".m4a", ".m4b", ".flac", ".ogg", ".opus"}
            if preserve_cover_art and cover_supported and not is_video_input:
                cmd += ["-map", "0:a:0", "-map", "0:v:0?", "-c:v", "copy"]
            else:
                cmd += ["-vn", "-map", "0:a:0"]
            codec = _audio_codec_for_format(out_ext)
            if codec:
                cmd += ["-c:a", codec]
            if audio_bitrate and lossy_audio_out:
                cmd += ["-b:a", str(audio_bitrate)]
        else:
            pass
    if out_ext in {".mp4", ".mkv", ".mov", ".webm", ".avi", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"}:
        # Choose deterministic video encoding
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
            # CRF -> CQ
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
        elif video_codec in {"h265", "hevc"}:
            cmd += ["-c:v", "libx265", "-preset", "medium", "-crf", str(video_crf or 26)]
            default_audio_codec = "aac"
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
    elif video_crf:
        cmd += ["-crf", str(video_crf)]
    cmd.append(str(output_path))

    try:
        duration_s = get_duration_seconds(input_path) if callable(progress_cb) else None
        use_progress = bool(duration_s and duration_s > 0 and callable(progress_cb))
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
                    if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
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
                                t = float(val) / (1_000_000.0 if key in {"out_time_ms", "out_time_us"} else 1_000.0)
                            frac = 0.0 if not duration_s else max(0.0, min(1.0, t / duration_s))
                            if proc.poll() is None and frac >= 0.999:
                                frac = 0.99
                            last = float(last_frac_box["v"])
                            if frac - last >= 0.01 or frac in {0.0, 1.0}:
                                last_frac_box["v"] = frac
                                try:
                                    progress_cb(frac)
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                pass

        t_err = threading.Thread(target=drain_stderr, daemon=True)
        t_err.start()
        t_prog = threading.Thread(target=read_progress, daemon=True) if use_progress else None
        if t_prog:
            t_prog.start()

        while True:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                try:
                    proc.terminate()
                except Exception:
                    pass
                return MediaOpResult(ok=False, message="Cancelled.")
            rc = proc.poll()
            if rc is not None:
                if rc == 0:
                    try:
                        if callable(progress_cb):
                            progress_cb(1.0)
                    except Exception:
                        pass
                    break
                err = "".join(stderr_buf).strip()
                return MediaOpResult(ok=False, message=(err or f"ffmpeg failed with code {rc}")[:1200])
            threading.Event().wait(0.15)
        return MediaOpResult(ok=True, message="Converted.", output_path=str(output_path))
    except Exception as e:
        return MediaOpResult(ok=False, message=str(e))


def cut_video_segment(
    input_path: Path,
    *,
    output_path: Path,
    start: str,
    end: str | None = None,
    duration: str | None = None,
    overwrite: bool = False,
    reencode: bool = False,
    audio_bitrate: str | None = None,
) -> MediaOpResult:
    """
    Cut a segment starting at `start` with either `end` or `duration`.
    If reencode=False, uses stream copy (fast, may cut on keyframes).
    """
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return MediaOpResult(ok=False, message="ffmpeg not available. Install 'imageio-ffmpeg' or set FYLORRA_FFMPEG.")

    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        return MediaOpResult(ok=False, message="Input file not found.")
    if output_path.exists() and not overwrite:
        return MediaOpResult(ok=False, message=f"Output already exists: {output_path.name}")

    start_s = parse_timestamp_to_seconds(start)
    if duration and end:
        return MediaOpResult(ok=False, message="Provide either end or duration, not both.")
    if end:
        end_s = parse_timestamp_to_seconds(end)
        if end_s <= start_s:
            return MediaOpResult(ok=False, message="End time must be after start time.")
        dur_s = end_s - start_s
    elif duration:
        dur_s = parse_timestamp_to_seconds(duration)
        if dur_s <= 0:
            return MediaOpResult(ok=False, message="Duration must be > 0.")
    else:
        return MediaOpResult(ok=False, message="Provide end or duration.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # If output container differs, stream-copy is usually invalid.
    if not reencode and input_path.suffix.lower() != output_path.suffix.lower():
        reencode = True

    cmd = [
        str(ffmpeg),
        "-y" if overwrite else "-n",
        "-ss",
        str(start_s),
        "-i",
        str(input_path),
        "-t",
        str(dur_s),
    ]
    out_ext = output_path.suffix.lower()
    if not reencode:
        cmd += ["-c", "copy"]
    else:
        # Audio-only outputs (e.g. ringtone.mp3)
        if out_ext in {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}:
            cmd += ["-vn"]
            if out_ext == ".mp3":
                cmd += ["-c:a", "libmp3lame"]
                if audio_bitrate:
                    cmd += ["-b:a", str(audio_bitrate)]
            elif out_ext == ".m4a":
                cmd += ["-c:a", "aac"]
            else:
                cmd += ["-c:a", "aac"]
        else:
            # Video outputs (mp4/mkv/etc): use a broadly compatible encode.
            # This avoids failures when container differs or when precise cut is requested.
            if out_ext == ".webm":
                cmd += ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"]
            else:
                cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac"]
                if audio_bitrate:
                    cmd += ["-b:a", str(audio_bitrate)]
    cmd.append(str(output_path))

    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            **_subprocess_kwargs(),
        )
        return MediaOpResult(ok=True, message="Cut complete.", output_path=str(output_path))
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e)).strip()
        return MediaOpResult(ok=False, message=msg[:1200])
    except Exception as e:
        return MediaOpResult(ok=False, message=str(e))
