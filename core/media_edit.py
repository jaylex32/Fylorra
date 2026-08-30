"""
Fylorra - Media Edit (ffmpeg)
Lightweight single-file audio/video editing wrappers with progress + cancel.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import json

from core.ffmpeg_manager import ffmpeg_has_encoder, get_ffmpeg_exe, get_ffprobe_exe
from core.time_parse import parse_timestamp_to_seconds
from core.tag_tools import ensure_mp3_cover_art, extract_cover_art


@dataclass(frozen=True)
class MediaEditRequest:
    input_path: Path
    output_path: Path
    overwrite: bool = False

    # Trim
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None

    # Audio
    audio_codec: Optional[str] = None  # e.g. "aac", "libmp3lame", "flac", "pcm_s16le"
    audio_bitrate: Optional[str] = None  # e.g. "320k"
    volume_db: Optional[float] = None  # +dB / -dB
    normalize: bool = False
    fade_in_seconds: Optional[float] = None
    fade_out_seconds: Optional[float] = None
    # Optional: apply fades at specific timestamps (seconds) instead of only at 0/end.
    fade_in_at_seconds: Optional[float] = None
    fade_out_at_seconds: Optional[float] = None
    # Optional: apply multiple fades at specific timestamps (post-trim/post-cut timeline).
    # Items are ("in"|"out", start_seconds, duration_seconds).
    audio_fade_regions: Optional[list[tuple[str, float, float]]] = None
    # Optional: remove multiple segments from audio (absolute seconds in original media).
    audio_remove_segments: Optional[list[tuple[float, float]]] = None
    preserve_cover_art: bool = True

    # Video
    video_codec: Optional[str] = None  # "h264", "h265", "vp9"
    video_crf: Optional[str] = None
    scale_height: Optional[int] = None
    fps: Optional[int] = None
    use_gpu: bool = False
    video_filters: Optional[list[str]] = None


@dataclass(frozen=True)
class MediaEditResult:
    ok: bool
    message: str
    output_path: Optional[str] = None


@dataclass(frozen=True)
class TimelineClip:
    path: Path
    kind: str = "video"  # "video" | "image" | "audio"
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None  # for images (or explicit durations)
    timeline_start_seconds: Optional[float] = None  # for audio clips on separate track
    volume_db: Optional[float] = None
    fade_in_seconds: Optional[float] = None
    fade_out_seconds: Optional[float] = None
    loop: bool = False


def _is_image_path(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def _image_exif_rotation_deg(path: Path) -> int:
    try:
        from PIL import Image
    except Exception:
        return 0
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            orient = int(exif.get(274, 1)) if exif else 1
    except Exception:
        return 0
    if orient == 3:
        return 180
    if orient == 6:
        return 90
    if orient == 8:
        return 270
    return 0


def _rotation_filter_for_deg(deg: int) -> str:
    d = int(deg) % 360
    if d == 90:
        return "transpose=1"
    if d == 180:
        return "transpose=1,transpose=1"
    if d == 270:
        return "transpose=2"
    return ""


def _subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    try:
        kwargs: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si
        return kwargs
    except Exception:
        return {}


def probe_has_audio(path: Path) -> bool:
    if _is_image_path(Path(path)):
        return False
    ffprobe = get_ffprobe_exe()
    if not ffprobe:
        return False
    try:
        proc = subprocess.run(
            [str(ffprobe), "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "default=nw=1:nk=1", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            **_subprocess_kwargs(),
        )
        out = (proc.stdout or "").strip()
        return bool(out)
    except Exception:
        return False


def render_video_timeline(
    clips: list[TimelineClip],
    *,
    output_path: Path,
    overwrite: bool = False,
    output_format: str = "mp4",
    video_codec: str = "h264",
    video_crf: str | None = None,
    scale_height: int | None = None,
    fps: int | None = None,
    use_gpu: bool = False,
    include_audio: bool = True,
    include_video_audio: bool = True,
    audio_clips: list[TimelineClip] | None = None,
    audio_bed_path: Path | None = None,
    transition: str | None = None,
    transition_duration: float | None = None,
    transitions: list[tuple[str | None, float]] | None = None,
    video_filters: list[str] | None = None,
    image_rotations: dict[str, int] | None = None,
    cancel_event=None,
    progress_cb=None,  # callable(frac: float, msg: str)
) -> MediaEditResult:
    """
    Render a sequential multi-clip timeline (single video track) using ffmpeg filter_complex concat.
    Always re-encodes for determinism and to support trims/scales/fps changes.
    """
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return MediaEditResult(ok=False, message="ffmpeg not available. Install 'imageio-ffmpeg' or set FYLORRA_FFMPEG.")
    if not clips:
        return MediaEditResult(ok=False, message="No clips in timeline.")

    output_path = Path(output_path)
    if output_path.exists() and not overwrite:
        return MediaEditResult(ok=False, message=f"Output already exists: {output_path.name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Total duration (best-effort) for progress.
    total_dur = 0.0
    for c in clips:
        p = Path(c.path)
        if c.duration_seconds and float(c.duration_seconds) > 0:
            total_dur += float(c.duration_seconds)
            continue
        if (c.kind or "").lower() == "image" or _is_image_path(p):
            total_dur += 3.0
            continue
        dur = _duration_seconds(p) or 0.0
        s = float(c.start_seconds or 0.0)
        e = float(c.end_seconds) if c.end_seconds is not None else dur
        if dur > 0:
            e = min(e, dur)
        span = max(0.0, e - s) if e > 0 else 0.0
        total_dur += span

    cmd = [str(ffmpeg), "-hide_banner", "-y" if overwrite else "-n"]
    for c in clips:
        p = Path(c.path)
        if (c.kind or "").lower() == "image" or _is_image_path(p):
            d = float(c.duration_seconds or 3.0)
            d = 3.0 if d <= 0 else d
            cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(p)]
        else:
            cmd += ["-i", str(p)]

    audio_input_start = len(clips)
    if audio_clips:
        for ac in audio_clips:
            cmd += ["-i", str(Path(ac.path))]

    audio_index = None
    if audio_bed_path:
        audio_index = len(clips) + (len(audio_clips) if audio_clips else 0)
        cmd += ["-stream_loop", "-1", "-i", str(Path(audio_bed_path))]

    vfilters: list[str] = []
    afilters: list[str] = []
    vlabels: list[str] = []
    alabels: list[str] = []
    clip_durations: list[float] = []

    all_have_audio = True
    if include_audio and include_video_audio and not audio_bed_path:
        for c in clips:
            p = Path(c.path)
            if (c.kind or "").lower() == "image" or _is_image_path(p):
                all_have_audio = False
                break
            if not probe_has_audio(p):
                all_have_audio = False
                break

    for i, c in enumerate(clips):
        p = Path(c.path)
        is_img = (c.kind or "").lower() == "image" or _is_image_path(p)
        s = 0.0 if is_img else float(c.start_seconds or 0.0)
        e = None
        if is_img:
            d = float(c.duration_seconds or 3.0)
            d = 3.0 if d <= 0 else d
            e = d
        else:
            e = float(c.end_seconds) if c.end_seconds is not None else None
            if e is not None and e <= s:
                e = None
        dur_total = 0.0
        clip_dur = 0.0
        if is_img:
            clip_dur = float(e or 0.0)
        else:
            try:
                dur_total = _duration_seconds(p) or 0.0
            except Exception:
                dur_total = 0.0
            if e is not None:
                clip_dur = max(0.05, float(e) - float(s))
            elif dur_total > 0:
                clip_dur = max(0.05, float(dur_total) - float(s))
            else:
                clip_dur = 5.0
        clip_durations.append(float(clip_dur))

        v = f"[{i}:v]trim=start={s}"
        if e is not None:
            v += f":end={e}"
        v += ",setpts=PTS-STARTPTS"
        if is_img:
            rot = _image_exif_rotation_deg(p)
            if image_rotations:
                try:
                    rot += int(image_rotations.get(str(p), image_rotations.get(p, 0)))
                except Exception:
                    pass
            rot = rot % 360
            rf = _rotation_filter_for_deg(rot)
            if rf:
                v += f",{rf}"
        if scale_height and int(scale_height) > 0:
            v += f",scale=-2:{int(scale_height)}"
        if fps and int(fps) > 0:
            v += f",fps={int(fps)}"
        vout = f"[v{i}]"
        vfilters.append(v + vout)
        vlabels.append(vout)

        if include_audio and include_video_audio and all_have_audio and not audio_bed_path:
            a = f"[{i}:a]atrim=start={s}"
            if e is not None:
                a += f":end={e}"
            a += ",asetpts=PTS-STARTPTS"
            aout = f"[a{i}]"
            afilters.append(a + aout)
            alabels.append(aout)

    transition_name = (transition or "").strip().lower()
    if transition_name in {"", "none"}:
        transition_name = None
    try:
        td = float(transition_duration or 0.0)
    except Exception:
        td = 0.0

    filter_parts = []
    maps: list[str] = []
    transition_seq: list[tuple[str | None, float]] = []
    if transitions:
        for i in range(max(0, len(vlabels) - 1)):
            if i < len(transitions):
                name, dur = transitions[i]
            else:
                name, dur = transition_name, td
            key = (name or "").strip().lower()
            if key in {"", "none", "clear"}:
                name = None
            else:
                name = key
            try:
                dur = float(dur or 0.0)
            except Exception:
                dur = 0.0
            transition_seq.append((name, max(0.0, float(dur))))
    elif transition_name and td > 0.0 and len(vlabels) > 1:
        transition_seq = [(transition_name, float(td)) for _ in range(len(vlabels) - 1)]
    else:
        transition_seq = [(None, 0.0) for _ in range(max(0, len(vlabels) - 1))]

    has_any_transition = any((nm and float(dur) > 0.01) for nm, dur in transition_seq)
    if has_any_transition and len(vlabels) > 1:
        comb_v_parts: list[str] = []
        cur_label = vlabels[0]
        cur_dur = float(clip_durations[0] if clip_durations else 0.0)
        for i in range(1, len(vlabels)):
            name, dur = transition_seq[i - 1] if (i - 1) < len(transition_seq) else (None, 0.0)
            try:
                dur = float(dur or 0.0)
            except Exception:
                dur = 0.0
            use_xfade = bool(name and dur > 0.0)
            pair_td = 0.0
            if use_xfade:
                prev_dur = float(clip_durations[i - 1] or 0.0)
                cur_dur_clip = float(clip_durations[i] or 0.0)
                pair_td = min(dur, prev_dur * 0.5, cur_dur_clip * 0.5)
                if pair_td < 0.05:
                    use_xfade = False
            if use_xfade:
                offset = max(0.0, cur_dur - pair_td)
                out_label = "[vout]" if i == (len(vlabels) - 1) else f"[vxf{i}]"
                comb_v_parts.append(
                    f"{cur_label}{vlabels[i]}xfade=transition={name}:duration={pair_td:.3f}:offset={offset:.3f}{out_label}"
                )
                cur_dur = cur_dur + float(clip_durations[i]) - pair_td
            else:
                out_label = "[vout]" if i == (len(vlabels) - 1) else f"[vcat{i}]"
                comb_v_parts.append(f"{cur_label}{vlabels[i]}concat=n=2:v=1:a=0{out_label}")
                cur_dur = cur_dur + float(clip_durations[i])
            cur_label = out_label
        filter_parts = vfilters + comb_v_parts
        maps = ["-map", "[vout]"]

        if include_audio and include_video_audio and all_have_audio and alabels and not audio_bed_path:
            comb_a_parts: list[str] = []
            cur_a = alabels[0]
            for i in range(1, len(alabels)):
                name, dur = transition_seq[i - 1] if (i - 1) < len(transition_seq) else (None, 0.0)
                try:
                    dur = float(dur or 0.0)
                except Exception:
                    dur = 0.0
                use_xfade = bool(name and dur > 0.0)
                pair_td = 0.0
                if use_xfade:
                    prev_dur = float(clip_durations[i - 1] or 0.0)
                    cur_dur_clip = float(clip_durations[i] or 0.0)
                    pair_td = min(dur, prev_dur * 0.5, cur_dur_clip * 0.5)
                    if pair_td < 0.05:
                        use_xfade = False
                if use_xfade:
                    out_label = "[aout]" if i == (len(alabels) - 1) else f"[axf{i}]"
                    comb_a_parts.append(f"{cur_a}{alabels[i]}acrossfade=d={pair_td:.3f}:c1=tri:c2=tri{out_label}")
                else:
                    out_label = "[aout]" if i == (len(alabels) - 1) else f"[acat{i}]"
                    comb_a_parts.append(f"{cur_a}{alabels[i]}concat=n=2:v=0:a=1{out_label}")
                cur_a = out_label
            filter_parts = vfilters + afilters + comb_v_parts + comb_a_parts
            maps += ["-map", "[aout]"]
    else:
        concat_v = "".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[vout]"
        filter_parts = vfilters + [concat_v]
        maps = ["-map", "[vout]"]

        if include_audio and include_video_audio and all_have_audio and alabels and not audio_bed_path:
            concat_a = "".join(alabels) + f"concat=n={len(alabels)}:v=0:a=1[aout]"
            filter_parts = vfilters + afilters + [concat_v, concat_a]
            maps += ["-map", "[aout]"]

    # Optional audio bed (looped) for slideshows or muted clips. (looped) for slideshows or muted clips.
    if include_audio and audio_bed_path and audio_index is not None:
        if total_dur and total_dur > 0:
            filter_parts = list(filter_parts) + [f"[{audio_index}:a]atrim=start=0:end={total_dur:.3f},asetpts=PTS-STARTPTS[audbed]"]
            maps += ["-map", "[audbed]"]
        else:
            maps += ["-map", f"{audio_index}:a:0"]

    # Optional audio track clips (mixed over base).
    if include_audio and audio_clips:
        base_labels: list[str] = []
        # Preserve any existing mapped audio (aout / audbed) by labeling into mix.
        # If maps already includes an audio label, use it.
        if "[aout]" in maps:
            base_labels.append("[aout]")
        if "[audbed]" in maps:
            base_labels.append("[audbed]")

        # Remove existing audio map targets; we will output a mixed audio label.
        cleaned_maps: list[str] = []
        it = iter(maps)
        for token in it:
            if token == "-map":
                tgt = next(it, "")
                if tgt in {"[aout]", "[audbed]"}:
                    continue
                cleaned_maps += ["-map", tgt]
            else:
                cleaned_maps.append(token)
        maps = cleaned_maps

        at_parts: list[str] = []
        mix_inputs: list[str] = []
        if base_labels:
            # If multiple base labels, mix them first.
            if len(base_labels) == 1:
                mix_inputs.append(base_labels[0])
            else:
                base_mix = "".join(base_labels) + f"amix=inputs={len(base_labels)}:normalize=0[abase]"
                at_parts.append(base_mix)
                mix_inputs.append("[abase]")

        for j, ac in enumerate(audio_clips):
            idx_in = audio_input_start + j
            s = float(ac.start_seconds or 0.0)
            e = float(ac.end_seconds) if ac.end_seconds is not None else None
            if e is not None and e <= s:
                e = None
            chain = f"[{idx_in}:a]atrim=start={s}"
            if e is not None:
                chain += f":end={e}"
            chain += ",asetpts=PTS-STARTPTS"
            if ac.volume_db is not None:
                chain += f",volume={float(ac.volume_db)}dB"
            if ac.fade_in_seconds and ac.fade_in_seconds > 0:
                chain += f",afade=t=in:st=0:d={float(ac.fade_in_seconds)}"
            if ac.fade_out_seconds and ac.fade_out_seconds > 0:
                # Fade-out time requires knowing clip duration; best-effort if end specified.
                if e is not None:
                    st = max(0.0, float(e - s) - float(ac.fade_out_seconds))
                    chain += f",afade=t=out:st={st:.3f}:d={float(ac.fade_out_seconds)}"
            if ac.timeline_start_seconds and ac.timeline_start_seconds > 0:
                ms = int(float(ac.timeline_start_seconds) * 1000.0)
                chain += f",adelay={ms}|{ms}"
            lbl = f"[atr{j}]"
            at_parts.append(chain + lbl)
            mix_inputs.append(lbl)

        if mix_inputs:
            # Mix all sources down to aout2
            mix = "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:normalize=0[aout2]"
            filter_parts = list(filter_parts) + at_parts + [mix]
            maps += ["-map", "[aout2]"]

    if video_filters:
        vf_chain = []
        for vf in list(video_filters):
            v = str(vf or "").strip()
            if v:
                vf_chain.append(v)
        if vf_chain:
            filter_parts = list(filter_parts) + [f"[vout]{','.join(vf_chain)}[vfx]"]
            for i in range(len(maps) - 1):
                if maps[i] == '-map' and maps[i + 1] == '[vout]':
                    maps[i + 1] = '[vfx]'

    cmd += ["-filter_complex", ";".join(filter_parts)]
    cmd += maps

    out_ext = "." + str(output_format).lower().lstrip(".")
    vc = (video_codec or "h264").strip().lower()

    if use_gpu and ffmpeg_has_encoder("h264_nvenc") and out_ext in {".mp4", ".mkv", ".mov"}:
        if vc in {"h265", "hevc"} and ffmpeg_has_encoder("hevc_nvenc"):
            cmd += ["-c:v", "hevc_nvenc", "-preset", "p4"]
        else:
            cmd += ["-c:v", "h264_nvenc", "-preset", "p4"]
        cq = "23"
        try:
            if video_crf:
                cq = str(int(float(video_crf)))
        except Exception:
            pass
        cmd += ["-cq", cq]
    elif out_ext == ".webm" or vc == "vp9":
        cmd += ["-c:v", "libvpx-vp9", "-crf", str(video_crf or 32), "-b:v", "0"]
    elif vc == "av1":
        cmd += ["-c:v", "libaom-av1", "-crf", str(video_crf or 32), "-b:v", "0", "-cpu-used", "6"]
    elif vc in {"h265", "hevc"}:
        cmd += ["-c:v", "libx265", "-preset", "medium", "-crf", str(video_crf or 26)]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(video_crf or 20)]

    has_audio_out = include_audio and (
        ("-map" in maps and any(t in {"[aout]", "[audbed]", "[aout2]"} for t in maps))
        or (include_video_audio and all_have_audio and alabels and not audio_bed_path)
        or bool(audio_bed_path)
        or bool(audio_clips)
    )
    if has_audio_out:
        if out_ext == ".webm":
            cmd += ["-c:a", "libopus"]
        else:
            cmd += ["-c:a", "aac"]
        cmd += ["-shortest"]
    else:
        cmd += ["-an"]

    use_progress = bool(total_dur and callable(progress_cb))
    cmd_run = list(cmd) + [str(output_path)]
    if use_progress:
        cmd_run = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + cmd_run[1:]

    stderr_buf: list[str] = []
    last_frac_box = {"v": -1.0}

    def drain_stderr():
        try:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_buf.append(line)
                if len(stderr_buf) > 500:
                    del stderr_buf[:100]
        except Exception:
            pass

    def read_progress():
        try:
            if proc.stdout is None:
                return
            dur = float(total_dur or 0.0)
            for raw in proc.stdout:
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    return
                line = (raw or "").strip()
                if not line or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if key not in {"out_time_ms", "out_time_us", "out_time"}:
                    continue
                t = None
                try:
                    if key == "out_time":
                        parts = val.split(":")
                        if len(parts) == 3:
                            t = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    else:
                        t = float(val) / 1_000_000.0
                except Exception:
                    t = None
                if t is None or dur <= 0:
                    continue
                frac = max(0.0, min(1.0, float(t) / dur))
                if proc.poll() is None and frac >= 0.999:
                    frac = 0.99
                last = float(last_frac_box["v"])
                if frac - last >= 0.01 or frac in {0.0, 1.0}:
                    last_frac_box["v"] = frac
                    try:
                        progress_cb(frac, "Rendering timeline…")
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            cmd_run,
            stdout=subprocess.PIPE if use_progress else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_kwargs(),
        )
    except Exception as e:
        return MediaEditResult(ok=False, message=str(e))

    threading.Thread(target=drain_stderr, daemon=True).start()
    if use_progress:
        threading.Thread(target=read_progress, daemon=True).start()

    while True:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            try:
                proc.terminate()
            except Exception:
                pass
            return MediaEditResult(ok=False, message="Cancelled.")
        rc = proc.poll()
        if rc is not None:
            if rc == 0:
                try:
                    if callable(progress_cb):
                        progress_cb(1.0, "Done.")
                except Exception:
                    pass
                break
            err = "".join(stderr_buf).strip()
            return MediaEditResult(ok=False, message=(err or f"ffmpeg failed with code {rc}")[:1400])
        threading.Event().wait(0.15)

    msg = "Rendered timeline."
    if include_audio and not all_have_audio:
        msg += " (No audio: one or more clips have no audio stream.)"
    return MediaEditResult(ok=True, message=msg, output_path=str(output_path))


def _duration_seconds(media_path: Path) -> Optional[float]:
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
                return dur if dur >= 0.5 else None
        except Exception:
            pass
    return None


def _parse_time(v: Optional[str | float]) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        pass
    try:
        return float(parse_timestamp_to_seconds(s))
    except Exception:
        return None


def edit_media(
    req: MediaEditRequest,
    *,
    cancel_event=None,
    progress_cb=None,  # callable(frac: float, msg: str) -> None
) -> MediaEditResult:
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return MediaEditResult(ok=False, message="ffmpeg not available. Install 'imageio-ffmpeg' or set FYLORRA_FFMPEG.")

    inp = Path(req.input_path)
    outp = Path(req.output_path)
    if not inp.exists():
        return MediaEditResult(ok=False, message="Input file not found.")
    if outp.exists() and not req.overwrite:
        return MediaEditResult(ok=False, message=f"Output already exists: {outp.name}")
    outp.parent.mkdir(parents=True, exist_ok=True)

    start_s = req.start_seconds
    end_s = req.end_seconds
    if start_s is not None and end_s is not None and end_s <= start_s:
        return MediaEditResult(ok=False, message="End time must be after start time.")

    duration_total = _duration_seconds(inp) or None
    duration_span = None
    if duration_total and start_s is not None:
        duration_span = max(0.0, duration_total - float(start_s))
    if duration_total and start_s is not None and end_s is not None:
        duration_span = max(0.0, float(end_s) - float(start_s))

    # Build filters
    afilters: list[str] = []
    vfilters: list[str] = []

    if req.volume_db is not None:
        afilters.append(f"volume={float(req.volume_db)}dB")
    if req.normalize:
        afilters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
    # NOTE: fade *_at_seconds are expected to be relative to the exported segment (after trim/cut),
    # so we do not offset them again by req.start_seconds here.
    if req.fade_in_seconds and req.fade_in_seconds > 0:
        st = float(req.fade_in_at_seconds) if req.fade_in_at_seconds is not None else 0.0
        if duration_span:
            st = min(max(0.0, st), max(0.0, float(duration_span) - 0.001))
        afilters.append(f"afade=t=in:st={max(0.0, st):.3f}:d={float(req.fade_in_seconds)}")
    if req.fade_out_seconds and req.fade_out_seconds > 0 and (duration_span or req.fade_out_at_seconds is not None):
        if req.fade_out_at_seconds is not None:
            st = max(0.0, float(req.fade_out_at_seconds))
        else:
            st = max(0.0, float(duration_span) - float(req.fade_out_seconds))  # type: ignore[arg-type]
        if duration_span:
            st = min(st, max(0.0, float(duration_span) - 0.001))
        afilters.append(f"afade=t=out:st={max(0.0, st):.3f}:d={float(req.fade_out_seconds)}")
    # Additional per-region fades (post-trim timeline).
    if req.audio_fade_regions:
        for t, st, d in list(req.audio_fade_regions):
            tt = (str(t or "")).strip().lower()
            if tt not in {"in", "out"}:
                continue
            try:
                st_f = max(0.0, float(st))
                d_f = max(0.0, float(d))
            except Exception:
                continue
            if d_f <= 0.001:
                continue
            if duration_span:
                st_f = min(st_f, max(0.0, float(duration_span) - 0.001))
            afilters.append(f"afade=t={tt}:st={st_f:.3f}:d={d_f:.3f}")

    if req.scale_height and int(req.scale_height) > 0:
        vfilters.append(f"scale=-2:{int(req.scale_height)}")
    if req.fps and int(req.fps) > 0:
        vfilters.append(f"fps={int(req.fps)}")
    if req.video_filters:
        for vf in list(req.video_filters):
            v = str(vf or "").strip()
            if v:
                vfilters.append(v)

    cmd = [str(ffmpeg), "-hide_banner"]
    cmd += ["-y" if req.overwrite else "-n"]
    if start_s is not None and start_s > 0:
        cmd += ["-ss", f"{float(start_s):.3f}"]
    cmd += ["-i", str(inp)]
    if end_s is not None and start_s is not None:
        cmd += ["-t", f"{max(0.0, float(end_s) - float(start_s)):.3f}"]
    elif end_s is not None and start_s is None:
        cmd += ["-to", f"{float(end_s):.3f}"]

    # Prefer re-encode when filters are present; allow stream copy only when no edits.
    out_ext = outp.suffix.lower()
    is_video = out_ext in {".mp4", ".mkv", ".mov", ".webm"} or inp.suffix.lower() in {".mp4", ".mkv", ".mov", ".avi", ".webm"}

    cover = None
    if out_ext == ".mp3" and req.preserve_cover_art:
        try:
            cover = extract_cover_art(inp)
        except Exception:
            cover = None

    if vfilters:
        cmd += ["-vf", ",".join(vfilters)]
    if afilters:
        cmd += ["-af", ",".join(afilters)]

    # Codecs
    if is_video:
        vc = (req.video_codec or "").strip().lower() or "h264"
        if req.use_gpu and ffmpeg_has_encoder("h264_nvenc") and out_ext in {".mp4", ".mkv", ".mov"}:
            if vc in {"h265", "hevc"} and ffmpeg_has_encoder("hevc_nvenc"):
                cmd += ["-c:v", "hevc_nvenc", "-preset", "p4"]
            else:
                cmd += ["-c:v", "h264_nvenc", "-preset", "p4"]
            cq = "23"
            try:
                if req.video_crf:
                    cq = str(int(float(req.video_crf)))
            except Exception:
                pass
            cmd += ["-cq", cq]
            cmd += ["-c:a", "aac"]
        elif out_ext == ".webm" or vc == "vp9":
            cmd += ["-c:v", "libvpx-vp9", "-crf", str(req.video_crf or 32), "-b:v", "0", "-c:a", "libopus"]
        elif vc == "av1":
            # AV1 (slow, but great compression)
            cmd += ["-c:v", "libaom-av1", "-crf", str(req.video_crf or 32), "-b:v", "0", "-cpu-used", "6", "-c:a", "aac"]
        elif vc in {"h265", "hevc"}:
            cmd += ["-c:v", "libx265", "-preset", "medium", "-crf", str(req.video_crf or 26), "-c:a", "aac"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(req.video_crf or 20), "-c:a", "aac"]

        if req.audio_bitrate:
            cmd += ["-b:a", str(req.audio_bitrate)]
    else:
        # Audio-only export
        if out_ext == ".mp3":
            cmd += ["-map", "0:a:0", "-c:a", "libmp3lame", "-id3v2_version", "3", "-write_id3v1", "1"]
            if req.audio_bitrate:
                b = str(req.audio_bitrate)
                cmd += ["-b:a", b, "-minrate", b, "-maxrate", b, "-bufsize", b]
        elif out_ext == ".flac":
            cmd += ["-map", "0:a:0", "-c:a", "flac"]
        elif out_ext == ".wav":
            cmd += ["-map", "0:a:0", "-c:a", "pcm_s16le"]
        elif out_ext == ".m4a":
            cmd += ["-map", "0:a:0", "-c:a", "aac"]
            if req.audio_bitrate:
                cmd += ["-b:a", str(req.audio_bitrate)]
        else:
            # Best-effort
            if req.audio_codec:
                cmd += ["-c:a", str(req.audio_codec)]
            if req.audio_bitrate:
                cmd += ["-b:a", str(req.audio_bitrate)]

    # Progress
    use_progress = bool((duration_span or duration_total) and callable(progress_cb))
    cmd_run = list(cmd) + [str(outp)]
    if use_progress:
        cmd_run = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + cmd_run[1:]

    stderr_buf: list[str] = []
    last_frac_box = {"v": -1.0}

    def drain_stderr():
        try:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_buf.append(line)
                if len(stderr_buf) > 500:
                    del stderr_buf[:100]
        except Exception:
            pass

    def read_progress():
        try:
            if proc.stdout is None:
                return
            dur = float(duration_span or duration_total or 0.0)
            for raw in proc.stdout:
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    return
                line = (raw or "").strip()
                if not line or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if key not in {"out_time_ms", "out_time_us", "out_time"}:
                    continue
                t = None
                try:
                    if key == "out_time":
                        parts = val.split(":")
                        if len(parts) == 3:
                            t = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    else:
                        # ffmpeg -progress uses confusing names; in practice out_time_ms is microseconds.
                        t = float(val) / 1_000_000.0
                except Exception:
                    t = None
                if t is None or dur <= 0:
                    continue
                frac = max(0.0, min(1.0, float(t) / dur))
                if proc.poll() is None and frac >= 0.999:
                    frac = 0.99
                last = float(last_frac_box["v"])
                if frac - last >= 0.01 or frac in {0.0, 1.0}:
                    last_frac_box["v"] = frac
                    try:
                        progress_cb(frac, "Rendering…")
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            cmd_run,
            stdout=subprocess.PIPE if use_progress else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_kwargs(),
        )
    except Exception as e:
        return MediaEditResult(ok=False, message=str(e))

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
            return MediaEditResult(ok=False, message="Cancelled.")
        rc = proc.poll()
        if rc is not None:
            if rc == 0:
                try:
                    if callable(progress_cb):
                        progress_cb(1.0, "Done.")
                except Exception:
                    pass
                break
            err = "".join(stderr_buf).strip()
            return MediaEditResult(ok=False, message=(err or f"ffmpeg failed with code {rc}")[:1400])
        threading.Event().wait(0.15)

    if cover and out_ext == ".mp3":
        try:
            ensure_mp3_cover_art(outp, cover)
        except Exception:
            pass

    return MediaEditResult(ok=True, message="Rendered.", output_path=str(outp))


def edit_audio_remove_segment(
    req: MediaEditRequest,
    remove_start_seconds: float,
    remove_end_seconds: float,
    *,
    cancel_event=None,
    progress_cb=None,
) -> MediaEditResult:
    """
    Audio-only edit: remove a middle segment [remove_start, remove_end] and join the remaining audio.
    Applies req's audio filters (volume/normalize/fades) to the final output.
    """
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return MediaEditResult(ok=False, message="ffmpeg not available. Install 'imageio-ffmpeg' or set FYLORRA_FFMPEG.")

    inp = Path(req.input_path)
    outp = Path(req.output_path)
    if not inp.exists():
        return MediaEditResult(ok=False, message="Input file not found.")
    if outp.exists() and not req.overwrite:
        return MediaEditResult(ok=False, message=f"Output already exists: {outp.name}")
    outp.parent.mkdir(parents=True, exist_ok=True)

    rs = max(0.0, float(remove_start_seconds))
    re_ = max(0.0, float(remove_end_seconds))
    if re_ <= rs:
        return MediaEditResult(ok=False, message="Remove end must be after remove start.")

    duration_total = _duration_seconds(inp) or None
    if duration_total and rs >= duration_total - 0.05:
        return MediaEditResult(ok=False, message="Remove start is after the end of the file.")
    if duration_total:
        re_ = min(re_, duration_total)
    duration_final = None
    if duration_total:
        duration_final = max(0.0, float(duration_total) - (re_ - rs))

    out_ext = outp.suffix.lower()
    cover = None
    if out_ext == ".mp3" and req.preserve_cover_art:
        try:
            cover = extract_cover_art(inp)
        except Exception:
            cover = None

    # Build audio filter chain for final output
    afilters: list[str] = []
    if req.volume_db is not None:
        afilters.append(f"volume={float(req.volume_db)}dB")
    if req.normalize:
        afilters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
    if req.fade_in_seconds and req.fade_in_seconds > 0:
        st = float(req.fade_in_at_seconds) if req.fade_in_at_seconds is not None else 0.0
        if duration_final:
            st = min(max(0.0, st), max(0.0, float(duration_final) - 0.001))
        afilters.append(f"afade=t=in:st={max(0.0, st):.3f}:d={float(req.fade_in_seconds)}")
    if req.fade_out_seconds and req.fade_out_seconds > 0 and (duration_final or req.fade_out_at_seconds is not None):
        if req.fade_out_at_seconds is not None:
            st = max(0.0, float(req.fade_out_at_seconds))
        else:
            st = max(0.0, float(duration_final) - float(req.fade_out_seconds))  # type: ignore[arg-type]
        if duration_final:
            st = min(st, max(0.0, float(duration_final) - 0.001))
        afilters.append(f"afade=t=out:st={max(0.0, st):.3f}:d={float(req.fade_out_seconds)}")

    # Construct filter_complex:
    # a0 = 0..rs, a1 = re..end, concat, then apply afilters
    parts = [
        f"[0:a]atrim=start=0:end={rs:.6f},asetpts=PTS-STARTPTS[a0]",
        f"[0:a]atrim=start={re_:.6f},asetpts=PTS-STARTPTS[a1]",
        "[a0][a1]concat=n=2:v=0:a=1[acat]",
    ]
    last = "[acat]"
    if afilters:
        parts.append(f"{last}{','.join(afilters)}[aout]")
        last = "[aout]"

    cmd = [str(ffmpeg), "-hide_banner"]
    cmd += ["-y" if req.overwrite else "-n"]
    cmd += ["-i", str(inp)]
    cmd += ["-filter_complex", ";".join(parts)]
    cmd += ["-map", last]

    # Codecs similar to edit_media audio-only section
    if out_ext == ".mp3":
        cmd += ["-c:a", "libmp3lame", "-id3v2_version", "3", "-write_id3v1", "1"]
        if req.audio_bitrate:
            b = str(req.audio_bitrate)
            cmd += ["-b:a", b, "-minrate", b, "-maxrate", b, "-bufsize", b]
    elif out_ext == ".flac":
        cmd += ["-c:a", "flac"]
    elif out_ext == ".wav":
        cmd += ["-c:a", "pcm_s16le"]
    elif out_ext == ".m4a":
        cmd += ["-c:a", "aac"]
        if req.audio_bitrate:
            cmd += ["-b:a", str(req.audio_bitrate)]
    else:
        if req.audio_codec:
            cmd += ["-c:a", str(req.audio_codec)]
        if req.audio_bitrate:
            cmd += ["-b:a", str(req.audio_bitrate)]

    # Progress
    use_progress = bool(duration_final and callable(progress_cb))
    cmd_run = list(cmd) + [str(outp)]
    if use_progress:
        cmd_run = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + cmd_run[1:]

    stderr_buf: list[str] = []
    last_frac_box = {"v": -1.0}

    def drain_stderr():
        try:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_buf.append(line)
                if len(stderr_buf) > 500:
                    del stderr_buf[:100]
        except Exception:
            pass

    def read_progress():
        try:
            if proc.stdout is None:
                return
            dur = float(duration_final or 0.0)
            for raw in proc.stdout:
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    return
                line = (raw or "").strip()
                if not line or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if key not in {"out_time_ms", "out_time_us", "out_time"}:
                    continue
                t = None
                try:
                    if key == "out_time":
                        parts = val.split(":")
                        if len(parts) == 3:
                            t = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    else:
                        t = float(val) / 1_000_000.0
                except Exception:
                    t = None
                if t is None or dur <= 0:
                    continue
                frac = max(0.0, min(1.0, float(t) / dur))
                if proc.poll() is None and frac >= 0.999:
                    frac = 0.99
                last = float(last_frac_box["v"])
                if frac - last >= 0.01 or frac in {0.0, 1.0}:
                    last_frac_box["v"] = frac
                    try:
                        progress_cb(frac, "Cutting…")
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            cmd_run,
            stdout=subprocess.PIPE if use_progress else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_kwargs(),
        )
    except Exception as e:
        return MediaEditResult(ok=False, message=str(e))

    threading.Thread(target=drain_stderr, daemon=True).start()
    if use_progress:
        threading.Thread(target=read_progress, daemon=True).start()

    while True:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            try:
                proc.terminate()
            except Exception:
                pass
            return MediaEditResult(ok=False, message="Cancelled.")
        rc = proc.poll()
        if rc is not None:
            if rc == 0:
                try:
                    if callable(progress_cb):
                        progress_cb(1.0, "Done.")
                except Exception:
                    pass
                break
            err = "".join(stderr_buf).strip()
            return MediaEditResult(ok=False, message=(err or f"ffmpeg failed with code {rc}")[:1400])
        threading.Event().wait(0.15)

    if cover and out_ext == ".mp3":
        try:
            ensure_mp3_cover_art(outp, cover)
        except Exception:
            pass

    return MediaEditResult(ok=True, message="Cut complete.", output_path=str(outp))


def edit_audio_remove_segments(
    req: MediaEditRequest,
    remove_segments: list[tuple[float, float]] | None = None,
    *,
    cancel_event=None,
    progress_cb=None,
) -> MediaEditResult:
    """
    Audio-only edit: remove multiple segments and join the remaining audio.
    Supports req.start_seconds/end_seconds trimming, then removes segments within that trimmed window.
    Applies req's audio filters (volume/normalize/fades/audio_fade_regions) to the final output.
    """
    ffmpeg = get_ffmpeg_exe()
    if not ffmpeg:
        return MediaEditResult(ok=False, message="ffmpeg not available. Install 'imageio-ffmpeg' or set FYLORRA_FFMPEG.")

    inp = Path(req.input_path)
    outp = Path(req.output_path)
    if not inp.exists():
        return MediaEditResult(ok=False, message="Input file not found.")
    if outp.exists() and not req.overwrite:
        return MediaEditResult(ok=False, message=f"Output already exists: {outp.name}")
    outp.parent.mkdir(parents=True, exist_ok=True)

    duration_total = _duration_seconds(inp) or None
    trim_start = max(0.0, float(req.start_seconds or 0.0))
    trim_end: float | None = None
    if req.end_seconds is not None:
        trim_end = max(trim_start, float(req.end_seconds))
    elif duration_total is not None:
        trim_end = float(duration_total)

    if duration_total is not None:
        trim_start = min(trim_start, max(0.0, float(duration_total)))
        if trim_end is not None:
            trim_end = min(float(trim_end), max(0.0, float(duration_total)))

    if trim_end is not None and trim_end <= trim_start + 0.001:
        return MediaEditResult(ok=False, message="End time must be after start time.")

    # Normalize remove segments (absolute seconds) -> trim-relative, then merge overlaps.
    segs = list(remove_segments or req.audio_remove_segments or [])
    rel: list[tuple[float, float]] = []
    for rs, re_ in segs:
        try:
            a = float(rs)
            b = float(re_)
        except Exception:
            continue
        if b <= a:
            continue
        if trim_end is not None:
            if b <= trim_start or a >= trim_end:
                continue
            a = max(a, trim_start)
            b = min(b, trim_end)
        else:
            if b <= trim_start:
                continue
            a = max(a, trim_start)
        ra = max(0.0, a - trim_start)
        rb = max(0.0, b - trim_start)
        if rb <= ra + 0.001:
            continue
        rel.append((ra, rb))

    rel.sort(key=lambda x: (x[0], x[1]))
    merged: list[tuple[float, float]] = []
    for a, b in rel:
        if not merged:
            merged.append((a, b))
            continue
        la, lb = merged[-1]
        if a <= lb + 1e-6:
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))

    # Final duration estimate for progress.
    trim_dur: float | None = None
    if trim_end is not None:
        trim_dur = max(0.0, float(trim_end) - float(trim_start))
    elif duration_total is not None:
        trim_dur = max(0.0, float(duration_total) - float(trim_start))
    removed_len = sum(max(0.0, b - a) for a, b in merged)
    duration_final = max(0.0, float(trim_dur) - float(removed_len)) if trim_dur is not None else None

    out_ext = outp.suffix.lower()
    cover = None
    if out_ext == ".mp3" and req.preserve_cover_art:
        try:
            cover = extract_cover_art(inp)
        except Exception:
            cover = None

    # Build audio filter chain for final output.
    afilters: list[str] = []
    if req.volume_db is not None:
        afilters.append(f"volume={float(req.volume_db)}dB")
    if req.normalize:
        afilters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
    if req.fade_in_seconds and req.fade_in_seconds > 0:
        st = float(req.fade_in_at_seconds) if req.fade_in_at_seconds is not None else 0.0
        if duration_final:
            st = min(max(0.0, st), max(0.0, float(duration_final) - 0.001))
        afilters.append(f"afade=t=in:st={max(0.0, st):.3f}:d={float(req.fade_in_seconds)}")
    if req.fade_out_seconds and req.fade_out_seconds > 0 and (duration_final or req.fade_out_at_seconds is not None):
        if req.fade_out_at_seconds is not None:
            st = max(0.0, float(req.fade_out_at_seconds))
        else:
            st = max(0.0, float(duration_final) - float(req.fade_out_seconds))  # type: ignore[arg-type]
        if duration_final:
            st = min(st, max(0.0, float(duration_final) - 0.001))
        afilters.append(f"afade=t=out:st={max(0.0, st):.3f}:d={float(req.fade_out_seconds)}")
    if req.audio_fade_regions:
        for t, st, d in list(req.audio_fade_regions):
            tt = (str(t or "")).strip().lower()
            if tt not in {"in", "out"}:
                continue
            try:
                st_f = max(0.0, float(st))
                d_f = max(0.0, float(d))
            except Exception:
                continue
            if d_f <= 0.001:
                continue
            if duration_final:
                st_f = min(st_f, max(0.0, float(duration_final) - 0.001))
            afilters.append(f"afade=t={tt}:st={st_f:.3f}:d={d_f:.3f}")

    # Construct filter_complex: trim -> keep segments -> concat -> afilters
    parts: list[str] = []
    if trim_end is not None:
        parts.append(f"[0:a]atrim=start={trim_start:.6f}:end={float(trim_end):.6f},asetpts=PTS-STARTPTS[abase]")
    else:
        parts.append(f"[0:a]atrim=start={trim_start:.6f},asetpts=PTS-STARTPTS[abase]")

    # Build keep ranges between removed segments.
    keep: list[tuple[float, float | None]] = []
    cursor = 0.0
    for a, b in merged:
        if a > cursor + 1e-6:
            keep.append((cursor, a))
        cursor = max(cursor, b)
    keep.append((cursor, None))  # tail

    if trim_dur is not None and removed_len >= float(trim_dur) - 0.01:
        return MediaEditResult(ok=False, message="All audio would be removed by cut-out ranges.")

    labels: list[str] = []
    for i, (ks, ke) in enumerate(keep):
        if ke is not None and ke <= ks + 1e-6:
            continue
        if ke is None:
            parts.append(f"[abase]atrim=start={ks:.6f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            parts.append(f"[abase]atrim=start={ks:.6f}:end={float(ke):.6f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[a{i}]")

    if not labels:
        return MediaEditResult(ok=False, message="No audio remains after cut-out ranges.")

    if len(labels) == 1:
        parts.append(f"{labels[0]}anull[acat]")
    else:
        parts.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[acat]")

    last = "[acat]"
    if afilters:
        parts.append(f"{last}{','.join(afilters)}[aout]")
        last = "[aout]"

    cmd = [str(ffmpeg), "-hide_banner"]
    cmd += ["-y" if req.overwrite else "-n"]
    cmd += ["-i", str(inp)]
    cmd += ["-filter_complex", ";".join(parts)]
    cmd += ["-map", last]

    if out_ext == ".mp3":
        cmd += ["-c:a", "libmp3lame", "-id3v2_version", "3", "-write_id3v1", "1"]
        if req.audio_bitrate:
            b = str(req.audio_bitrate)
            cmd += ["-b:a", b, "-minrate", b, "-maxrate", b, "-bufsize", b]
    elif out_ext == ".flac":
        cmd += ["-c:a", "flac"]
    elif out_ext == ".wav":
        cmd += ["-c:a", "pcm_s16le"]
    elif out_ext == ".m4a":
        cmd += ["-c:a", "aac"]
        if req.audio_bitrate:
            cmd += ["-b:a", str(req.audio_bitrate)]
    else:
        if req.audio_codec:
            cmd += ["-c:a", str(req.audio_codec)]
        if req.audio_bitrate:
            cmd += ["-b:a", str(req.audio_bitrate)]

    use_progress = bool(duration_final and callable(progress_cb))
    cmd_run = list(cmd) + [str(outp)]
    if use_progress:
        cmd_run = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + cmd_run[1:]

    stderr_buf: list[str] = []
    last_frac_box = {"v": -1.0}

    def drain_stderr():
        try:
            if proc.stderr is None:
                return
            for line in proc.stderr:
                stderr_buf.append(line)
                if len(stderr_buf) > 500:
                    del stderr_buf[:100]
        except Exception:
            pass

    def read_progress():
        try:
            if proc.stdout is None:
                return
            dur = float(duration_final or 0.0)
            for raw in proc.stdout:
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    return
                line = (raw or "").strip()
                if not line or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if key not in {"out_time_ms", "out_time_us", "out_time"}:
                    continue
                t = None
                try:
                    if key == "out_time":
                        parts = val.split(":")
                        if len(parts) == 3:
                            t = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    else:
                        t = float(val) / 1_000_000.0
                except Exception:
                    t = None
                if t is None or dur <= 0:
                    continue
                frac = max(0.0, min(1.0, float(t) / dur))
                if proc.poll() is None and frac >= 0.999:
                    frac = 0.99
                last = float(last_frac_box["v"])
                if frac - last >= 0.01 or frac in {0.0, 1.0}:
                    last_frac_box["v"] = frac
                    try:
                        progress_cb(frac, "Cutting…")
                    except Exception:
                        pass
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            cmd_run,
            stdout=subprocess.PIPE if use_progress else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_kwargs(),
        )
    except Exception as e:
        return MediaEditResult(ok=False, message=str(e))

    threading.Thread(target=drain_stderr, daemon=True).start()
    if use_progress:
        threading.Thread(target=read_progress, daemon=True).start()

    while True:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            try:
                proc.terminate()
            except Exception:
                pass
            return MediaEditResult(ok=False, message="Cancelled.")
        rc = proc.poll()
        if rc is not None:
            if rc == 0:
                try:
                    if callable(progress_cb):
                        progress_cb(1.0, "Done.")
                except Exception:
                    pass
                break
            err = "".join(stderr_buf).strip()
            return MediaEditResult(ok=False, message=(err or f"ffmpeg failed with code {rc}")[:1400])
        threading.Event().wait(0.15)

    if cover and out_ext == ".mp3":
        try:
            ensure_mp3_cover_art(outp, cover)
        except Exception:
            pass

    return MediaEditResult(ok=True, message="Cut complete.", output_path=str(outp))
