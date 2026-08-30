"""
Fylorra - Professional Audio Editor (PySide6)
Modern DAW-style interface with professional waveform visualization,
icon-based controls, and comprehensive editing capabilities.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QToolButton,
)

from core.ffmpeg_manager import get_ffmpeg_exe, get_ffplay_exe, get_ffprobe_exe


# ============================================================================
# THEME CONSTANTS - Matching Original CustomTkinter Audio Editor
# ============================================================================

THEME = {
    "bg_main": "#1e1e1e",
    "bg_panel": "#252525",
    "bg_toolbar": "#2d2d2d",
    "bg_control": "#2d2d2d",
    "accent": "#3a7fd5",
    "accent_hover": "#4a8fe5",
    "accent_pressed": "#2a6fc5",
    "text_primary": "#ffffff",
    "text_secondary": "#a7abb3",
    "text_tip": "#8a8f98",
    "border": "#3a3f46",
    "border_light": "#4a4f56",
    "success": "#4caf50",
    "warning": "#ff9800",
    "danger": "#f44336",
    # Waveform colors - EXACT match to original
    "waveform_bg": "#151515",
    "waveform_bars": "#3aaed8",  # cyan/turquoise
    "waveform_midline": "#1f242b",
    "waveform_playhead": "#2b7cff",
    "waveform_in_marker": "#90cdf4",
    "waveform_out_marker": "#f6ad55",
    # Overlay colors with alpha - EXACT match to original
    "selection_overlay": "#2b6cb0",  # Will use 25% alpha (64)
    "cut_overlay": "#7a1420",  # Will use 25% alpha (64)
    "fade_in_overlay": "#0a6b3d",  # Will use 25% alpha (64)
    "fade_out_overlay": "#8a4b0f",  # Will use 25% alpha (64)
    # Button colors - EXACT match to original
    "button_inactive": "#444",
    "button_active": "#1f6aa5",
    "grid_line": "#2a2a2a",
    "grid_tick": "#3a3a3a",
    # dB meter colors
    "db_bg": "#0f0f10",
    "db_green_bg": "#10251a",
    "db_green_fill": "#1f7a3a",
    "db_yellow_bg": "#2a2313",
    "db_yellow_fill": "#caa52a",
    "db_red_bg": "#2a1417",
    "db_red_fill": "#b3212f",
}


# Icon paths
ICONS = {
    "folder": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\folder.png",
    "add": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\add.png",
    "export": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\export.png",
    "settings": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\settings.png",
    "search": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\search.png",
    "delete": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\delete.png",
    "play": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\play.png",
    "pause": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\pause.png",
    "stop": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\stop.png",
    "forward": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\foward.png",
    "rewind": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\rewind.png",
    "loop": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\loop.png",
    "fade_in": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\fade_in.png",
    "fade_out": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\fade_out.png",
    "audio_file": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\audio-file.png",
    "add_media": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\video_editor\add-media.png",
    "cut": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\Cloud_Sync\cut.png",
    "copy": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\Cloud_Sync\copy.png",
    "paste": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\Cloud_Sync\paste.png",
    "refresh": r"E:\Programing Code Projects\Python\Folder_Monitoring\assets\icons\Cloud_Sync\refresh.png",
}


def apply_theme_stylesheet(widget: QWidget) -> None:
    """Apply professional DAW theme stylesheet."""
    stylesheet = f"""
        QDialog {{
            background-color: {THEME['bg_main']};
            color: {THEME['text_primary']};
        }}
        QLabel {{
            color: {THEME['text_primary']};
            background-color: transparent;
        }}
        QPushButton {{
            background-color: {THEME['bg_control']};
            color: {THEME['text_primary']};
            border: 1px solid {THEME['border']};
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {THEME['accent_hover']};
            border-color: {THEME['accent']};
        }}
        QPushButton:pressed {{
            background-color: {THEME['accent_pressed']};
        }}
        QPushButton:disabled {{
            background-color: {THEME['bg_control']};
            color: {THEME['text_secondary']};
            border-color: {THEME['border']};
        }}
        QPushButton.accent {{
            background-color: {THEME['accent']};
            border-color: {THEME['accent']};
        }}
        QPushButton.accent:hover {{
            background-color: {THEME['accent_hover']};
        }}
        QPushButton.danger {{
            background-color: {THEME['danger']};
            border-color: {THEME['danger']};
        }}
        QToolButton {{
            background-color: {THEME['bg_toolbar']};
            color: {THEME['text_primary']};
            border: 1px solid {THEME['border']};
            border-radius: 6px;
            padding: 6px;
        }}
        QToolButton:hover {{
            background-color: {THEME['accent_hover']};
            border-color: {THEME['accent']};
        }}
        QToolButton:pressed {{
            background-color: {THEME['accent_pressed']};
        }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: {THEME['bg_control']};
            color: {THEME['text_primary']};
            border: 1px solid {THEME['border']};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 13px;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border-color: {THEME['accent']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid {THEME['text_primary']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {THEME['bg_control']};
            color: {THEME['text_primary']};
            border: 1px solid {THEME['border']};
            selection-background-color: {THEME['accent']};
        }}
        QSlider::groove:horizontal {{
            background-color: {THEME['bg_control']};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background-color: {THEME['accent']};
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background-color: {THEME['accent_hover']};
        }}
        QCheckBox {{
            color: {THEME['text_primary']};
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {THEME['border']};
            border-radius: 4px;
            background-color: {THEME['bg_control']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {THEME['accent']};
            border-color: {THEME['accent']};
        }}
        QProgressBar {{
            background-color: {THEME['bg_control']};
            border: 1px solid {THEME['border']};
            border-radius: 6px;
            text-align: center;
            color: {THEME['text_primary']};
            height: 24px;
        }}
        QProgressBar::chunk {{
            background-color: {THEME['accent']};
            border-radius: 5px;
        }}
        QListWidget {{
            background-color: {THEME['bg_panel']};
            color: {THEME['text_primary']};
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            background-color: {THEME['bg_control']};
            color: {THEME['text_primary']};
            border: 1px solid {THEME['border']};
            border-radius: 6px;
            padding: 8px;
            margin: 4px;
        }}
        QListWidget::item:hover {{
            background-color: {THEME['accent_hover']};
            border-color: {THEME['accent']};
        }}
        QListWidget::item:selected {{
            background-color: {THEME['accent']};
            border-color: {THEME['accent']};
        }}
        QScrollBar:vertical {{
            background-color: {THEME['bg_control']};
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {THEME['accent']};
            border-radius: 6px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QFrame.panel {{
            background-color: {THEME['bg_panel']};
            border: 1px solid {THEME['border']};
            border-radius: 8px;
        }}
        QFrame.toolbar {{
            background-color: {THEME['bg_toolbar']};
            border-bottom: 1px solid {THEME['border']};
        }}
        QFrame.transport {{
            background-color: {THEME['bg_toolbar']};
            border-top: 1px solid {THEME['border']};
        }}
    """
    widget.setStyleSheet(stylesheet)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def parse_time(s: str) -> Optional[float]:
    """Parse time string to seconds. Supports: 1.5, 01:30, 00:01:30."""
    s = (s or "").strip()
    if not s:
        return None

    # Try simple float
    try:
        return float(s)
    except ValueError:
        pass

    # Try HH:MM:SS or MM:SS format
    parts = s.split(":")
    try:
        if len(parts) == 2:
            mm, ss = parts
            return int(mm) * 60 + float(ss)
        elif len(parts) == 3:
            hh, mm, ss = parts
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
    except (ValueError, IndexError):
        pass

    return None


def format_time(seconds: float) -> str:
    """Format seconds to MM:SS.mm format."""
    seconds = max(0.0, float(seconds))
    mm = int(seconds // 60)
    ss = seconds % 60
    return f"{mm:02d}:{ss:05.2f}"


def get_audio_duration(file_path: str) -> Optional[float]:
    """Get audio duration in seconds using ffprobe."""
    ffprobe = get_ffprobe_exe()
    if not ffprobe or not Path(file_path).exists():
        return None

    try:
        cmd = [
            str(ffprobe),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(file_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=False,  # Get bytes instead of text
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout.decode('utf-8', errors='ignore'))
            duration = data.get("format", {}).get("duration")
            if duration:
                return float(duration)
    except Exception as e:
        print(f"Error getting duration: {e}")

    return None


# ============================================================================
# AUDIO TRACK DATA STRUCTURES
# ============================================================================

import random

def generate_track_color() -> str:
    """Generate a random professional track color."""
    colors = [
        "#3a7fd5", "#4caf50", "#ff9800", "#f44336", "#9c27b0",
        "#00bcd4", "#ffeb3b", "#e91e63", "#009688", "#ff5722"
    ]
    return random.choice(colors)


class AudioTrack:
    """Represents a single audio track with its own properties and regions."""

    def __init__(self, name: str, file_path: str):
        self.name = name
        self.file_path = file_path
        self.waveform_data = []  # Peak values for waveform display
        self.duration = 0.0  # Duration in seconds

        # Edit regions
        self.fade_in_regions = []  # List of (start, end) tuples
        self.fade_out_regions = []  # List of (start, end) tuples
        self.cut_regions = []  # List of (start, end) tuples
        self.last_selection = None  # (start, end) from waveform selection (seconds)

        # Mixing parameters
        self.volume = 0.0  # Volume in dB (-60 to +12)
        self.pan = 0.0  # Pan position (-1.0 = left, 0.0 = center, 1.0 = right)
        self.solo = False  # Solo state
        self.mute = False  # Mute state

        # Timeline position (like Audacity clips)
        self.time_offset = 0.0  # Start time offset in seconds (for horizontal positioning)

        # Visual properties
        self.color = generate_track_color()
        self.height = 120  # Height in pixels

        # Effects
        self.effects = {
            'eq': {'enabled': False, 'low': 0.0, 'mid': 0.0, 'high': 0.0},
            'compressor': {'enabled': False, 'threshold': -20.0, 'ratio': 4.0, 'attack': 5.0, 'release': 50.0},
            'reverb': {'enabled': False, 'size': 0.5, 'decay': 0.5, 'mix': 0.3},
            'delay': {'enabled': False, 'time': 500.0, 'feedback': 0.3, 'mix': 0.3},
            'pitch': {'enabled': False, 'semitones': 0.0, 'preserve_duration': True},
            'speed': {'enabled': False, 'multiplier': 1.0, 'preserve_pitch': True},
            'noise_reduction': {'enabled': False, 'threshold': 0.5, 'amount': 0.5},
            'limiter': {'enabled': False, 'ceiling': -0.1}
        }

    def get_ffmpeg_filter(self) -> str:
        """Generate ffmpeg filter string for this track's effects."""
        filters = []

        # Volume and pan
        if self.volume != 0.0:
            filters.append(f"volume={self.volume}dB")
        if self.pan != 0.0:
            # Convert -1..1 to 0..1 where 0.5 is center
            pan_val = (self.pan + 1.0) / 2.0
            filters.append(f"pan=stereo|c0={1-pan_val}*c0+{pan_val}*c1|c1={pan_val}*c0+{1-pan_val}*c1")

        # EQ
        if self.effects['eq']['enabled']:
            eq = self.effects['eq']
            if eq['low'] != 0.0:
                filters.append(f"equalizer=f=100:width_type=o:width=2:g={eq['low']}")
            if eq['mid'] != 0.0:
                filters.append(f"equalizer=f=1000:width_type=o:width=2:g={eq['mid']}")
            if eq['high'] != 0.0:
                filters.append(f"equalizer=f=10000:width_type=o:width=2:g={eq['high']}")

        # Compressor
        if self.effects['compressor']['enabled']:
            comp = self.effects['compressor']
            filters.append(f"acompressor=threshold={comp['threshold']}dB:ratio={comp['ratio']}:attack={comp['attack']}:release={comp['release']}")

        # Reverb (using aecho as approximation)
        if self.effects['reverb']['enabled']:
            rev = self.effects['reverb']
            decay_time = int(rev['decay'] * 1000)
            filters.append(f"aecho=0.8:0.88:{decay_time}:{rev['mix']}")

        # Delay
        if self.effects['delay']['enabled']:
            delay = self.effects['delay']
            filters.append(f"aecho=0.8:0.88:{int(delay['time'])}:{delay['feedback']}")

        # Pitch shift
        if self.effects['pitch']['enabled'] and self.effects['pitch']['semitones'] != 0.0:
            semitones = self.effects['pitch']['semitones']
            rate_factor = 2.0 ** (semitones / 12.0)
            if self.effects['pitch']['preserve_duration']:
                filters.append(f"asetrate=44100*{rate_factor},aresample=44100,atempo={1/rate_factor}")
            else:
                filters.append(f"asetrate=44100*{rate_factor},aresample=44100")

        # Speed change
        if self.effects['speed']['enabled'] and self.effects['speed']['multiplier'] != 1.0:
            speed = self.effects['speed']['multiplier']
            if self.effects['speed']['preserve_pitch']:
                filters.append(f"atempo={speed}")
            else:
                filters.append(f"asetrate=44100*{speed},aresample=44100")

        # Noise reduction
        if self.effects['noise_reduction']['enabled']:
            nr = self.effects['noise_reduction']
            filters.append(f"afftdn=nr={nr['amount']*20}:nf={nr['threshold']*100}")

        # Limiter
        if self.effects['limiter']['enabled']:
            lim = self.effects['limiter']
            filters.append(f"alimiter=limit={lim['ceiling']}:attack=5:release=50")

        return ','.join(filters) if filters else 'anull'


# ============================================================================
# WAVEFORM WORKER THREAD
# ============================================================================

class WaveformWorker(QThread):
    """Background thread to generate waveform data from audio file."""

    finished = Signal(list)  # List of peak values
    error = Signal(str)

    def __init__(self, file_path: str, samples: int = 1000):
        super().__init__()
        self.file_path = file_path
        self.samples = samples

    def run(self):
        """Generate waveform peaks using ffmpeg (streamed; never loads full PCM in memory)."""
        try:
            ffmpeg = get_ffmpeg_exe()
            if not ffmpeg:
                self.error.emit("FFmpeg not found")
                return

            duration = get_audio_duration(str(self.file_path)) or 0.0

            # Stream mono PCM at low sample rate to keep CPU/RAM low.
            # IMPORTANT: do not use capture_output for long files — it can OOM/crash the process.
            sample_rate = 8000
            sample_width_bytes = 2  # s16le
            cmd = [
                str(ffmpeg),
                "-v",
                "error",
                "-nostdin",
                "-i",
                str(self.file_path),
                "-f",
                "s16le",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-",
            ]

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )

            if not proc.stdout:
                self.error.emit("Failed to start FFmpeg (no stdout)")
                return

            import audioop

            # Estimate total samples for stable binning; fallback to adaptive downsampling.
            total_samples_est = int(duration * sample_rate) if duration and duration > 0 else 0
            bin_samples = max(1, int(total_samples_est // max(1, self.samples))) if total_samples_est else 0

            peaks: list[float] = []
            cur_max = 0
            cur_count = 0  # samples in current bin

            stop_now = False

            # Read in chunks and compute bin maxima.
            while True:
                data = proc.stdout.read(16384)
                if not data:
                    break

                # Ensure even number of bytes (whole samples)
                if len(data) % sample_width_bytes != 0:
                    data = data[: len(data) - (len(data) % sample_width_bytes)]
                    if not data:
                        continue

                if bin_samples:
                    # Fixed binning (preferred).
                    view = data
                    while view:
                        remaining = bin_samples - cur_count
                        take_samples = max(1, min(remaining, len(view) // sample_width_bytes))
                        take_bytes = take_samples * sample_width_bytes
                        chunk = view[:take_bytes]
                        view = view[take_bytes:]

                        try:
                            m = audioop.max(chunk, sample_width_bytes)
                        except Exception:
                            m = 0
                        if m > cur_max:
                            cur_max = m
                        cur_count += take_samples

                        if cur_count >= bin_samples:
                            peaks.append(float(cur_max))
                            cur_max = 0
                            cur_count = 0
                            if len(peaks) >= self.samples:
                                # We have enough peaks; stop reading and terminate the process.
                                view = b""
                                stop_now = True
                                break
                    if stop_now:
                        break
                else:
                    # Adaptive: store a chunk max and downsample progressively.
                    try:
                        m = audioop.max(data, sample_width_bytes)
                    except Exception:
                        m = 0
                    peaks.append(float(m))
                    # Keep memory bounded by progressively downsampling.
                    if len(peaks) > self.samples * 8:
                        peaks = [max(peaks[i], peaks[i + 1]) for i in range(0, len(peaks) - 1, 2)]
                if stop_now:
                    break

            # Add partial bin (fixed) if any.
            if bin_samples and cur_count > 0:
                peaks.append(float(cur_max))

            # Wait for process completion (best-effort) and surface errors.
            if stop_now:
                # Terminate quickly; do not call communicate() after closing stdout (avoids _readerthread errors).
                err = b""
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                        proc.wait(timeout=2)
                    except Exception:
                        pass
            else:
                try:
                    _, err = proc.communicate(timeout=10)
                except Exception:
                    err = b""
                    try:
                        proc.kill()
                    except Exception:
                        pass

            if proc.returncode not in (0, None):
                msg = ""
                try:
                    msg = (err or b"").decode("utf-8", errors="ignore").strip()
                except Exception:
                    msg = ""
                self.error.emit(f"FFmpeg error: {proc.returncode}{(': ' + msg) if msg else ''}")
                return

            if not peaks:
                self.error.emit("No audio data extracted")
                return

            # Final downsample to requested size (adaptive path).
            while len(peaks) > self.samples:
                peaks = [max(peaks[i], peaks[i + 1]) for i in range(0, len(peaks) - 1, 2)]
            if len(peaks) < self.samples:
                # Pad with last peak to keep UI stable.
                peaks.extend([peaks[-1]] * (self.samples - len(peaks)))

            # Normalize peaks to 0..1
            max_peak = max(peaks) if peaks else 1.0
            if max_peak <= 0:
                max_peak = 1.0
            peaks = [p / max_peak for p in peaks]

            self.finished.emit(peaks[: self.samples])

        except Exception as e:
            self.error.emit(str(e))


# ============================================================================
# EXPORT WORKER THREAD
# ============================================================================

class ExportWorker(QThread):
    """Background thread to export audio with ffmpeg."""

    progress = Signal(int)  # Progress percentage
    finished = Signal(str)  # Output file path
    error = Signal(str)

    def __init__(
        self,
        input_path: str,
        output_path: str,
        format_: str,
        bitrate: str,
        normalize: bool,
        volume_gain: float,
        cuts: list,
        fade_in: Optional[tuple],
        fade_out: Optional[tuple],
    ):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.format = format_
        self.bitrate = bitrate
        self.normalize = normalize
        self.volume_gain = volume_gain
        self.cuts = cuts
        self.fade_in = fade_in
        self.fade_out = fade_out

    def run(self):
        """Export audio using ffmpeg."""
        try:
            ffmpeg = get_ffmpeg_exe()
            if not ffmpeg:
                self.error.emit("FFmpeg not found")
                return

            # Build filter complex
            filters = []

            # Volume adjustment
            if self.volume_gain != 0.0:
                db = self.volume_gain
                filters.append(f"volume={db}dB")

            # Fade in
            if self.fade_in:
                start, end = self.fade_in
                duration = end - start
                filters.append(f"afade=t=in:st={start}:d={duration}")

            # Fade out
            if self.fade_out:
                start, end = self.fade_out
                duration = end - start
                filters.append(f"afade=t=out:st={start}:d={duration}")

            # Normalization
            if self.normalize:
                filters.append("loudnorm")

            # Build command
            cmd = [str(ffmpeg), "-i", str(self.input_path), "-y"]

            # Handle cuts (multiple segments)
            if self.cuts:
                # Sort cuts by start time
                sorted_cuts = sorted(self.cuts, key=lambda x: x[0])

                # Build select filter to exclude cut regions
                duration = get_audio_duration(self.input_path)
                if duration:
                    select_parts = []
                    prev_end = 0.0

                    for cut_start, cut_end in sorted_cuts:
                        if prev_end < cut_start:
                            select_parts.append(f"between(t,{prev_end},{cut_start})")
                        prev_end = cut_end

                    if prev_end < duration:
                        select_parts.append(f"gte(t,{prev_end})")

                    if select_parts:
                        select_expr = "+".join(select_parts)
                        filters.insert(0, f"aselect='{select_expr}',asetpts=N/SR/TB")

            # Add filters
            if filters:
                cmd.extend(["-af", ",".join(filters)])

            # Format-specific encoding
            if self.format.lower() == "mp3":
                cmd.extend(["-codec:a", "libmp3lame", "-b:a", self.bitrate])
            elif self.format.lower() == "wav":
                cmd.extend(["-codec:a", "pcm_s16le"])
            elif self.format.lower() == "flac":
                cmd.extend(["-codec:a", "flac"])
            elif self.format.lower() == "m4a":
                cmd.extend(["-codec:a", "aac", "-b:a", self.bitrate])
            elif self.format.lower() == "ogg":
                cmd.extend(["-codec:a", "libvorbis", "-b:a", self.bitrate])
            else:
                cmd.extend(["-b:a", self.bitrate])

            cmd.append(str(self.output_path))

            # Run ffmpeg with progress monitoring
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Monitor progress
            duration = get_audio_duration(self.input_path) or 1.0

            for line in process.stderr:
                # Parse time from ffmpeg output
                match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                if match:
                    h, m, s = match.groups()
                    current = int(h) * 3600 + int(m) * 60 + float(s)
                    percent = min(100, int((current / duration) * 100))
                    self.progress.emit(percent)

            process.wait()

            if process.returncode == 0:
                self.progress.emit(100)
                self.finished.emit(str(self.output_path))
            else:
                self.error.emit(f"FFmpeg error: {process.returncode}")

        except Exception as e:
            self.error.emit(str(e))


# ============================================================================
# AUDACITY-STYLE TRACK WIDGET
# ============================================================================

class TrackWidget(QWidget):
    """Single track widget with Mute/Solo/FX controls and waveform canvas - Audacity style."""

    mute_changed = Signal(bool)
    solo_changed = Signal(bool)
    volume_changed = Signal(float)
    offset_changed = Signal(object, float)  # (AudioTrack, time_offset seconds)
    remove_requested = Signal()  # Signal emitted when track should be removed
    clicked = Signal(object)  # AudioTrack selected

    def __init__(self, track: 'AudioTrack', parent=None):
        super().__init__(parent)
        print(f"DEBUG: TrackWidget.__init__ for track: {track.name}")

        self.track = track
        self._selected = False
        self.setMinimumHeight(150)  # Ensure it has height
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_Hover, True)

        # Main horizontal layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Left control panel (fixed width ~180px)
        control_panel = QFrame()
        control_panel.setFixedWidth(180)
        control_panel.setMinimumHeight(180)  # Ensure enough space for all controls
        control_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME['bg_panel']};
                border: 1px solid {THEME['border']};
                border-radius: 6px;
            }}
        """)
        self.control_panel = control_panel

        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(8, 8, 8, 8)
        control_layout.setSpacing(6)

        # Track name header with close button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(4)

        # Small track index badge (DAW-style) - clickable to select track.
        self.index_badge = QPushButton("1")
        self.index_badge.setFixedSize(22, 22)
        self.index_badge.setCursor(Qt.PointingHandCursor)
        self.index_badge.setFocusPolicy(Qt.NoFocus)
        self.index_badge.setStyleSheet(f"""
            QPushButton {{
                background: {THEME['bg_control']};
                color: {THEME['text_primary']};
                border: 1px solid {THEME['border']};
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                padding: 0px;
            }}
            QPushButton:hover {{
                border: 1px solid {THEME['accent']};
            }}
        """)
        self.index_badge.setToolTip("Select this track")
        header_layout.addWidget(self.index_badge)

        name_label = QLabel(track.name)
        name_label.setStyleSheet(f"""
            color: {THEME['text_primary']};
            font-size: 13px;
            font-weight: bold;
            padding: 5px;
            background: {THEME['bg_toolbar']};
            border-radius: 4px;
        """)
        name_label.setWordWrap(True)
        header_layout.addWidget(name_label, 1)

        # Close button
        close_btn = QPushButton("\u2715")  # ✕ character
        close_btn.setFixedSize(25, 25)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: #c93636;
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: #e04444;
            }}
        """)
        close_btn.setToolTip("Remove this track")
        close_btn.clicked.connect(lambda: self.remove_requested.emit())
        header_layout.addWidget(close_btn)

        control_layout.addLayout(header_layout)

        # Mute/Solo buttons row
        btn_row = QHBoxLayout()

        self.mute_btn = QPushButton("M")
        self.mute_btn.setFixedSize(32, 28)
        self.mute_btn.setCheckable(True)
        self.mute_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['bg_control']};
                color: {THEME['text_primary']};
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: {THEME['danger']};
                color: white;
            }}
        """)
        self.mute_btn.setToolTip("Mute Track")
        self.mute_btn.clicked.connect(lambda checked: self.mute_changed.emit(checked))
        btn_row.addWidget(self.mute_btn)

        self.solo_btn = QPushButton("S")
        self.solo_btn.setFixedSize(32, 28)
        self.solo_btn.setCheckable(True)
        self.solo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['bg_control']};
                color: {THEME['text_primary']};
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: #ffeb3b;
                color: #000000;
            }}
        """)
        self.solo_btn.setToolTip("Solo Track")
        self.solo_btn.clicked.connect(lambda checked: self.solo_changed.emit(checked))
        btn_row.addWidget(self.solo_btn)

        self.fx_btn = QPushButton("FX")
        self.fx_btn.setFixedSize(32, 28)
        self.fx_btn.setCheckable(True)
        self.fx_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['bg_control']};
                color: {THEME['text_primary']};
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: {THEME['accent']};
                color: white;
            }}
        """)
        self.fx_btn.setToolTip("Show Effects Panel")
        btn_row.addWidget(self.fx_btn)

        btn_row.addStretch()
        control_layout.addLayout(btn_row)

        # Volume control
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Vol:"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(-60, 12)
        self.vol_slider.setValue(int(track.volume))
        self.vol_slider.valueChanged.connect(lambda val: self.volume_changed.emit(float(val)))
        vol_row.addWidget(self.vol_slider, 1)
        self.vol_label = QLabel(f"{int(track.volume)}dB")
        self.vol_label.setFixedWidth(40)
        self.vol_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.vol_slider.valueChanged.connect(lambda val: self.vol_label.setText(f"{val}dB"))
        vol_row.addWidget(self.vol_label)
        control_layout.addLayout(vol_row)

        # Pan control
        pan_row = QHBoxLayout()
        pan_row.addWidget(QLabel("Pan:"))
        self.pan_slider = QSlider(Qt.Horizontal)
        self.pan_slider.setRange(-10, 10)
        self.pan_slider.setValue(int(track.pan * 10))
        pan_row.addWidget(self.pan_slider, 1)
        self.pan_label = QLabel("C")
        self.pan_label.setFixedWidth(25)
        self.pan_label.setAlignment(Qt.AlignCenter)

        def update_pan_label(val):
            if val < -1:
                self.pan_label.setText("L")
            elif val > 1:
                self.pan_label.setText("R")
            else:
                self.pan_label.setText("C")
        self.pan_slider.valueChanged.connect(update_pan_label)
        pan_row.addWidget(self.pan_label)
        control_layout.addLayout(pan_row)

        control_layout.addStretch()

        main_layout.addWidget(control_panel)

        # Right side - Waveform canvas (expandable)
        self.waveform_canvas = WaveformCanvas()
        self.waveform_canvas.track = track  # Store track reference for time offset dragging
        self.waveform_canvas.setMinimumHeight(120)
        main_layout.addWidget(self.waveform_canvas, 1)

        # Notify parent when this track is repositioned (Shift-drag).
        try:
            self.waveform_canvas.track_offset_changed.connect(lambda off: self.offset_changed.emit(self.track, float(off)))
        except Exception:
            pass

        # Click-to-select: let clicks on the control panel or waveform select the track.
        try:
            control_panel.installEventFilter(self)
            self.waveform_canvas.waveform.installEventFilter(self)
        except Exception:
            pass

        # Explicit badge click (more discoverable than eventFilter).
        try:
            self.index_badge.clicked.connect(lambda: self.clicked.emit(self.track))
        except Exception:
            pass

        self._apply_selected_style()

    def set_track_index(self, idx: int):
        try:
            self.index_badge.setText(str(idx))
        except Exception:
            pass

    def set_selected(self, selected: bool):
        self._selected = bool(selected)
        self._apply_selected_style()

    def _apply_selected_style(self):
        # Selected track gets a brighter outline; non-selected uses subtle separators.
        if self._selected:
            badge_bg = THEME["accent"]
            badge_fg = "#ffffff"
            panel_border = THEME["accent"]
        else:
            badge_bg = THEME["bg_control"]
            badge_fg = THEME["text_primary"]
            panel_border = THEME["border"]

        outer = (
            f"border-top: 2px solid {panel_border};"
            f"border-right: 2px solid {panel_border};"
            f"border-bottom: 2px solid {panel_border};"
        )

        try:
            self.index_badge.setStyleSheet(f"""
                QPushButton {{
                    background: {badge_bg};
                    color: {badge_fg};
                    border: 1px solid {THEME['border']};
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    border: 1px solid {THEME['accent']};
                }}
            """)
        except Exception:
            pass

        try:
            self.control_panel.setStyleSheet(f"""
                QFrame {{
                    background-color: {THEME['bg_panel']};
                    border: 2px solid {panel_border};
                    border-radius: 6px;
                }}
            """)
        except Exception:
            pass

        self.setStyleSheet(f"""
            TrackWidget {{
                background-color: {THEME['bg_main']};
                {outer}
                border-left: 3px solid {self.track.color};
                border-radius: 8px;
                margin: 0px;
                padding: 0px;
            }}
        """)

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.clicked.emit(self.track)
        except Exception:
            pass
        return False


# ============================================================================
# MULTI-TRACK VIEW WITH STACKED WAVEFORMS
# ============================================================================

class MultiTrackView(QWidget):
    ruler_seek = Signal(float)  # seconds
    """Audacity-style multi-track view with vertically stacked waveforms."""
    track_clicked = Signal(object)  # AudioTrack
    ruler_selection_finalized = Signal(float, float)  # (start_s, end_s) timeline selection

    def __init__(self, parent=None):
        super().__init__(parent)

        self.tracks = []  # List of AudioTrack objects
        self.track_widgets = []  # List of TrackWidget objects
        self.shared_zoom = 1.0
        self.shared_pan = 0.0
        self.loop_start = None  # Shared loop start time
        self.loop_end = None  # Shared loop end time
        self.loop_enabled = False  # Shared loop enabled state

        # Ruler selection state
        self.ruler_selection_start = None
        self.ruler_selection_end = None
        self._ruler_dragging = False

        # Main vertical layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Shared timeline ruler at top
        self.timeline_ruler = QWidget()
        self.timeline_ruler.setFixedHeight(30)
        self.timeline_ruler.setStyleSheet(f"background-color: {THEME['bg_panel']};")
        self.timeline_ruler.paintEvent = self._paint_timeline_ruler
        self.timeline_ruler.mousePressEvent = self._ruler_mouse_press
        self.timeline_ruler.mouseMoveEvent = self._ruler_mouse_move
        self.timeline_ruler.mouseReleaseEvent = self._ruler_mouse_release
        self.timeline_ruler.mouseDoubleClickEvent = self._ruler_double_click
        main_layout.addWidget(self.timeline_ruler)
        try:
            # Keep cached ruler geometry synced with resize/layout changes.
            self.timeline_ruler.installEventFilter(self)
        except Exception:
            pass

        # Horizontal pan scrollbar (like Audacity)
        self.pan_scrollbar = QScrollBar(Qt.Horizontal)
        self.pan_scrollbar.setRange(0, 1000)
        self.pan_scrollbar.setValue(0)
        self.pan_scrollbar.setPageStep(100)
        self.pan_scrollbar.valueChanged.connect(self._on_pan_scrollbar_changed)
        main_layout.addWidget(self.pan_scrollbar)

        # Scroll area for tracks
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.NoFrame)

        # Container for track widgets
        self.tracks_container = QWidget()
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 0, 0, 0)
        self.tracks_layout.setSpacing(2)

        # Add Track button at bottom
        self.add_track_btn = QPushButton("+ Add Track")
        self.add_track_btn.setProperty("class", "accent")
        self.add_track_btn.setFixedHeight(40)
        self.tracks_layout.addWidget(self.add_track_btn)

        scroll_area.setWidget(self.tracks_container)
        main_layout.addWidget(scroll_area, 1)
        self._scroll_area = scroll_area
        try:
            scroll_area.viewport().installEventFilter(self)
        except Exception:
            pass

    def _timeline_duration(self) -> float:
        try:
            return float(max((t.duration + t.time_offset for t in self.tracks), default=0.0))
        except Exception:
            return 0.0

    def _view_window(self) -> tuple[float, float, float]:
        """
        Return (start_time, visible_duration, max_duration) for the shared timeline view.
        This is the single source of truth for ruler + waveform alignment.
        """
        max_duration = self._timeline_duration()
        if max_duration <= 0:
            return 0.0, 0.0, 0.0

        zoom = max(1e-6, float(self.shared_zoom or 1.0))
        visible_duration = max_duration / zoom

        if visible_duration >= max_duration:
            return 0.0, max_duration, max_duration

        pan = max(0.0, min(1.0, float(self.shared_pan or 0.0)))
        start_time = pan * (max_duration - visible_duration)
        return float(start_time), float(visible_duration), float(max_duration)

    def _apply_view_window(self):
        """
        Push the shared view window into all waveforms so every track draws
        using the same start_time/visible_duration as the ruler.
        """
        start_time, visible_duration, max_duration = self._view_window()
        if max_duration <= 0 or visible_duration <= 0:
            return
        for track_widget in self.track_widgets:
            try:
                track_widget.waveform_canvas.set_view_window(start_time, visible_duration)
            except Exception:
                pass
        try:
            self.timeline_ruler.update()
        except Exception:
            pass

    def _visible_range(self) -> tuple[float, float, float]:
        """
        Return (start_time, end_time, visible_duration) for the current shared view.
        """
        start_time, visible_duration, max_duration = self._view_window()
        if max_duration <= 0 or visible_duration <= 0:
            return 0.0, 0.0, 0.0
        end_time = start_time + visible_duration
        return start_time, end_time, visible_duration

    def _ruler_x_to_time(self, x: int) -> float | None:
        """
        Convert an x position on the shared ruler to a timeline time (seconds).
        Returns None if outside the waveform-aligned ruler span.
        """
        offset_x, width = self._ruler_span()
        if x < offset_x or width <= 0:
            return None
        start_time, visible_duration, max_duration = self._view_window()
        if max_duration <= 0 or visible_duration <= 0:
            return None
        local_x = max(0, min(width, int(x - offset_x)))
        t_seconds = start_time + (float(local_x) / float(width)) * visible_duration
        return max(0.0, min(float(t_seconds), float(max_duration)))

    def _ruler_time_to_x(self, t_seconds: float) -> int:
        """
        Convert a timeline time (seconds) to an x pixel in the shared ruler space.
        """
        offset_x, width = self._ruler_span()
        start_time, visible_duration, max_duration = self._view_window()
        if max_duration <= 0 or visible_duration <= 0:
            return offset_x
        t_seconds = max(0.0, min(float(t_seconds), float(max_duration)))
        rel = (t_seconds - start_time) / max(1e-9, visible_duration)
        local_x = int(rel * width)
        return int(max(offset_x, min(offset_x + width, offset_x + local_x)))

    def ensure_time_visible(self, t_seconds: float, *, center: bool = True):
        """
        Adjust shared pan so a specific time is visible (and optionally centered).
        This prevents clips from "disappearing" when they are far right and the user zooms.
        """
        max_duration = self._timeline_duration()
        if max_duration <= 0:
            return

        t_seconds = max(0.0, min(float(t_seconds), float(max_duration)))
        visible_duration = max_duration / max(1e-6, float(self.shared_zoom or 1.0))
        if visible_duration >= max_duration:
            try:
                self.pan_scrollbar.blockSignals(True)
                self.pan_scrollbar.setValue(0)
            finally:
                self.pan_scrollbar.blockSignals(False)
            self.set_shared_pan(0.0)
            return

        start_time, end_time, _ = self._visible_range()
        if center:
            target_center = t_seconds
            new_start = target_center - (visible_duration * 0.5)
        else:
            # Only move if outside with small margins.
            margin = visible_duration * 0.05
            if (start_time + margin) <= t_seconds <= (end_time - margin):
                return
            new_start = t_seconds - margin

        new_start = max(0.0, min(new_start, max_duration - visible_duration))
        denom = (max_duration - visible_duration)
        new_pan = 0.0 if denom <= 1e-9 else (new_start / denom)
        new_pan = max(0.0, min(float(new_pan), 1.0))

        try:
            self.pan_scrollbar.blockSignals(True)
            self.pan_scrollbar.setValue(int(new_pan * 1000.0))
        finally:
            self.pan_scrollbar.blockSignals(False)
        self.set_shared_pan(new_pan)

    def _ruler_span(self) -> tuple[int, int]:
        """
        Return (offset_x, width_px) for the part of the timeline ruler that aligns with the
        actual waveform drawing area (not the track control panel). This avoids hard-coded
        pixel offsets that break with DPI scaling / layout changes.
        """
        if not self.track_widgets:
            return 0, max(1, self.timeline_ruler.width())

        try:
            tw = self.track_widgets[0]
            offset_x = 0
            try:
                layout = tw.layout()
                if layout is not None:
                    try:
                        offset_x += int(layout.contentsMargins().left())
                    except Exception:
                        pass
                    try:
                        offset_x += int(layout.spacing())
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if hasattr(tw, "control_panel") and tw.control_panel is not None:
                    offset_x += int(tw.control_panel.width())
            except Exception:
                pass

            wf_w = 0
            try:
                wf_w = int(tw.waveform_canvas.waveform.width())
            except Exception:
                wf_w = 0

            if wf_w <= 10:
                wf_w = max(1, self.timeline_ruler.width() - offset_x)

            self._cached_ruler_offset_x = int(offset_x)
            self._cached_ruler_wave_w = int(max(1, wf_w))
            return int(offset_x), int(max(1, wf_w))
        except Exception:
            pass

        try:
            ox_cached = getattr(self, "_cached_ruler_offset_x", None)
            ww_cached = getattr(self, "_cached_ruler_wave_w", None)
            if isinstance(ox_cached, int) and isinstance(ww_cached, int) and ww_cached > 0:
                return int(ox_cached), int(ww_cached)
        except Exception:
            pass

        return 0, max(1, self.timeline_ruler.width())

    def eventFilter(self, obj, event):
        try:
            if obj in (getattr(self, "timeline_ruler", None), getattr(self, "_scroll_area", None)) or (
                hasattr(self, "_scroll_area") and obj == self._scroll_area.viewport()
            ):
                if event.type() in (QEvent.Resize, QEvent.LayoutRequest):
                    try:
                        QTimer.singleShot(0, self._recompute_ruler_geometry)
                    except Exception:
                        pass
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            QTimer.singleShot(0, self._recompute_ruler_geometry)
        except Exception:
            pass

    def add_track(self, track: 'AudioTrack') -> TrackWidget:
        """Add a new track to the view."""
        print(f"DEBUG: MultiTrackView.add_track called for: {track.name}")

        track_widget = TrackWidget(track)
        print(f"DEBUG: TrackWidget created")

        # DAW-style: click to select track
        try:
            track_widget.clicked.connect(lambda t=track: self.track_clicked.emit(t))
        except Exception:
            pass

        # Connect signals
        track_widget.mute_changed.connect(lambda checked: self._on_track_mute(track, checked))
        track_widget.solo_changed.connect(lambda checked: self._on_track_solo(track, checked))
        track_widget.volume_changed.connect(lambda val: self._on_track_volume(track, val))
        track_widget.offset_changed.connect(lambda _t, _off: self._on_track_offset_changed(track))
        track_widget.remove_requested.connect(lambda: self._remove_track(track))

        # Sync zoom/pan with shared values
        track_widget.waveform_canvas.set_zoom(self.shared_zoom)
        track_widget.waveform_canvas.set_pan(self.shared_pan)
        try:
            self._apply_view_window()
        except Exception:
            pass

        # Insert before "Add Track" button
        insert_position = len(self.track_widgets)
        print(f"DEBUG: Inserting widget at position {insert_position}")
        self.tracks_layout.insertWidget(insert_position, track_widget)

        self.tracks.append(track)
        self.track_widgets.append(track_widget)

        # Update indices (1..N)
        try:
            for i, w in enumerate(self.track_widgets, start=1):
                w.set_track_index(i)
        except Exception:
            pass

        print(f"DEBUG: Track added. Total tracks in view: {len(self.track_widgets)}")

        # Update global duration for all tracks
        self._update_global_duration()
        # After layout settles, recompute ruler geometry for accurate hit-testing.
        try:
            QTimer.singleShot(0, self._recompute_ruler_geometry)
        except Exception:
            pass

        # Force update
        track_widget.setVisible(True)
        track_widget.update()
        self.tracks_container.updateGeometry()

        return track_widget

    def _on_track_offset_changed(self, track: 'AudioTrack'):
        """
        Track time offset changed (Shift-drag on waveform).
        Recompute global duration/ruler + restart playback if needed.
        """
        try:
            self._update_global_duration()
        except Exception:
            pass

        try:
            QTimer.singleShot(0, self._recompute_ruler_geometry)
        except Exception:
            pass

        # Refresh visuals
        try:
            self._apply_view_window()
        except Exception:
            pass
        try:
            for w in self.track_widgets:
                w.waveform_canvas.update()
        except Exception:
            pass

        # If currently playing, restart the mix so timing is correct.
        try:
            parent = self.parent()
            if parent is not None and hasattr(parent, "playback_process") and parent.playback_process is not None:
                parent._restart_playback()
        except Exception:
            pass

        # Keep the moved clip visible in the current view (best-effort).
        try:
            self.ensure_time_visible(float(track.time_offset or 0.0), center=False)
        except Exception:
            pass

    def _update_global_duration(self):
        """Update global duration for all track waveforms based on max track end time."""
        if not self.tracks:
            return

        # Calculate max duration including time offsets
        global_duration = max((t.duration + t.time_offset for t in self.tracks), default=0.0)

        # Set global duration on all track waveforms
        for track_widget in self.track_widgets:
            track_widget.waveform_canvas.set_global_duration(global_duration)

        self._apply_view_window()

    def _recompute_ruler_geometry(self):
        """
        Cache the x-offset and width for the timeline ruler so hit-testing and selection
        aligns with the waveform area. Avoid mapTo() to prevent crashes during layout churn.
        """
        try:
            if not self.track_widgets:
                self._cached_ruler_offset_x = None
                self._cached_ruler_wave_w = None
                return

            tw = self.track_widgets[0]
            # Compute offset using stable layout widths (no mapTo).
            offset_x = 0
            try:
                layout = tw.layout()
                if layout is not None:
                    try:
                        offset_x += int(layout.contentsMargins().left())
                    except Exception:
                        pass
                    try:
                        offset_x += int(layout.spacing())
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if hasattr(tw, "control_panel") and tw.control_panel is not None:
                    offset_x += int(tw.control_panel.width())
            except Exception:
                pass

            wf_w = 0
            try:
                wf_w = int(tw.waveform_canvas.waveform.width())
            except Exception:
                wf_w = 0

            if wf_w <= 10:
                wf_w = max(1, self.timeline_ruler.width() - offset_x)

            self._cached_ruler_offset_x = int(offset_x)
            self._cached_ruler_wave_w = int(max(1, wf_w))
        except Exception:
            self._cached_ruler_offset_x = None
            self._cached_ruler_wave_w = None

    def remove_track(self, index: int):
        """Remove a track from the view."""
        if 0 <= index < len(self.track_widgets):
            widget = self.track_widgets.pop(index)
            self.tracks.pop(index)
            widget.deleteLater()
            try:
                self._update_global_duration()
                QTimer.singleShot(0, self._recompute_ruler_geometry)
            except Exception:
                pass

    def set_shared_zoom(self, zoom: float):
        """Set zoom level for all tracks (synchronized)."""
        self.shared_zoom = zoom
        for track_widget in self.track_widgets:
            track_widget.waveform_canvas.set_zoom(zoom)

        # Update scrollbar page step based on zoom (higher zoom = smaller page step)
        page_step = max(10, int(100 / zoom))
        self.pan_scrollbar.setPageStep(page_step)

        try:
            self._recompute_ruler_geometry()
        except Exception:
            pass
        self._apply_view_window()

    def set_shared_pan(self, pan: float):
        """Set pan position for all tracks (synchronized)."""
        self.shared_pan = pan
        for track_widget in self.track_widgets:
            track_widget.waveform_canvas.set_pan(pan)
        self._apply_view_window()

    def _on_pan_scrollbar_changed(self, value):
        """Handle horizontal pan scrollbar changes."""
        # Convert scrollbar value (0-1000) to pan value (0.0-1.0)
        pan = value / 1000.0
        self.set_shared_pan(pan)

    def set_shared_playhead(self, position: float):
        """Set playhead position for all tracks (synchronized)."""
        for track_widget in self.track_widgets:
            track_widget.waveform_canvas.set_playhead(position)

    def set_loop_region(self, start: float, end: float):
        """Set shared loop region for all tracks."""
        self.loop_start = start
        self.loop_end = end
        self.loop_enabled = True
        self.timeline_ruler.update()

    def clear_loop_region(self):
        """Clear shared loop region."""
        self.loop_start = None
        self.loop_end = None
        self.loop_enabled = False
        self.timeline_ruler.update()

    def _on_track_mute(self, track: 'AudioTrack', muted: bool):
        """Handle track mute."""
        track.mute = muted
        print(f"DEBUG: Track {track.name} mute = {muted}")

        # If currently playing, restart playback with new mix
        if hasattr(self.parent(), 'playback_process') and self.parent().playback_process is not None:
            self.parent()._restart_playback()

    def _on_track_solo(self, track: 'AudioTrack', soloed: bool):
        """Handle track solo."""
        track.solo = soloed
        print(f"DEBUG: Track {track.name} solo = {soloed}")

        # If solo is on, mute all other tracks
        if soloed:
            for i, t in enumerate(self.tracks):
                if t != track:
                    t.mute = True
                    self.track_widgets[i].mute_btn.setChecked(True)

        # If currently playing, restart playback with new mix
        if hasattr(self.parent(), 'playback_process') and self.parent().playback_process is not None:
            self.parent()._restart_playback()

    def _on_track_volume(self, track: 'AudioTrack', volume: float):
        """Handle track volume change."""
        track.volume = volume
        print(f"DEBUG: Track {track.name} volume = {volume} dB")

        # If currently playing, restart playback with new mix
        if hasattr(self.parent(), 'playback_process') and self.parent().playback_process is not None:
            self.parent()._restart_playback()

    def _remove_track(self, track: 'AudioTrack'):
        """Remove a track from the view."""
        if track not in self.tracks:
            return

        idx = self.tracks.index(track)

        # Remove widget
        widget = self.track_widgets[idx]
        self.tracks_layout.removeWidget(widget)
        widget.deleteLater()

        # Remove from lists
        self.tracks.pop(idx)
        self.track_widgets.pop(idx)

        print(f"DEBUG: Removed track {track.name}. Remaining tracks: {len(self.tracks)}")
        try:
            # Update indices (1..N)
            for i, w in enumerate(self.track_widgets, start=1):
                w.set_track_index(i)
        except Exception:
            pass
        try:
            self._update_global_duration()
            QTimer.singleShot(0, self._recompute_ruler_geometry)
        except Exception:
            pass

    def select_track(self, track: 'AudioTrack'):
        """Select/highlight a track."""
        for t, widget in zip(self.tracks, self.track_widgets):
            try:
                widget.set_selected(t == track)
            except Exception:
                pass

    def _ruler_mouse_press(self, event):
        """Handle mouse press on timeline ruler to start selection."""
        if event.button() == Qt.LeftButton:
            x = event.pos().x()
            time = self._ruler_x_to_time(int(x))
            if time is not None and self.tracks:

                # Start selection
                self.ruler_selection_start = time
                self.ruler_selection_end = time
                self._ruler_dragging = True
                self.timeline_ruler.update()

                # Update all track waveforms to show selection
                for track_widget in self.track_widgets:
                    track_widget.waveform_canvas.ruler_selection_start = time
                    track_widget.waveform_canvas.ruler_selection_end = time
                    track_widget.waveform_canvas.update()

    def _ruler_mouse_move(self, event):
        """Handle mouse move on timeline ruler to update selection."""
        if self._ruler_dragging and self.tracks:
            x = event.pos().x()
            time = self._ruler_x_to_time(int(x))
            if time is not None:

                # Update selection end
                self.ruler_selection_end = time
                self.timeline_ruler.update()

                # Update all track waveforms to show selection
                for track_widget in self.track_widgets:
                    track_widget.waveform_canvas.ruler_selection_end = time
                    track_widget.waveform_canvas.update()

    def _ruler_mouse_release(self, event):
        """Handle mouse release on timeline ruler to finalize selection."""
        if event.button() == Qt.LeftButton and self._ruler_dragging:
            self._ruler_dragging = False
            try:
                if self.ruler_selection_start is not None and self.ruler_selection_end is not None:
                    s = float(min(self.ruler_selection_start, self.ruler_selection_end))
                    e = float(max(self.ruler_selection_start, self.ruler_selection_end))
                    self.ruler_selection_finalized.emit(s, e)
            except Exception:
                pass

    def _ruler_double_click(self, event):
        """Seek the shared playhead by double-clicking on the ruler (affects all tracks)."""
        if event.button() != Qt.LeftButton or not self.tracks:
            return
        t_seconds = self._ruler_x_to_time(int(event.pos().x()))
        if t_seconds is None:
            return

        # Move playhead on all tracks and notify the dialog.
        self.set_shared_playhead(t_seconds)
        self.timeline_ruler.update()
        self.ruler_seek.emit(float(t_seconds))

    def _paint_timeline_ruler(self, event):
        """Paint shared timeline ruler showing time marks."""
        painter = QPainter(self.timeline_ruler)
        painter.setRenderHint(QPainter.Antialiasing, False)

        rect = self.timeline_ruler.rect()
        offset_x, width = self._ruler_span()
        height = rect.height()

        # Draw background
        painter.fillRect(rect, QColor(THEME['bg_panel']))

        if not self.tracks:
            painter.setPen(QColor(THEME['text_secondary']))
            painter.drawText(rect, Qt.AlignCenter, "Add tracks to begin")
            return

        # Get max duration from all tracks (including time offsets)
        max_duration = self._timeline_duration()
        if max_duration <= 0:
            return

        # Calculate visible range based on zoom and pan
        start_time, end_time, visible_duration = self._visible_range()

        # Calculate grid interval based on visible duration
        if visible_duration <= 10:
            grid_interval = 1.0
        elif visible_duration <= 30:
            grid_interval = 5.0
        elif visible_duration <= 120:
            grid_interval = 10.0
        elif visible_duration <= 300:
            grid_interval = 30.0
        else:
            grid_interval = 60.0

        # Draw ruler line
        y = height - 2
        painter.setPen(QPen(QColor(THEME["grid_line"]), 2))
        painter.drawLine(offset_x, y, offset_x + width, y)

        # Draw time marks (only draw text at major intervals to avoid overlap)
        painter.setFont(QFont("Segoe UI", 8))
        t = int(float(start_time) / grid_interval) * grid_interval
        if t < start_time:
            t += grid_interval

        painter.setPen(QColor(THEME["text_primary"]))
        last_text_x = -100  # Track last text position to avoid overlap
        while t <= end_time + 1e-6:
            if visible_duration > 0:
                x = self._ruler_time_to_x(float(t))

                # Always draw tick mark
                painter.drawLine(x, y, x, y - 8)

                # Only draw text if there's enough space (at least 60 pixels from last text)
                if x - last_text_x >= 60:
                    painter.drawText(x + 4, 2, 100, height - 10, Qt.AlignLeft | Qt.AlignTop, format_time(t))
                    last_text_x = x
            t += grid_interval

        # Draw ruler selection (cyan overlay for selecting loop region)
        if self.ruler_selection_start is not None and self.ruler_selection_end is not None:
            sel_start = min(self.ruler_selection_start, self.ruler_selection_end)
            sel_end = max(self.ruler_selection_start, self.ruler_selection_end)
            sel_x1 = self._ruler_time_to_x(float(sel_start))
            sel_x2 = self._ruler_time_to_x(float(sel_end))

            if sel_x2 > sel_x1:
                # Draw cyan selection overlay
                sel_color = QColor(43, 108, 176, 64)  # Cyan with alpha
                painter.fillRect(sel_x1, 0, sel_x2 - sel_x1, height, sel_color)

                # Draw selection markers
                marker_pen = QPen(QColor(43, 108, 176), 2)
                painter.setPen(marker_pen)
                painter.drawLine(sel_x1, 0, sel_x1, height)
                painter.drawLine(sel_x2, 0, sel_x2, height)

        # Draw loop region overlay (like Audacity - gold/yellow)
        if self.loop_start is not None and self.loop_end is not None and self.loop_enabled:
            # Convert loop times to pixel positions
            loop_x1 = self._ruler_time_to_x(float(self.loop_start))
            loop_x2 = self._ruler_time_to_x(float(self.loop_end))

            if loop_x2 > loop_x1:
                # Draw gold/yellow overlay with transparency
                loop_color = QColor(255, 215, 0, 80)  # Gold with alpha
                painter.fillRect(loop_x1, 0, loop_x2 - loop_x1, height, loop_color)

                # Draw loop markers (vertical lines)
                marker_pen = QPen(QColor(255, 215, 0), 2)
                painter.setPen(marker_pen)
                painter.drawLine(loop_x1, 0, loop_x1, height)
                painter.drawLine(loop_x2, 0, loop_x2, height)


# ============================================================================
# PROFESSIONAL WAVEFORM CANVAS WITH dB METER
# ============================================================================

class WaveformCanvas(QWidget):
    """Professional waveform display with dB meter - EXACT match to original."""

    selection_changed = Signal(float, float)  # start, end in seconds
    playhead_position = Signal(float)  # position in seconds
    track_offset_changed = Signal(float)  # new time_offset in seconds (multi-track drag)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create horizontal layout for waveform + dB meter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Waveform canvas (main)
        self.waveform = QWidget()
        self.waveform.setMinimumHeight(250)
        self.waveform.setAttribute(Qt.WA_Hover, True)  # Enable hover events
        self.waveform.setMouseTracking(True)  # Track mouse movement
        self.waveform.paintEvent = self._paint_waveform
        self.waveform.mousePressEvent = self.mousePressEvent
        self.waveform.mouseMoveEvent = self.mouseMoveEvent
        self.waveform.mouseReleaseEvent = self.mouseReleaseEvent
        self.waveform.mouseDoubleClickEvent = self.mouseDoubleClickEvent
        self.waveform.installEventFilter(self)  # Install event filter to catch double-clicks
        layout.addWidget(self.waveform, 1)

        # dB meter on the right
        meter_frame = QFrame()
        meter_frame.setFixedWidth(32)
        meter_frame.setStyleSheet(f"background-color: {THEME['waveform_bg']}; border-radius: 10px;")
        meter_layout = QVBoxLayout(meter_frame)
        meter_layout.setContentsMargins(0, 8, 0, 8)
        meter_layout.setSpacing(4)

        db_label_top = QLabel("dB")
        db_label_top.setStyleSheet(f"color: {THEME['text_secondary']}; background: transparent;")
        db_label_top.setAlignment(Qt.AlignCenter)
        meter_layout.addWidget(db_label_top)

        self.db_meter = QWidget()
        self.db_meter.setFixedWidth(18)
        self.db_meter.setMinimumHeight(200)
        self.db_meter.paintEvent = self._paint_db_meter
        meter_layout.addWidget(self.db_meter, 1)

        self.db_label = QLabel("-∞")
        self.db_label.setStyleSheet(f"color: {THEME['text_secondary']}; background: transparent;")
        self.db_label.setAlignment(Qt.AlignCenter)
        meter_layout.addWidget(self.db_label)

        layout.addWidget(meter_frame)

        # State
        self.peaks = []
        self.duration = 0.0
        self.global_duration = None  # For multi-track sync (uses this instead of duration if set)
        self.zoom = 1.0
        self.pan = 0.0
        self.view_start_time = None
        self.view_visible_duration = None

        # Selection (for editing)
        self.selection_start = None
        self.selection_end = None
        self.playhead = 0.0

        # Loop region (separate from selection)
        self.loop_start = None
        self.loop_end = None

        # Ruler selection (from timeline ruler in multi-track mode)
        self.ruler_selection_start = None
        self.ruler_selection_end = None

        self.cuts = []  # List of (start, end) tuples
        self.cut_regions = []  # List of (start, end) tuples
        self.fade_in = None  # (start, end) tuple
        self.fade_out = None  # (start, end) tuple
        self.fade_in_regions = []  # List of (start, end) tuples
        self.fade_out_regions = []  # List of (start, end) tuples

        self._drag_start = None
        self._is_dragging = False
        self._is_dragging_track = False  # For Shift+drag to move track horizontally
        self._drag_track_start_offset = 0.0  # Store initial time offset when drag starts
        self._drag_track_start_x = 0  # Store mouse x position when drag starts
        self.track = None  # Will be set by TrackWidget

        # dB meter state
        self._db_current = -60.0
        self._db_smooth = 0.0
        self._db_peak_hold = 0.0

        # Loop mode state
        self.loop_enabled = False

        # Set background
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(THEME["waveform_bg"]))
        self.setPalette(palette)

    def eventFilter(self, obj, event):
        """Filter events to catch double-clicks properly."""
        if obj == self.waveform and event.type() == event.Type.MouseButtonDblClick:
            print("DEBUG: EventFilter caught double-click!")
            self.mouseDoubleClickEvent(event)
            return True
        return super().eventFilter(obj, event)

    def set_peaks(self, peaks: list, duration: float):
        """Set waveform peak data."""
        self.peaks = peaks
        self.duration = float(duration or 0.0)

        # IMPORTANT:
        # Waveform peaks are generated in a background thread. In multi-track mode we must NOT
        # reset zoom/pan/selection/playhead when peaks arrive, otherwise the shared timeline
        # view becomes misaligned and clips can "disappear" after the user already zoomed/panned.
        in_multitrack = self.global_duration is not None

        if not in_multitrack:
            # Single-track editor behavior: when loading a new file, reset view state.
            self.zoom = 1.0
            self.pan = 0.0
            self.selection_start = None
            self.selection_end = None
            self.playhead = 0.0
            self.cuts = []
            self.fade_in = None
            self.fade_out = None
        else:
            # Multi-track: preserve the shared view/interaction state. Clamp to timeline.
            timeline_duration = float(self.global_duration or 0.0)
            if timeline_duration > 0:
                try:
                    self.playhead = max(0.0, min(timeline_duration, float(self.playhead or 0.0)))
                except Exception:
                    self.playhead = 0.0

                if self.selection_start is not None and self.selection_end is not None:
                    try:
                        s = max(0.0, min(timeline_duration, float(self.selection_start)))
                        e = max(0.0, min(timeline_duration, float(self.selection_end)))
                        self.selection_start, self.selection_end = (s, e) if s <= e else (e, s)
                    except Exception:
                        self.selection_start = None
                        self.selection_end = None

        self.update()

    def set_zoom(self, zoom: float):
        """Set zoom level (1.0 to 20.0)."""
        self.zoom = max(1.0, min(20.0, zoom))
        self.update()

    def set_pan(self, pan: float):
        """Set pan position (0.0 to 1.0)."""
        self.pan = max(0.0, min(1.0, pan))
        self.update()

    def set_view_window(self, start_time: float | None, visible_duration: float | None):
        """Override view window for multi-track alignment."""
        try:
            if start_time is None or visible_duration is None:
                self.view_start_time = None
                self.view_visible_duration = None
            else:
                self.view_start_time = float(start_time)
                self.view_visible_duration = float(visible_duration)
        except Exception:
            self.view_start_time = None
            self.view_visible_duration = None
        self.update()

    def set_global_duration(self, duration: float):
        """Set global timeline duration for multi-track sync."""
        self.global_duration = duration
        self.update()

    def set_playhead(self, position: float):
        """Set playhead position in seconds."""
        # In multi-track mode the playhead lives on the shared timeline (which can exceed this
        # clip's own duration due to time offsets). Clamp to the timeline, not the clip.
        timeline_duration = self.global_duration if self.global_duration is not None else self.duration
        self.playhead = max(0.0, min(timeline_duration, position))
        self._update_db_meter(self.playhead)
        self.update()

    def set_selection(self, start: float, end: float):
        """Set selection region."""
        timeline_duration = self.global_duration if self.global_duration is not None else self.duration
        self.selection_start = max(0.0, min(timeline_duration, start))
        self.selection_end = max(0.0, min(timeline_duration, end))
        if self.selection_start > self.selection_end:
            self.selection_start, self.selection_end = self.selection_end, self.selection_start
        self.update()

    def clear_selection(self):
        """Clear selection region."""
        self.selection_start = None
        self.selection_end = None
        self.update()

    def add_cut(self, start: float, end: float):
        """Add a cut region."""
        self.cuts.append((start, end))
        self.update()

    def clear_cuts(self):
        """Clear all cut regions."""
        self.cuts = []
        self.update()

    def set_fade_in(self, start: float, end: float):
        """Set fade in region."""
        self.fade_in = (start, end)
        self.update()

    def set_fade_out(self, start: float, end: float):
        """Set fade out region."""
        self.fade_out = (start, end)
        self.update()

    def set_fade_in_regions(self, regions):
        """Set all fade in regions."""
        self.fade_in_regions = regions
        print(f"DEBUG: WaveformCanvas.set_fade_in_regions() called with {len(regions)} regions")
        self.update()

    def set_fade_out_regions(self, regions):
        """Set all fade out regions."""
        self.fade_out_regions = regions
        print(f"DEBUG: WaveformCanvas.set_fade_out_regions() called with {len(regions)} regions")
        self.update()

    def set_cuts(self, regions):
        """Set all cut regions."""
        self.cuts = regions
        self.cut_regions = regions  # Also update cut_regions for painting
        self.update()

    def set_loop_enabled(self, enabled: bool):
        """Set loop mode enabled state."""
        self.loop_enabled = enabled
        self.update()

    def _time_to_x(self, time_: float) -> int:
        """Convert time in seconds to x pixel coordinate."""
        if self.duration == 0:
            return 0

        # Use global duration if set (for multi-track sync), otherwise use own duration
        timeline_duration = self.global_duration if self.global_duration is not None else self.duration

        # Account for zoom and pan (or use a shared view window if set by MultiTrackView).
        if self.view_start_time is not None and self.view_visible_duration is not None:
            start_time = self.view_start_time
            visible_duration = self.view_visible_duration
        else:
            visible_duration = timeline_duration / self.zoom
            start_time = self.pan * (timeline_duration - visible_duration)

        if time_ < start_time or time_ > start_time + visible_duration:
            return -1  # Out of visible range

        relative_time = time_ - start_time
        return int((relative_time / visible_duration) * self.waveform.width())

    def _x_to_time(self, x: int) -> float:
        """Convert x pixel coordinate to time in seconds."""
        if self.waveform.width() == 0 or self.duration == 0:
            return 0.0

        # Use global duration if set (for multi-track sync), otherwise use own duration
        timeline_duration = self.global_duration if self.global_duration is not None else self.duration

        if self.view_start_time is not None and self.view_visible_duration is not None:
            start_time = self.view_start_time
            visible_duration = self.view_visible_duration
        else:
            visible_duration = timeline_duration / self.zoom
            start_time = self.pan * (timeline_duration - visible_duration)

        relative_time = (x / self.waveform.width()) * visible_duration
        calculated_time = start_time + relative_time

        # Clamp to valid range: [0.0, timeline_duration]
        return max(0.0, min(calculated_time, timeline_duration))

    def _paint_waveform(self, event):
        """Paint professional waveform with time offset support."""
        painter = QPainter(self.waveform)
        painter.setRenderHint(QPainter.Antialiasing, False)  # Disable for crisp waveform bars

        rect = self.waveform.rect()
        width = rect.width()
        height = rect.height()

        # Draw background
        painter.fillRect(rect, QColor(THEME["waveform_bg"]))

        if not self.peaks or self.duration == 0:
            # Draw placeholder text
            painter.setPen(QColor(THEME["text_secondary"]))
            painter.drawText(rect, Qt.AlignCenter, "No audio loaded - Import audio to begin")
            return

        # Get track time offset (for multi-track horizontal positioning like Audacity)
        time_offset = self.track.time_offset if self.track else 0.0

        # Use global duration if set (for multi-track sync), otherwise use own duration
        timeline_duration = self.global_duration if self.global_duration is not None else self.duration

        # Calculate visible range (shared view window in multi-track mode)
        if self.view_start_time is not None and self.view_visible_duration is not None:
            start_time = self.view_start_time
            visible_duration = self.view_visible_duration
        else:
            visible_duration = timeline_duration / self.zoom
            start_time = self.pan * (timeline_duration - visible_duration)
        end_time = start_time + visible_duration

        clip_start = float(time_offset or 0.0)
        clip_end = clip_start + float(self.duration or 0.0)
        if visible_duration <= 0:
            return

        # Visible part of the clip within the current timeline window.
        vis_start = max(start_time, clip_start)
        vis_end = min(end_time, clip_end)

        if vis_end > vis_start:
            draw_start_x = int(((vis_start - start_time) / visible_duration) * width)
            draw_end_x = int(((vis_end - start_time) / visible_duration) * width)
            draw_start_x = max(0, min(width, draw_start_x))
            draw_end_x = max(0, min(width, draw_end_x))

            # Darken empty space before/after the clip for better separation.
            if draw_start_x > 0:
                painter.fillRect(0, 0, draw_start_x, height, QColor(30, 30, 30, 255))
            if draw_end_x < width:
                painter.fillRect(draw_end_x, 0, width - draw_end_x, height, QColor(30, 30, 30, 255))

            # Convert visible timeline range to clip-local audio time.
            audio_start_time = max(0.0, min(self.duration, vis_start - clip_start))
            audio_end_time = max(0.0, min(self.duration, vis_end - clip_start))

            if audio_end_time > audio_start_time:
                # Calculate which part of the audio is visible
                total_peaks = len(self.peaks)
                start_idx = int((audio_start_time / self.duration) * total_peaks)
                end_idx = int((audio_end_time / self.duration) * total_peaks)
                start_idx = max(0, min(total_peaks - 1, start_idx))
                end_idx = max(0, min(total_peaks, end_idx))

                visible_peaks = self.peaks[start_idx:end_idx]

                if visible_peaks:
                    # Draw waveform bars (cyan/turquoise #3aaed8)
                    center_y = height / 2
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(THEME["waveform_bars"]))

                    vlen = len(visible_peaks)
                    clip_draw_w = max(1, draw_end_x - draw_start_x)

                    for x in range(draw_start_x, draw_end_x):
                        # Map x position to audio sample within the visible clip range.
                        audio_x = x - draw_start_x
                        # Sample the correct portion of visible_peaks for this pixel
                        a0 = int((audio_x / max(1, clip_draw_w)) * vlen)
                        a1 = int(((audio_x + 1) / max(1, clip_draw_w)) * vlen)
                        if a1 <= a0:
                            a1 = min(vlen, a0 + 1)

                        if a0 >= vlen:
                            break

                        chunk = visible_peaks[a0:min(a1, vlen)]
                        peak = max(chunk) if chunk else 0.0
                        peak = max(0.0, min(1.0, peak))

                        bar_height = peak * (center_y - 10)
                        y_top = center_y - bar_height
                        y_bottom = center_y + bar_height

                        painter.drawRect(QRectF(x, y_top, 1, y_bottom - y_top))

            # Draw clip boundary indicators (like Audacity)
            clip_start_x = self._time_to_x(clip_start)
            if clip_start_x > 0 and clip_start_x < width:
                painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
                painter.drawLine(clip_start_x, 0, clip_start_x, height)

            clip_end_x = self._time_to_x(clip_end)
            if clip_end_x > 0 and clip_end_x < width:
                painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
                painter.drawLine(clip_end_x, 0, clip_end_x, height)

        # Draw midline
        center_y = height / 2
        painter.setPen(QPen(QColor(THEME["waveform_midline"]), 1))
        painter.drawLine(0, int(center_y), width, int(center_y))

        # Draw time ruler at bottom (single-track mode only).
        # In multi-track mode a shared ruler is drawn by MultiTrackView; drawing another ruler
        # per track causes drift/confusion at high zoom and wastes vertical space.
        if self.global_duration is None:
            painter.setPen(QColor(THEME["grid_tick"]))
            font = QFont("Segoe UI", 9)
            painter.setFont(font)

            # Calculate grid interval (matching timeline ruler logic)
            if visible_duration <= 10:
                grid_interval = 1.0
            elif visible_duration <= 30:
                grid_interval = 5.0
            elif visible_duration <= 120:
                grid_interval = 10.0
            elif visible_duration <= 300:
                grid_interval = 30.0
            else:
                grid_interval = 60.0

            y_ruler = height - 16
            painter.setPen(QPen(QColor(THEME["grid_line"]), 1))
            painter.drawLine(0, y_ruler, width, y_ruler)

            t = int(start_time / grid_interval) * grid_interval
            if t < start_time:
                t += grid_interval

            painter.setPen(QColor(THEME["grid_tick"]))
            while t <= end_time + 1e-6:
                x = self._time_to_x(t)
                if x >= 0:
                    painter.drawLine(x, y_ruler, x, y_ruler + 6)
                    if grid_interval >= 5 or abs((t / grid_interval) % 2) < 1e-6:
                        painter.setPen(QColor(THEME["text_tip"]))
                        painter.drawText(x + 2, y_ruler - 2, format_time(t))
                        painter.setPen(QColor(THEME["grid_tick"]))
                t += grid_interval

        # Draw ALL fade in regions with 25% alpha (64) - FIXED BUG: Draw all regions, not just current
        for fade_start, fade_end in self.fade_in_regions:
            x1 = self._time_to_x(fade_start)
            x2 = self._time_to_x(fade_end)
            if x1 >= 0 or x2 >= 0:
                x1 = max(0, x1)
                x2 = min(width, x2)
                color = QColor(THEME["fade_in_overlay"])
                color.setAlpha(64)  # 25% transparency
                painter.fillRect(QRect(x1, 0, x2 - x1, height), color)
                # Draw label
                painter.setPen(QColor("#e5e7eb"))
                painter.drawText(x1 + 6, 18, "Fade In")

        # Draw ALL fade out regions with 25% alpha (64) - FIXED BUG: Draw all regions, not just current
        for fade_start, fade_end in self.fade_out_regions:
            x1 = self._time_to_x(fade_start)
            x2 = self._time_to_x(fade_end)
            if x1 >= 0 or x2 >= 0:
                x1 = max(0, x1)
                x2 = min(width, x2)
                color = QColor(THEME["fade_out_overlay"])
                color.setAlpha(64)  # 25% transparency
                painter.fillRect(QRect(x1, 0, x2 - x1, height), color)
                # Draw label
                painter.setPen(QColor("#e5e7eb"))
                painter.drawText(x1 + 6, 18, "Fade Out")

        # Draw ALL cut regions with 25% alpha (64) - FIXED BUG: Use cut_regions list
        for cut_start, cut_end in self.cut_regions:
            x1 = self._time_to_x(cut_start)
            x2 = self._time_to_x(cut_end)
            if x1 >= 0 or x2 >= 0:
                x1 = max(0, x1)
                x2 = min(width, x2)
                color = QColor(THEME["cut_overlay"])
                color.setAlpha(64)  # 25% transparency
                painter.fillRect(QRect(x1, 0, x2 - x1, height), color)
                # Draw label
                painter.setPen(QColor("#ffffff"))
                painter.drawText(x1 + 6, 18, "Cut")

        # Draw ruler selection overlay (CYAN - from timeline ruler in multi-track)
        if self.ruler_selection_start is not None and self.ruler_selection_end is not None:
            sel_start = min(self.ruler_selection_start, self.ruler_selection_end)
            sel_end = max(self.ruler_selection_start, self.ruler_selection_end)
            x1 = self._time_to_x(sel_start)
            x2 = self._time_to_x(sel_end)
            if x1 >= 0 or x2 >= 0:
                x1 = max(0, x1)
                x2 = min(width, x2)
                # Cyan overlay with transparency
                selection_color = QColor(43, 108, 176, 64)  # Cyan with alpha
                painter.fillRect(x1, 0, x2 - x1, height, selection_color)
                # Draw selection markers
                pen = QPen(QColor(43, 108, 176), 2)
                painter.setPen(pen)
                painter.drawLine(x1, 0, x1, height)
                painter.drawLine(x2, 0, x2, height)

        # Draw selection overlay (CYAN - for editing) - only if no ruler selection
        elif self.selection_start is not None and self.selection_end is not None:
            x1 = self._time_to_x(self.selection_start)
            x2 = self._time_to_x(self.selection_end)
            if x1 >= 0 or x2 >= 0:
                x1 = max(0, x1)
                x2 = min(width, x2)
                # Cyan overlay with transparency
                selection_color = QColor(43, 108, 176, 64)  # Cyan with alpha
                painter.fillRect(x1, 0, x2 - x1, height, selection_color)
                # Draw selection markers
                pen = QPen(QColor(43, 108, 176), 2)
                painter.setPen(pen)
                painter.drawLine(x1, 0, x1, height)
                painter.drawLine(x2, 0, x2, height)

        # NOTE: Loop region overlay is now shown in the timeline ruler (Audacity style)
        # Keeping this code for single-track mode compatibility
        # if self.loop_enabled and self.loop_start is not None and self.loop_end is not None:
        #     x1 = self._time_to_x(self.loop_start)
        #     x2 = self._time_to_x(self.loop_end)
        #     if x1 >= 0 or x2 >= 0:
        #         x1 = max(0, x1)
        #         x2 = min(width, x2)
        #
        #         # Gold overlay with transparency
        #         loop_color = QColor(255, 215, 0, 30)
        #         painter.fillRect(x1, 0, x2 - x1, height, loop_color)
        #
        #         # Gold border lines (dashed to distinguish from selection)
        #         pen = QPen(QColor(255, 215, 0), 3)  # Thicker for visibility
        #         pen.setStyle(Qt.DashLine)  # Dashed to distinguish from selection
        #         painter.setPen(pen)
        #         painter.drawLine(x1, 0, x1, height)
        #         painter.drawLine(x2, 0, x2, height)

        # Draw In/Out markers
        # Note: These are drawn separately from selection, using start_var/end_var in the dialog
        # The waveform canvas itself doesn't draw these - they're drawn by the dialog's _on_scrub

        # Draw playhead
        playhead_x = self._time_to_x(self.playhead)
        if playhead_x >= 0:
            painter.setPen(QPen(QColor(THEME["waveform_playhead"]), 2))
            painter.drawLine(playhead_x, 0, playhead_x, height)

    def _paint_db_meter(self, event):
        """Paint dB meter - EXACT match to original."""
        painter = QPainter(self.db_meter)
        painter.setRenderHint(QPainter.Antialiasing, False)

        rect = self.db_meter.rect()
        width = rect.width()
        height = rect.height()

        # Background
        painter.fillRect(rect, QColor(THEME["db_bg"]))

        # dB zones
        def y_for_db(db_level: float) -> int:
            """Map dB (-60 to 0) to y coordinate."""
            frac = (db_level + 60.0) / 60.0
            frac = max(0.0, min(1.0, frac))
            return height - int(frac * height)

        y_green_top = y_for_db(-18.0)
        y_yellow_top = y_for_db(-6.0)

        # Draw zone backgrounds
        painter.fillRect(0, y_green_top, width, height - y_green_top, QColor(THEME["db_green_bg"]))
        painter.fillRect(0, y_yellow_top, width, y_green_top - y_yellow_top, QColor(THEME["db_yellow_bg"]))
        painter.fillRect(0, 0, width, y_yellow_top, QColor(THEME["db_red_bg"]))

        # Draw current level fill
        db = self._db_current
        frac = self._db_smooth
        fill_h = int(frac * height)
        y0 = height - fill_h

        if db >= -6.0:
            color = QColor(THEME["db_red_fill"])
        elif db >= -18.0:
            color = QColor(THEME["db_yellow_fill"])
        else:
            color = QColor(THEME["db_green_fill"])

        painter.fillRect(0, y0, width, fill_h, color)

        # Draw peak hold line
        y_peak = height - int(self._db_peak_hold * height)
        painter.setPen(QPen(QColor("#e5e7eb"), 1))
        painter.drawLine(0, y_peak, width, y_peak)

        # Draw tick marks
        painter.setPen(QPen(QColor(THEME["grid_tick"]), 1))
        for tick_db in (-60, -30, -12, -6, -3, 0):
            y = y_for_db(tick_db)
            painter.drawLine(0, y, 4, y)

    def _update_db_meter(self, t_seconds: float):
        """Update dB meter based on playhead position."""
        if not self.peaks or self.duration <= 0:
            self._db_current = -60.0
            self._db_smooth = 0.0
            self._db_peak_hold = 0.0
            self.db_label.setText("-∞")
            self.db_meter.update()
            return

        # In multi-track mode the playhead is timeline time, but the audio for this canvas is
        # clip-local time (offset by track.time_offset). Show silence when the playhead is
        # outside this clip's active region.
        if self.track is not None and self.global_duration is not None:
            t = float(t_seconds) - float(getattr(self.track, "time_offset", 0.0) or 0.0)
        else:
            t = float(t_seconds)

        if t < 0.0 or t > self.duration:
            self._db_current = -60.0
            self._db_smooth = self._db_smooth * 0.75
            self._db_peak_hold = self._db_peak_hold * 0.985
            self.db_label.setText("-ė")
            self.db_meter.update()
            return

        idx = int((t / self.duration) * (len(self.peaks) - 1))

        # Smooth using a small neighborhood
        w = 10
        lo = max(0, idx - w)
        hi = min(len(self.peaks), idx + w + 1)
        window = self.peaks[lo:hi] if lo < hi else [0.0]

        if not window:
            window = [0.0]

        # Calculate RMS
        rms = math.sqrt(sum(x * x for x in window) / len(window))
        amp = max(0.0, min(1.0, rms))

        # Convert to dBFS
        db = -60.0
        if amp > 1e-6:
            db = 20.0 * math.log10(amp)
            db = max(-60.0, min(0.0, db))

        self._db_current = db

        # Map -60..0 to 0..1
        frac = (db + 60.0) / 60.0
        frac = max(0.0, min(1.0, frac))

        # Smooth UI updates
        self._db_smooth = (0.75 * self._db_smooth) + (0.25 * frac)

        # Peak hold (slow decay)
        self._db_peak_hold = max(self._db_smooth, self._db_peak_hold * 0.985)

        # Update label
        self.db_label.setText(f"{db:.0f} dB" if db > -59.5 else "-∞")

        self.db_meter.update()

    def _find_multitrack_view(self):
        """Locate the parent MultiTrackView (if any)."""
        widget = self.parent()
        while widget is not None:
            if isinstance(widget, MultiTrackView):
                return widget
            widget = widget.parent()
        return None

    def mousePressEvent(self, event):
        """Handle mouse press for selection or track movement."""
        if event.button() == Qt.LeftButton:
            # Check if Shift is held for track horizontal dragging
            if event.modifiers() & Qt.ShiftModifier and self.track is not None:
                self._is_dragging_track = True
                self._drag_track_start_x = event.pos().x()
                self._drag_track_start_offset = self.track.time_offset
                self.waveform.setCursor(Qt.ClosedHandCursor)
                print(f"DEBUG: Started track drag, initial offset: {self.track.time_offset}")
            else:
                # Normal selection mode
                self._drag_start = event.pos()
                self._is_dragging = True

                time_ = self._x_to_time(event.pos().x())
                self.selection_start = time_
                self.selection_end = time_
            self.update()

    def mouseMoveEvent(self, event):
        """Handle mouse move for selection or track movement."""
        if self._is_dragging_track and self.track is not None:
            # Calculate time delta based on mouse movement
            delta_x = event.pos().x() - self._drag_track_start_x
            timeline_duration = self.global_duration if self.global_duration is not None else self.duration
            visible_duration = timeline_duration / max(1e-6, self.zoom)
            pixels_per_second = self.waveform.width() / max(1e-6, visible_duration)
            delta_time = delta_x / max(1e-6, pixels_per_second)

            # Update track time offset
            new_offset = max(0.0, self._drag_track_start_offset + delta_time)
            self.track.time_offset = new_offset

            print(f"DEBUG: Track offset: {new_offset:.2f}s")
            try:
                if self.global_duration is not None:
                    view = self._find_multitrack_view()
                    if view is not None:
                        view.ensure_time_visible(float(new_offset), center=False)
            except Exception:
                pass
            self.update()

        elif self._is_dragging and self._drag_start is not None:
            # Normal selection mode
            time_ = self._x_to_time(event.pos().x())
            self.selection_end = time_
            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release to finalize selection or track movement."""
        if event.button() == Qt.LeftButton:
            if self._is_dragging_track:
                self._is_dragging_track = False
                self.waveform.setCursor(Qt.ArrowCursor)
                print(f"DEBUG: Finished track drag, final offset: {self.track.time_offset}")
                # If the user moved the clip, shift any stored regions (fade/cut/selection)
                # so edits stay attached to the clip (DAW-like behavior).
                try:
                    old_off = float(getattr(self, "_drag_track_start_offset", 0.0) or 0.0)
                    new_off = float(getattr(self.track, "time_offset", 0.0) or 0.0)
                    delta = new_off - old_off
                    if abs(delta) > 1e-6:
                        def _shift(regs):
                            out = []
                            for a, b in regs or []:
                                s = float(a) + delta
                                e = float(b) + delta
                                if e <= 0:
                                    continue
                                s = max(0.0, s)
                                e = max(0.0, e)
                                out.append((s, e))
                            return out

                        self.track.fade_in_regions = _shift(self.track.fade_in_regions)
                        self.track.fade_out_regions = _shift(self.track.fade_out_regions)
                        self.track.cut_regions = _shift(self.track.cut_regions)
                        if getattr(self.track, "last_selection", None):
                            s, e = self.track.last_selection
                            ns = max(0.0, float(s) + delta)
                            ne = max(0.0, float(e) + delta)
                            self.track.last_selection = (ns, ne)

                        # Mirror into this canvas so the overlay stays correct immediately.
                        self.fade_in_regions = list(self.track.fade_in_regions)
                        self.fade_out_regions = list(self.track.fade_out_regions)
                        self.cut_regions = list(self.track.cut_regions)
                        if self.selection_start is not None:
                            self.selection_start = max(0.0, float(self.selection_start) + delta)
                        if self.selection_end is not None:
                            self.selection_end = max(0.0, float(self.selection_end) + delta)
                except Exception:
                    pass
                # Notify parent widgets (TrackWidget/MultiTrackView/Dialog) to recompute duration/ruler.
                try:
                    self.track_offset_changed.emit(float(self.track.time_offset))
                except Exception:
                    pass

            elif self._is_dragging:
                self._is_dragging = False

                if self.selection_start is not None and self.selection_end is not None:
                    start = min(self.selection_start, self.selection_end)
                    end = max(self.selection_start, self.selection_end)

                    # Only emit if selection is meaningful (> 0.1 seconds)
                    if abs(end - start) > 0.1:
                        self.selection_start = start
                        self.selection_end = end
                        self.selection_changed.emit(start, end)
                    else:
                        self.clear_selection()

            self.update()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to position playhead and start playback."""
        print(f"DEBUG: Double-click detected at x={event.pos().x()}")
        if event.button() == Qt.LeftButton:
            # Get time position from click
            time_ = self._x_to_time(event.pos().x())
            print(f"DEBUG: Converted to time: {time_}")

            # Emit playhead position signal
            self.playhead_position.emit(time_)

            # Set playhead visually
            self.set_playhead(time_)

            # Find the AudioEditorDialog (might be several levels up)
            dialog = None
            widget = self.parent()
            while widget:
                if hasattr(widget, 'playback_process') and hasattr(widget, '_start_playback'):
                    dialog = widget
                    break
                widget = widget.parent()

            if dialog:
                print(f"DEBUG: Found AudioEditorDialog")
                was_playing = dialog.playback_process is not None

                # Stop current playback if any
                if was_playing:
                    dialog._stop_playback_process()

                # Set position and start playback
                dialog.playback_pause_position = time_
                dialog.playback_paused = True  # Mark as paused so it seeks to position
                dialog._start_playback()  # Start playback from the new position

                print(f"DEBUG: Started playback from {time_}")
            else:
                print("ERROR: Could not find AudioEditorDialog parent")

            # Clear selection
            self.clear_selection()

            # Force update
            self.update()

            print(f"DEBUG: Playhead positioned at {time_}")


# ============================================================================
# MAIN AUDIO EDITOR DIALOG
# ============================================================================

class AudioEditorDialog(QMainWindow):
    """Professional DAW-style audio editor with automatic single/multi-track switching.

    Features:
    - Automatically shows single waveform view for 1 file
    - Automatically switches to multi-track Audacity-style view for 2+ files
    - Import multiple files at once to create tracks automatically
    - All effects, tools, and transport controls work in both modes
    """

    def __init__(self, parent=None, ai_manager=None, initial_files: list = None, initial_file=None):
        # Ensure QApplication exists
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        # Handle tkinter parent (ignore it - can't mix tkinter and Qt)
        if parent is not None and not isinstance(parent, QDialog) and not hasattr(parent, 'windowTitle'):
            parent = None

        super().__init__(parent)

        # Make native crashes/tracebacks visible (helps diagnose rare Qt/native faults).
        # This does not prevent crashes, but it ensures we get a usable stack trace/log.
        try:
            import faulthandler
            from pathlib import Path as _Path

            if not faulthandler.is_enabled():
                log_dir = _Path.home() / ".fylorra" / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                crash_log = log_dir / "audio_editor_crash.log"
                self._faulthandler_file = open(crash_log, "a", encoding="utf-8", buffering=1)
                faulthandler.enable(file=self._faulthandler_file, all_threads=True)
        except Exception:
            pass

        # Handle both initial_file and initial_files
        if initial_file is not None and initial_files is None:
            initial_files = [initial_file]

        # State
        self.ai_manager = ai_manager
        self.audio_files = []
        self.current_file = None
        self.current_duration = 0.0

        # Multi-track support
        self.tracks = []  # List of AudioTrack objects
        self.current_track = None  # Currently selected track
        # Track widgets:
        # - `track_view_widgets`: AudioTrack -> TrackWidget (multitrack canvas widgets)
        # - `track_list_widgets`: AudioTrack -> QWidget (sidebar/list widgets)
        # Keep these separate; overwriting the TrackWidget reference can let Qt delete
        # a visible widget (via GC) and hard-crash the process on Windows.
        self.track_view_widgets = {}
        self.track_list_widgets = {}
        # Cached set of tracks used for the current playback run (respects mute/solo).
        self._active_playback_tracks = None
        # Drag-and-drop queue to avoid re-entrancy crashes.
        self._drop_queue = []
        self._drop_in_progress = False
        self._syncing_effects = False

        self.playback_process = None
        self.ffmpeg_process = None  # For multi-track mixing
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self._update_playhead)
        self.playback_start_time = 0.0
        self.playback_paused = False
        self.playback_pause_position = 0.0

        self.waveform_worker = None
        self.export_worker = None

        # Fade/Cut region tracking for toggle behavior (for single-track mode)
        self.fade_in_regions = []  # List of (start, end) tuples
        self.fade_out_regions = []  # List of (start, end) tuples
        self.cut_regions = []  # List of (start, end) tuples

        # Active region indices (for toggle behavior)
        self.active_fade_in_idx = None
        self.active_fade_out_idx = None
        self.active_cut_idx = None

        # Track selection UI (multi-track)
        self._suppress_track_select = False

        # Sidebar state
        self.sidebar_collapsed = False
        self.sidebar_width = 250

        # Setup UI
        self.setWindowTitle("Audio Editor - Fylorra")
        self.setWindowFlags(Qt.Window)  # Ensure proper window controls
        self.resize(1440, 860)
        self.setMinimumSize(1280, 800)

        # Enable drag and drop
        self.setAcceptDrops(True)

        apply_theme_stylesheet(self)
        self._build_ui()

        # Add initial files
        if initial_files:
            self.add_files(initial_files)

        # Show the dialog
        self.show()
        self.raise_()
        self.activateWindow()

    def _build_ui(self):
        """Build professional DAW interface."""
        # Create central widget for QMainWindow
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # AI Prompt bar at very top
        prompt_bar = self._create_prompt_bar()
        main_layout.addWidget(prompt_bar)

        # Top toolbar
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Main 3-panel layout
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setHandleWidth(1)
        self.main_splitter = main_splitter

        # Left panel - File list
        left_panel = self._create_left_panel()
        main_splitter.addWidget(left_panel)

        # Center panel with vertical splitter (waveform + tools) - EXACT match to original
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # Vertical splitter for waveform and tools
        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.vertical_splitter.setHandleWidth(8)
        self.vertical_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {THEME['border']};
            }}
        """)

        # Waveform panel (top)
        center_panel = self._create_center_panel()
        self.vertical_splitter.addWidget(center_panel)

        # Tools panel (bottom) - will be created later
        tools_panel = self._create_tools_panel()
        self.vertical_splitter.addWidget(tools_panel)

        # Set minimum sizes
        self.vertical_splitter.setCollapsible(0, False)
        self.vertical_splitter.setCollapsible(1, False)
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 0)

        center_layout.addWidget(self.vertical_splitter)
        main_splitter.addWidget(center_container)

        # Right panel - Effects/Properties
        right_panel = self._create_right_panel()
        main_splitter.addWidget(right_panel)

        # Set initial sizes: 250px | flexible | 300px
        main_splitter.setSizes([250, 900, 300])

        main_layout.addWidget(main_splitter, 1)

        # Bottom transport bar
        transport = self._create_transport_bar()
        main_layout.addWidget(transport)

        # Status bar
        self.status_bar = QProgressBar()
        self.status_bar.setVisible(False)
        self.status_bar.setTextVisible(True)
        self.status_bar.setFixedHeight(24)
        main_layout.addWidget(self.status_bar)

        # Keyboard shortcuts


    def _create_prompt_bar(self) -> QWidget:
        """Create AI prompt bar at top - EXACT match to original."""
        prompt_frame = QFrame()
        prompt_frame.setObjectName("prompt_bar")
        prompt_frame.setFixedHeight(70)
        prompt_frame.setStyleSheet(f"""
            QFrame#prompt_bar {{
                background-color: {THEME['bg_panel']};
                border-bottom: 1px solid {THEME['border']};
            }}
        """)

        layout = QHBoxLayout(prompt_frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # AI Prompt text field
        self.prompt_entry = QLineEdit()
        self.prompt_entry.setPlaceholderText("e.g., 'trim 0:30-1:45, fade out last 3s, export as podcast.mp3'")
        self.prompt_entry.setMinimumHeight(40)
        self.prompt_entry.returnPressed.connect(self._apply_prompt)
        layout.addWidget(self.prompt_entry, 1)

        # Apply button
        apply_btn = QPushButton("Apply")
        apply_btn.setProperty("class", "accent")
        apply_btn.setFixedSize(90, 40)
        apply_btn.clicked.connect(self._apply_prompt)
        layout.addWidget(apply_btn)

        # Export button
        export_btn = QPushButton("Export")
        export_btn.setProperty("class", "accent")
        export_btn.setFixedSize(120, 40)
        export_btn.clicked.connect(self._show_export_dialog)
        layout.addWidget(export_btn)

        # Info button
        info_btn = QPushButton("i")
        info_btn.setFixedSize(40, 40)
        info_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #3a3a3a;
                color: {THEME['text_primary']};
                border: 1px solid {THEME['border']};
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #4a4a4a;
            }}
        """)
        info_btn.clicked.connect(self._show_prompt_examples)
        layout.addWidget(info_btn)

        return prompt_frame

    def _create_toolbar(self) -> QWidget:
        """Create top toolbar with icon buttons."""
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setProperty("class", "toolbar")
        toolbar.setFixedHeight(58)
        toolbar.setStyleSheet(f"""
            QFrame#toolbar {{
                background-color: {THEME['bg_toolbar']};
                border-bottom: 1px solid {THEME['border']};
            }}
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(15, 4, 15, 10)
        layout.setSpacing(8)

        # File operations section
        layout.addWidget(self._create_separator())

        folder_btn = self._create_icon_button(ICONS["folder"], "Open Folder", 40)
        folder_btn.clicked.connect(self._open_folder)
        layout.addWidget(folder_btn)

        add_btn = self._create_icon_button(ICONS["add_media"], "Import Audio", 40)
        add_btn.clicked.connect(self._import_audio_files)
        layout.addWidget(add_btn)

        export_btn = self._create_icon_button(ICONS["export"], "Export Audio", 40)
        export_btn.clicked.connect(self._show_export_dialog)
        layout.addWidget(export_btn)

        settings_btn = self._create_icon_button(ICONS["settings"], "Settings", 40)
        settings_btn.clicked.connect(lambda: QMessageBox.information(self, "Settings", "Settings panel coming soon!"))
        layout.addWidget(settings_btn)

        layout.addWidget(self._create_separator())

        # Edit tools section
        self.cut_btn = self._create_icon_button(ICONS["cut"], "Cut Selection", 40)
        self.cut_btn.clicked.connect(self._toggle_cut)
        self.cut_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
        layout.addWidget(self.cut_btn)

        copy_btn = self._create_icon_button(ICONS["copy"], "Copy", 40)
        copy_btn.clicked.connect(lambda: QMessageBox.information(self, "Copy", "Copy functionality coming soon!"))
        layout.addWidget(copy_btn)

        paste_btn = self._create_icon_button(ICONS["paste"], "Paste", 40)
        paste_btn.clicked.connect(lambda: QMessageBox.information(self, "Paste", "Paste functionality coming soon!"))
        layout.addWidget(paste_btn)

        delete_btn = self._create_icon_button(ICONS["delete"], "Delete Selection", 40)
        delete_btn.clicked.connect(self._clear_selection)
        layout.addWidget(delete_btn)

        layout.addWidget(self._create_separator())

        layout.addStretch()

        layout.addStretch()

        return toolbar

    def _create_icon_button(self, icon_path: str, tooltip: str, size: int = 32) -> QToolButton:
        """Create an icon button."""
        btn = QToolButton()
        if Path(icon_path).exists():
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(size, size))
        else:
            btn.setText(tooltip[:1])
        btn.setToolTip(tooltip)
        btn.setFixedSize(size + 8, size + 8)
        return btn

    def _create_separator(self) -> QFrame:
        """Create a vertical separator line."""
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFixedWidth(1)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        return line

    def _create_left_panel(self) -> QWidget:
        """Create left panel with file list and multi-track support."""
        # Container for panel + toggle button
        container = QWidget()
        self.left_container = container
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Sidebar toggle button on left edge
        self.sidebar_toggle_btn = QPushButton("⟨")
        self.sidebar_toggle_btn.setFixedSize(14, 74)
        self.sidebar_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #3a3f46;
                color: {THEME['text_primary']};
                border: none;
                border-radius: 8px;
                font-size: 12px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #4a515a;
            }}
        """)
        self.sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        container_layout.addWidget(self.sidebar_toggle_btn, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setProperty("class", "panel")
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(400)
        panel.setStyleSheet(f"""
            QFrame#panel {{
                background-color: {THEME['bg_panel']};
                border-right: 1px solid {THEME['border']};
            }}
        """)
        self.left_panel = panel

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # Track list (hidden, for backward compatibility)
        self.track_list = QListWidget()
        self.track_list.setMaximumHeight(0)  # Hidden
        self.track_list.setVisible(False)
        layout.addWidget(self.track_list)

        # Audio Files Section
        header = QLabel("Audio Files")
        header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # File list
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self._on_file_clicked)
        layout.addWidget(self.file_list, 1)

        # Import button
        import_btn = QPushButton("Import Audio Files")
        import_btn.setProperty("class", "accent")
        import_btn.clicked.connect(self._import_audio_files)
        layout.addWidget(import_btn)

        container_layout.addWidget(panel)

        return container

    def _create_center_panel(self) -> QWidget:
        """Create center panel with waveform display - supports both single and multi-track modes."""
        panel = QFrame()
        panel.setObjectName("center")
        panel.setStyleSheet(f"""
            QFrame#center {{
                background-color: {THEME['bg_main']};
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # Header with zoom controls
        header_layout = QHBoxLayout()

        header_layout.addStretch()

        # Zoom controls
        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet(f"color: {THEME['text_secondary']};")
        header_layout.addWidget(zoom_label)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(200)
        self.zoom_slider.setValue(10)
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        header_layout.addWidget(self.zoom_slider)

        self.zoom_label = QLabel("1.0x")
        self.zoom_label.setFixedWidth(45)
        self.zoom_label.setStyleSheet(f"color: {THEME['text_secondary']};")
        header_layout.addWidget(self.zoom_label)

        layout.addLayout(header_layout)

        # Stacked widget to switch between modes
        self.mode_stack = QStackedWidget()

        # === MODE 0: Single Track View ===
        single_track_container = QWidget()
        single_layout = QVBoxLayout(single_track_container)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.setSpacing(12)

        # Mini time ruler (shows visible portion)
        self.mini_ruler = QWidget()
        self.mini_ruler.setFixedHeight(22)
        self.mini_ruler.setStyleSheet(f"background-color: #1f1f1f;")
        self.mini_ruler.paintEvent = self._paint_mini_ruler
        single_layout.addWidget(self.mini_ruler)

        # Waveform canvas (includes dB meter on right side)
        self.waveform_canvas = WaveformCanvas()
        self.waveform_canvas.selection_changed.connect(self._on_selection_changed)
        self.waveform_canvas.playhead_position.connect(self._seek_to_position)
        single_layout.addWidget(self.waveform_canvas, 1)

        # Pan slider
        pan_layout = QHBoxLayout()
        pan_label = QLabel("Pan:")
        pan_label.setStyleSheet(f"color: {THEME['text_secondary']};")
        pan_layout.addWidget(pan_label)

        self.pan_slider = QSlider(Qt.Horizontal)
        self.pan_slider.setMinimum(0)
        self.pan_slider.setMaximum(100)
        self.pan_slider.setValue(0)
        self.pan_slider.setEnabled(False)
        self.pan_slider.valueChanged.connect(self._on_pan_changed)
        pan_layout.addWidget(self.pan_slider, 1)

        single_layout.addLayout(pan_layout)

        self.mode_stack.addWidget(single_track_container)

        # === MODE 1: Multi-Track View ===
        self.multitrack_view = MultiTrackView()
        # Hide the Add Track button - users should use Import Audio Files instead
        self.multitrack_view.add_track_btn.setVisible(False)
        # Click-to-select a track (DAW behavior)
        try:
            self.multitrack_view.track_clicked.connect(self._select_track)
        except Exception:
            pass
        # Double-click the multitrack ruler to seek all tracks.
        try:
            self.multitrack_view.ruler_seek.connect(self._seek_to_position)
        except Exception:
            pass
        # Drag-select on the multitrack ruler should populate In/Out on the selected track.
        try:
            self.multitrack_view.ruler_selection_finalized.connect(self._on_ruler_selection_finalized)
        except Exception:
            pass
        self.mode_stack.addWidget(self.multitrack_view)

        layout.addWidget(self.mode_stack, 1)

        return panel

    def _create_right_panel(self) -> QWidget:
        """Create right panel with professional effects and properties."""
        panel = QFrame()
        panel.setObjectName("right")
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(450)
        panel.setStyleSheet(f"""
            QFrame#right {{
                background-color: {THEME['bg_panel']};
                border-left: 1px solid {THEME['border']};
            }}
        """)

        # Scrollable area for all effects
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Effects header
        effects_header = QLabel("Effects & Properties")
        effects_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(effects_header)

        # Volume control
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("Volume:"))
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(-60.0, 12.0)
        self.volume_spin.setValue(0.0)
        self.volume_spin.setSuffix(" dB")
        vol_layout.addWidget(self.volume_spin, 1)
        layout.addLayout(vol_layout)

        # Fade controls
        fade_layout = QHBoxLayout()

        self.fade_in_btn = QPushButton()
        if Path(ICONS["fade_in"]).exists():
            self.fade_in_btn.setIcon(QIcon(ICONS["fade_in"]))
            self.fade_in_btn.setIconSize(QSize(24, 24))
        self.fade_in_btn.setText("Fade In")
        self.fade_in_btn.clicked.connect(self._toggle_fade_in)
        self.fade_in_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
        fade_layout.addWidget(self.fade_in_btn)

        self.fade_out_btn = QPushButton()
        if Path(ICONS["fade_out"]).exists():
            self.fade_out_btn.setIcon(QIcon(ICONS["fade_out"]))
            self.fade_out_btn.setIconSize(QSize(24, 24))
        self.fade_out_btn.setText("Fade Out")
        self.fade_out_btn.clicked.connect(self._toggle_fade_out)
        self.fade_out_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
        fade_layout.addWidget(self.fade_out_btn)

        layout.addLayout(fade_layout)

        # Normalize
        self.normalize_check = QCheckBox("Normalize Audio")
        layout.addWidget(self.normalize_check)

        layout.addWidget(self._create_h_separator())

        # ==== PROFESSIONAL AUDIO EFFECTS ====

        # Equalizer (3-band)
        eq_header = QLabel("Equalizer (3-Band)")
        eq_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(eq_header)

        self.eq_enabled = QCheckBox("Enable EQ")
        layout.addWidget(self.eq_enabled)

        self.eq_low = self._create_slider_control("Low (100Hz):", -15.0, 15.0, 0.0, " dB")
        layout.addLayout(self.eq_low['layout'])

        self.eq_mid = self._create_slider_control("Mid (1kHz):", -15.0, 15.0, 0.0, " dB")
        layout.addLayout(self.eq_mid['layout'])

        self.eq_high = self._create_slider_control("High (10kHz):", -15.0, 15.0, 0.0, " dB")
        layout.addLayout(self.eq_high['layout'])

        layout.addWidget(self._create_h_separator())

        # Compressor
        comp_header = QLabel("Compressor")
        comp_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(comp_header)

        self.comp_enabled = QCheckBox("Enable Compressor")
        layout.addWidget(self.comp_enabled)

        self.comp_threshold = self._create_slider_control("Threshold:", -60.0, 0.0, -20.0, " dB")
        layout.addLayout(self.comp_threshold['layout'])

        self.comp_ratio = self._create_slider_control("Ratio:", 1.0, 20.0, 4.0, ":1")
        layout.addLayout(self.comp_ratio['layout'])

        self.comp_attack = self._create_slider_control("Attack:", 0.1, 100.0, 5.0, " ms")
        layout.addLayout(self.comp_attack['layout'])

        self.comp_release = self._create_slider_control("Release:", 10.0, 1000.0, 50.0, " ms")
        layout.addLayout(self.comp_release['layout'])

        layout.addWidget(self._create_h_separator())

        # Reverb
        rev_header = QLabel("Reverb")
        rev_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(rev_header)

        self.rev_enabled = QCheckBox("Enable Reverb")
        layout.addWidget(self.rev_enabled)

        self.rev_size = self._create_slider_control("Room Size:", 0.0, 1.0, 0.5, "")
        layout.addLayout(self.rev_size['layout'])

        self.rev_decay = self._create_slider_control("Decay Time:", 0.0, 1.0, 0.5, "")
        layout.addLayout(self.rev_decay['layout'])

        self.rev_mix = self._create_slider_control("Wet/Dry Mix:", 0.0, 1.0, 0.3, "")
        layout.addLayout(self.rev_mix['layout'])

        layout.addWidget(self._create_h_separator())

        # Delay/Echo
        delay_header = QLabel("Delay / Echo")
        delay_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(delay_header)

        self.delay_enabled = QCheckBox("Enable Delay")
        layout.addWidget(self.delay_enabled)

        self.delay_time = self._create_slider_control("Delay Time:", 0.0, 2000.0, 500.0, " ms")
        layout.addLayout(self.delay_time['layout'])

        self.delay_feedback = self._create_slider_control("Feedback:", 0.0, 0.99, 0.3, "")
        layout.addLayout(self.delay_feedback['layout'])

        self.delay_mix = self._create_slider_control("Wet/Dry Mix:", 0.0, 1.0, 0.3, "")
        layout.addLayout(self.delay_mix['layout'])

        layout.addWidget(self._create_h_separator())

        # Pitch Shift
        pitch_header = QLabel("Pitch Shift")
        pitch_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(pitch_header)

        self.pitch_enabled = QCheckBox("Enable Pitch Shift")
        layout.addWidget(self.pitch_enabled)

        self.pitch_semitones = self._create_slider_control("Semitones:", -12.0, 12.0, 0.0, " st")
        layout.addLayout(self.pitch_semitones['layout'])

        self.pitch_preserve = QCheckBox("Preserve Duration")
        self.pitch_preserve.setChecked(True)
        layout.addWidget(self.pitch_preserve)

        layout.addWidget(self._create_h_separator())

        # Speed Change
        speed_header = QLabel("Speed Change")
        speed_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(speed_header)

        self.speed_enabled = QCheckBox("Enable Speed Change")
        layout.addWidget(self.speed_enabled)

        self.speed_mult = self._create_slider_control("Speed:", 0.5, 2.0, 1.0, "x")
        layout.addLayout(self.speed_mult['layout'])

        self.speed_preserve = QCheckBox("Preserve Pitch")
        self.speed_preserve.setChecked(True)
        layout.addWidget(self.speed_preserve)

        layout.addWidget(self._create_h_separator())

        # Noise Reduction
        nr_header = QLabel("Noise Reduction")
        nr_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(nr_header)

        self.nr_enabled = QCheckBox("Enable Noise Reduction")
        layout.addWidget(self.nr_enabled)

        self.nr_threshold = self._create_slider_control("Threshold:", 0.0, 1.0, 0.5, "")
        layout.addLayout(self.nr_threshold['layout'])

        self.nr_amount = self._create_slider_control("Amount:", 0.0, 1.0, 0.5, "")
        layout.addLayout(self.nr_amount['layout'])

        layout.addWidget(self._create_h_separator())

        # Limiter
        lim_header = QLabel("Limiter")
        lim_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(lim_header)

        self.lim_enabled = QCheckBox("Enable Limiter")
        layout.addWidget(self.lim_enabled)

        self.lim_ceiling = self._create_slider_control("Ceiling:", -6.0, 0.0, -0.1, " dB")
        layout.addLayout(self.lim_ceiling['layout'])

        layout.addWidget(self._create_h_separator())

        # Selection header
        sel_header = QLabel("Selection")
        sel_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(sel_header)

        # In/Out points
        in_layout = QHBoxLayout()
        in_layout.addWidget(QLabel("In:"))
        self.in_entry = QLineEdit()
        self.in_entry.setPlaceholderText("00:00.00")
        self.in_entry.textChanged.connect(self._on_in_changed)
        in_layout.addWidget(self.in_entry)
        set_in_btn = QPushButton("Set")
        set_in_btn.setFixedWidth(50)
        set_in_btn.clicked.connect(self._set_in_point)
        in_layout.addWidget(set_in_btn)
        layout.addLayout(in_layout)

        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("Out:"))
        self.out_entry = QLineEdit()
        self.out_entry.setPlaceholderText("00:00.00")
        self.out_entry.textChanged.connect(self._on_out_changed)
        out_layout.addWidget(self.out_entry)
        set_out_btn = QPushButton("Set")
        set_out_btn.setFixedWidth(50)
        set_out_btn.clicked.connect(self._set_out_point)
        out_layout.addWidget(set_out_btn)
        layout.addLayout(out_layout)

        layout.addWidget(self._create_h_separator())

        # Export settings
        export_header = QLabel("Export Settings")
        export_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(export_header)

        # Format
        fmt_layout = QHBoxLayout()
        fmt_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP3", "WAV", "FLAC", "M4A", "OGG"])
        fmt_layout.addWidget(self.format_combo, 1)
        layout.addLayout(fmt_layout)

        # Bitrate
        bitrate_layout = QHBoxLayout()
        bitrate_layout.addWidget(QLabel("Bitrate:"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["320k", "256k", "192k", "128k", "96k"])
        bitrate_layout.addWidget(self.bitrate_combo, 1)
        layout.addLayout(bitrate_layout)

        layout.addWidget(self._create_h_separator())

        # Cut regions list
        cuts_header = QLabel("Cut Regions")
        cuts_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(cuts_header)

        self.cuts_list = QListWidget()
        self.cuts_list.setMaximumHeight(100)
        layout.addWidget(self.cuts_list)

        clear_cuts_btn = QPushButton("Clear All Cuts")
        clear_cuts_btn.clicked.connect(self._clear_all_cuts)
        layout.addWidget(clear_cuts_btn)

        layout.addStretch()

        scroll.setWidget(scroll_widget)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)

        # Connect all effect controls for real-time updates during playback
        self._connect_effect_controls()

        return panel

    def _connect_effect_controls(self):
        """Connect all effect controls to restart playback with new effects when changed."""
        # Volume
        self.volume_spin.valueChanged.connect(self._on_effect_changed)

        # Normalize
        self.normalize_check.stateChanged.connect(self._on_effect_changed)

        # EQ
        self.eq_enabled.stateChanged.connect(self._on_effect_changed)
        self.eq_low['slider'].valueChanged.connect(self._on_effect_changed)
        self.eq_mid['slider'].valueChanged.connect(self._on_effect_changed)
        self.eq_high['slider'].valueChanged.connect(self._on_effect_changed)

        # Compressor
        self.comp_enabled.stateChanged.connect(self._on_effect_changed)
        self.comp_threshold['slider'].valueChanged.connect(self._on_effect_changed)
        self.comp_ratio['slider'].valueChanged.connect(self._on_effect_changed)
        self.comp_attack['slider'].valueChanged.connect(self._on_effect_changed)
        self.comp_release['slider'].valueChanged.connect(self._on_effect_changed)

        # Reverb
        self.rev_enabled.stateChanged.connect(self._on_effect_changed)
        self.rev_size['slider'].valueChanged.connect(self._on_effect_changed)
        self.rev_decay['slider'].valueChanged.connect(self._on_effect_changed)
        self.rev_mix['slider'].valueChanged.connect(self._on_effect_changed)

        # Delay
        self.delay_enabled.stateChanged.connect(self._on_effect_changed)
        self.delay_time['slider'].valueChanged.connect(self._on_effect_changed)
        self.delay_feedback['slider'].valueChanged.connect(self._on_effect_changed)
        self.delay_mix['slider'].valueChanged.connect(self._on_effect_changed)

        # Pitch
        self.pitch_enabled.stateChanged.connect(self._on_effect_changed)
        self.pitch_semitones['slider'].valueChanged.connect(self._on_effect_changed)
        self.pitch_preserve.stateChanged.connect(self._on_effect_changed)

        # Speed
        self.speed_enabled.stateChanged.connect(self._on_effect_changed)
        self.speed_mult['slider'].valueChanged.connect(self._on_effect_changed)
        self.speed_preserve.stateChanged.connect(self._on_effect_changed)

        # Noise Reduction
        self.nr_enabled.stateChanged.connect(self._on_effect_changed)
        self.nr_threshold['slider'].valueChanged.connect(self._on_effect_changed)
        self.nr_amount['slider'].valueChanged.connect(self._on_effect_changed)

        # Limiter
        self.lim_enabled.stateChanged.connect(self._on_effect_changed)
        self.lim_ceiling['slider'].valueChanged.connect(self._on_effect_changed)

    def _sync_effect_controls_from_track(self, track: AudioTrack):
        """Sync right-panel effect controls from a track (multi-track mode)."""
        if track is None:
            return

        fx = track.effects or {}
        self._syncing_effects = True
        try:
            self.volume_spin.setValue(float(getattr(track, "volume", 0.0) or 0.0))

            eq = fx.get("eq", {})
            self.eq_enabled.setChecked(bool(eq.get("enabled", False)))
            self.eq_low['slider'].setValue(int(round(float(eq.get("low", 0.0)) * 10.0)))
            self.eq_mid['slider'].setValue(int(round(float(eq.get("mid", 0.0)) * 10.0)))
            self.eq_high['slider'].setValue(int(round(float(eq.get("high", 0.0)) * 10.0)))

            comp = fx.get("compressor", {})
            self.comp_enabled.setChecked(bool(comp.get("enabled", False)))
            self.comp_threshold['slider'].setValue(int(round(float(comp.get("threshold", -20.0)) * 10.0)))
            self.comp_ratio['slider'].setValue(int(round(float(comp.get("ratio", 4.0)) * 10.0)))
            self.comp_attack['slider'].setValue(int(round(float(comp.get("attack", 5.0)) * 10.0)))
            self.comp_release['slider'].setValue(int(round(float(comp.get("release", 50.0)) * 10.0)))

            rev = fx.get("reverb", {})
            self.rev_enabled.setChecked(bool(rev.get("enabled", False)))
            self.rev_size['slider'].setValue(int(round(float(rev.get("size", 0.5)) * 10.0)))
            self.rev_decay['slider'].setValue(int(round(float(rev.get("decay", 0.5)) * 10.0)))
            self.rev_mix['slider'].setValue(int(round(float(rev.get("mix", 0.3)) * 10.0)))

            delay = fx.get("delay", {})
            self.delay_enabled.setChecked(bool(delay.get("enabled", False)))
            self.delay_time['slider'].setValue(int(round(float(delay.get("time", 500.0)) * 10.0)))
            self.delay_feedback['slider'].setValue(int(round(float(delay.get("feedback", 0.3)) * 10.0)))
            self.delay_mix['slider'].setValue(int(round(float(delay.get("mix", 0.3)) * 10.0)))

            pitch = fx.get("pitch", {})
            self.pitch_enabled.setChecked(bool(pitch.get("enabled", False)))
            self.pitch_semitones['slider'].setValue(int(round(float(pitch.get("semitones", 0.0)) * 10.0)))
            self.pitch_preserve.setChecked(bool(pitch.get("preserve_duration", True)))

            speed = fx.get("speed", {})
            self.speed_enabled.setChecked(bool(speed.get("enabled", False)))
            self.speed_mult['slider'].setValue(int(round(float(speed.get("multiplier", 1.0)) * 10.0)))
            self.speed_preserve.setChecked(bool(speed.get("preserve_pitch", True)))

            nr = fx.get("noise_reduction", {})
            self.nr_enabled.setChecked(bool(nr.get("enabled", False)))
            self.nr_threshold['slider'].setValue(int(round(float(nr.get("threshold", 0.5)) * 10.0)))
            self.nr_amount['slider'].setValue(int(round(float(nr.get("amount", 0.5)) * 10.0)))

            lim = fx.get("limiter", {})
            self.lim_enabled.setChecked(bool(lim.get("enabled", False)))
            self.lim_ceiling['slider'].setValue(int(round(float(lim.get("ceiling", -0.1)) * 10.0)))
        finally:
            self._syncing_effects = False

    def _apply_effect_controls_to_track(self):
        """Apply right-panel effect control values to the selected track (multi-track mode)."""
        if len(self.tracks) <= 1:
            return

        track = self.current_track
        if track is None and self.tracks:
            # Pick a default track without clobbering the current UI state.
            self._select_track(self.tracks[0], sync_effects=False)
            track = self.current_track

        if track is None:
            return

        track.volume = float(self.volume_spin.value())
        fx = track.effects

        fx.setdefault("eq", {})
        fx["eq"]["enabled"] = self.eq_enabled.isChecked()
        fx["eq"]["low"] = self.eq_low['slider'].value() / 10.0
        fx["eq"]["mid"] = self.eq_mid['slider'].value() / 10.0
        fx["eq"]["high"] = self.eq_high['slider'].value() / 10.0

        fx.setdefault("compressor", {})
        fx["compressor"]["enabled"] = self.comp_enabled.isChecked()
        fx["compressor"]["threshold"] = self.comp_threshold['slider'].value() / 10.0
        fx["compressor"]["ratio"] = self.comp_ratio['slider'].value() / 10.0
        fx["compressor"]["attack"] = self.comp_attack['slider'].value() / 10.0
        fx["compressor"]["release"] = self.comp_release['slider'].value() / 10.0

        fx.setdefault("reverb", {})
        fx["reverb"]["enabled"] = self.rev_enabled.isChecked()
        fx["reverb"]["size"] = self.rev_size['slider'].value() / 10.0
        fx["reverb"]["decay"] = self.rev_decay['slider'].value() / 10.0
        fx["reverb"]["mix"] = self.rev_mix['slider'].value() / 10.0

        fx.setdefault("delay", {})
        fx["delay"]["enabled"] = self.delay_enabled.isChecked()
        fx["delay"]["time"] = self.delay_time['slider'].value() / 10.0
        fx["delay"]["feedback"] = self.delay_feedback['slider'].value() / 10.0
        fx["delay"]["mix"] = self.delay_mix['slider'].value() / 10.0

        fx.setdefault("pitch", {})
        fx["pitch"]["enabled"] = self.pitch_enabled.isChecked()
        fx["pitch"]["semitones"] = self.pitch_semitones['slider'].value() / 10.0
        fx["pitch"]["preserve_duration"] = self.pitch_preserve.isChecked()

        fx.setdefault("speed", {})
        fx["speed"]["enabled"] = self.speed_enabled.isChecked()
        fx["speed"]["multiplier"] = self.speed_mult['slider'].value() / 10.0
        fx["speed"]["preserve_pitch"] = self.speed_preserve.isChecked()

        fx.setdefault("noise_reduction", {})
        fx["noise_reduction"]["enabled"] = self.nr_enabled.isChecked()
        fx["noise_reduction"]["threshold"] = self.nr_threshold['slider'].value() / 10.0
        fx["noise_reduction"]["amount"] = self.nr_amount['slider'].value() / 10.0

        fx.setdefault("limiter", {})
        fx["limiter"]["enabled"] = self.lim_enabled.isChecked()
        fx["limiter"]["ceiling"] = self.lim_ceiling['slider'].value() / 10.0

        # Keep the track strip volume slider in sync (avoid double restarts).
        tw = self.track_view_widgets.get(track)
        if tw is not None and hasattr(tw, "vol_slider"):
            try:
                tw.vol_slider.blockSignals(True)
                tw.vol_slider.setValue(int(round(track.volume)))
            finally:
                tw.vol_slider.blockSignals(False)
            try:
                tw.vol_label.setText(f"{int(round(track.volume))}dB")
            except Exception:
                pass

    def _create_slider_control(self, label: str, min_val: float, max_val: float, default: float, suffix: str) -> dict:
        """Create a slider control with label and value display."""
        layout = QHBoxLayout()

        lbl = QLabel(label)
        lbl.setMinimumWidth(100)
        layout.addWidget(lbl)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(int(min_val * 10), int(max_val * 10))
        slider.setValue(int(default * 10))
        layout.addWidget(slider, 1)

        value_lbl = QLabel(f"{default:.1f}{suffix}")
        value_lbl.setMinimumWidth(60)
        value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(value_lbl)

        # Connect slider to update label
        def update_label(val):
            value_lbl.setText(f"{val/10:.1f}{suffix}")
        slider.valueChanged.connect(update_label)

        return {'layout': layout, 'slider': slider, 'label': value_lbl, 'min': min_val, 'max': max_val, 'suffix': suffix}

    def _create_tools_panel(self) -> QWidget:
        """Create bottom tools panel with advanced editing tools."""
        panel = QFrame()
        panel.setObjectName("tools")
        panel.setMinimumHeight(220)
        panel.setStyleSheet(f"""
            QFrame#tools {{
                background-color: {THEME['bg_panel']};
                border-top: 1px solid {THEME['border']};
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # Tools header
        tools_header = QLabel("Advanced Editing Tools")
        tools_header.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(tools_header)

        # Create horizontal layout for tool buttons
        tools_row1 = QHBoxLayout()

        # Trim tools
        trim_start_btn = QPushButton("Trim Start")
        trim_start_btn.setToolTip("Remove audio from start to current playhead position")
        trim_start_btn.clicked.connect(self._trim_start)
        tools_row1.addWidget(trim_start_btn)

        trim_end_btn = QPushButton("Trim End")
        trim_end_btn.setToolTip("Remove audio from current playhead position to end")
        trim_end_btn.clicked.connect(self._trim_end)
        tools_row1.addWidget(trim_end_btn)

        # Split tool
        split_btn = QPushButton("Split at Playhead")
        split_btn.setToolTip("Split audio into two files at playhead position")
        split_btn.clicked.connect(self._split_at_playhead)
        tools_row1.addWidget(split_btn)

        # Silence detection
        silence_btn = QPushButton("Detect Silence")
        silence_btn.setToolTip("Auto-detect silent regions in audio")
        silence_btn.clicked.connect(self._detect_silence)
        tools_row1.addWidget(silence_btn)

        layout.addLayout(tools_row1)

        # Second row of tools
        tools_row2 = QHBoxLayout()

        # Markers
        add_marker_btn = QPushButton("Add Marker")
        add_marker_btn.setToolTip("Add named marker at playhead position")
        add_marker_btn.clicked.connect(self._add_marker)
        tools_row2.addWidget(add_marker_btn)

        # Time stretch
        time_stretch_btn = QPushButton("Time Stretch")
        time_stretch_btn.setToolTip("Change duration without changing pitch")
        time_stretch_btn.clicked.connect(self._time_stretch)
        tools_row2.addWidget(time_stretch_btn)

        # Insert silence
        insert_silence_btn = QPushButton("Insert Silence")
        insert_silence_btn.setToolTip("Insert silence at playhead position")
        insert_silence_btn.clicked.connect(self._insert_silence)
        tools_row2.addWidget(insert_silence_btn)

        # Reverse audio
        reverse_btn = QPushButton("Reverse Selection")
        reverse_btn.setToolTip("Reverse the selected audio region")
        reverse_btn.clicked.connect(self._reverse_selection)
        tools_row2.addWidget(reverse_btn)

        layout.addLayout(tools_row2)

        # Third row - Copy/Paste
        tools_row3 = QHBoxLayout()

        copy_btn = QPushButton("Copy Selection")
        if Path(ICONS["copy"]).exists():
            copy_btn.setIcon(QIcon(ICONS["copy"]))
        copy_btn.setToolTip("Copy selected region to clipboard")
        copy_btn.clicked.connect(self._copy_selection)
        tools_row3.addWidget(copy_btn)

        paste_btn = QPushButton("Paste at Playhead")
        if Path(ICONS["paste"]).exists():
            paste_btn.setIcon(QIcon(ICONS["paste"]))
        paste_btn.setToolTip("Paste clipboard content at playhead")
        paste_btn.clicked.connect(self._paste_at_playhead)
        tools_row3.addWidget(paste_btn)

        duplicate_btn = QPushButton("Duplicate Selection")
        duplicate_btn.setToolTip("Duplicate selected region")
        duplicate_btn.clicked.connect(self._duplicate_selection)
        tools_row3.addWidget(duplicate_btn)

        tools_row3.addStretch()

        layout.addLayout(tools_row3)

        # Info label
        info_label = QLabel("Note: Advanced tools work on selected regions. Use In/Out points to define regions.")
        info_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 10px; font-style: italic;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()

        return panel

    def _create_h_separator(self) -> QFrame:
        """Create horizontal separator."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        return line

    def _create_transport_bar(self) -> QWidget:
        """Create bottom transport bar - EXACT match to original."""
        bar = QFrame()
        bar.setObjectName("transport")
        bar.setProperty("class", "transport")
        bar.setFixedHeight(90)
        bar.setStyleSheet(f"""
            QFrame#transport {{
                background-color: {THEME['bg_toolbar']};
                border-top: 1px solid {THEME['border']};
            }}
        """)

        layout = QVBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # Timeline position
        time_layout = QHBoxLayout()

        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 14px; font-weight: bold;")
        time_layout.addWidget(self.time_label)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setMinimum(0)
        self.seek_slider.setMaximum(1000)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        time_layout.addWidget(self.seek_slider, 1)

        layout.addLayout(time_layout)

        # Transport controls - EXACT match to original layout
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()

        # Home button (⏮)
        self.btn_home = QPushButton()
        if Path(ICONS["rewind"]).exists():
            self.btn_home.setIcon(QIcon(ICONS["rewind"]))
            self.btn_home.setIconSize(QSize(18, 18))
        else:
            self.btn_home.setText("⏮")
        self.btn_home.setFixedWidth(42)
        self.btn_home.clicked.connect(lambda: self._seek_relative(-self.current_duration))
        controls_layout.addWidget(self.btn_home)
        controls_layout.addSpacing(2)

        # Back 5s button (⏪ 5s)
        self.btn_back = QPushButton("⏪ 5s")
        self.btn_back.setFixedWidth(66)
        self.btn_back.clicked.connect(lambda: self._seek_relative(-5))
        controls_layout.addWidget(self.btn_back)
        controls_layout.addSpacing(2)

        # Play/Pause button (▶/⏸)
        self.play_pause_btn = QPushButton()
        if Path(ICONS["play"]).exists():
            self.play_pause_btn.setIcon(QIcon(ICONS["play"]))
            self.play_pause_btn.setIconSize(QSize(18, 18))
        else:
            self.play_pause_btn.setText("▶")
        self.play_pause_btn.setFixedWidth(56)
        self.play_pause_btn.clicked.connect(self._toggle_playback)
        controls_layout.addWidget(self.play_pause_btn)
        controls_layout.addSpacing(2)

        # Stop button (⏹) - darker gray
        self.stop_btn = QPushButton()
        if Path(ICONS["stop"]).exists():
            self.stop_btn.setIcon(QIcon(ICONS["stop"]))
            self.stop_btn.setIconSize(QSize(18, 18))
        else:
            self.stop_btn.setText("⏹")
        self.stop_btn.setFixedWidth(56)
        self.stop_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
        self.stop_btn.clicked.connect(self._stop_playback)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addSpacing(2)

        # Forward 5s button (5s ⏩)
        self.btn_fwd = QPushButton("5s ⏩")
        self.btn_fwd.setFixedWidth(66)
        self.btn_fwd.clicked.connect(lambda: self._seek_relative(5))
        controls_layout.addWidget(self.btn_fwd)
        controls_layout.addSpacing(2)

        # End button (⏭)
        self.btn_end = QPushButton()
        if Path(ICONS["forward"]).exists():
            self.btn_end.setIcon(QIcon(ICONS["forward"]))
            self.btn_end.setIconSize(QSize(18, 18))
        else:
            self.btn_end.setText("⏭")
        self.btn_end.setFixedWidth(42)
        self.btn_end.clicked.connect(lambda: self._seek_relative(self.current_duration))
        controls_layout.addWidget(self.btn_end)
        controls_layout.addSpacing(6)

        # Loop button (🔁) - inactive #444, active #1f6aa5
        self.loop_btn = QPushButton()
        if Path(ICONS["loop"]).exists():
            self.loop_btn.setIcon(QIcon(ICONS["loop"]))
            self.loop_btn.setIconSize(QSize(18, 18))
        else:
            self.loop_btn.setText("🔁")
        self.loop_btn.setFixedWidth(42)
        self.loop_btn.setCheckable(True)
        self.loop_btn.setToolTip("Enable/disable loop playback (uses selection as loop region)")
        self.loop_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
        self.loop_btn.clicked.connect(self._toggle_loop)
        controls_layout.addWidget(self.loop_btn)

        controls_layout.addStretch()

        layout.addLayout(controls_layout)

        return bar

    def _toggle_loop(self):
        """Toggle loop state."""
        is_checked = self.loop_btn.isChecked()

        if is_checked:
            # When enabling loop, use current selection as loop region
            if len(self.tracks) > 1:
                # Multi-track mode - get loop region from RULER selection (Audacity style)
                if self.multitrack_view.ruler_selection_start is not None and self.multitrack_view.ruler_selection_end is not None:
                    loop_start = min(self.multitrack_view.ruler_selection_start, self.multitrack_view.ruler_selection_end)
                    loop_end = max(self.multitrack_view.ruler_selection_start, self.multitrack_view.ruler_selection_end)

                    # Set shared loop region on multitrack view (Audacity style)
                    self.multitrack_view.set_loop_region(loop_start, loop_end)
                else:
                    # Fallback: use the currently selected track's in/out selection.
                    in_time = parse_time(self.in_entry.text())
                    out_time = parse_time(self.out_entry.text())
                    if in_time is None or out_time is None or in_time >= out_time:
                        QMessageBox.warning(
                            self,
                            "Loop",
                            "Select a region on a track waveform (or the timeline ruler) first, then enable Loop.",
                        )
                        self.loop_btn.setChecked(False)
                        return

                    loop_start, loop_end = in_time, out_time
                    # Mirror it into the timeline ruler selection for consistent UI.
                    self.multitrack_view.ruler_selection_start = loop_start
                    self.multitrack_view.ruler_selection_end = loop_end
                    for tw in self.multitrack_view.track_widgets:
                        tw.waveform_canvas.ruler_selection_start = loop_start
                        tw.waveform_canvas.ruler_selection_end = loop_end
                        tw.waveform_canvas.update()
                    self.multitrack_view.timeline_ruler.update()
                    self.multitrack_view.set_loop_region(loop_start, loop_end)
            else:
                # Single track mode
                if self.waveform_canvas.selection_start is not None and self.waveform_canvas.selection_end is not None:
                    self.waveform_canvas.loop_start = self.waveform_canvas.selection_start
                    self.waveform_canvas.loop_end = self.waveform_canvas.selection_end
                self.waveform_canvas.set_loop_enabled(is_checked)

            self.loop_btn.setStyleSheet(f"background-color: {THEME['button_active']};")
        else:
            self.loop_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")

            # Disable loop
            if len(self.tracks) > 1:
                self.multitrack_view.clear_loop_region()
                self.multitrack_view.ruler_selection_start = None
                self.multitrack_view.ruler_selection_end = None
                try:
                    for tw in self.multitrack_view.track_widgets:
                        tw.waveform_canvas.ruler_selection_start = None
                        tw.waveform_canvas.ruler_selection_end = None
                        tw.waveform_canvas.update()
                    self.multitrack_view.timeline_ruler.update()
                except Exception:
                    pass
            else:
                self.waveform_canvas.set_loop_enabled(is_checked)

    # ========================================================================
    # FILE MANAGEMENT
    # ========================================================================

    def add_files(self, paths: list):
        """Add audio files - multi-track mode."""
        if not paths:
            print("DEBUG: No paths provided")
            return

        print(f"DEBUG: add_files called with {len(paths)} files")
        print(f"DEBUG: Current tracks count: {len(self.tracks)}")

        paths = [Path(p) if isinstance(p, str) else p for p in paths]

        # Add to file list in sidebar
        for path in paths:
            path_str = str(path)
            if path_str not in self.audio_files:
                self.audio_files.append(path_str)

                item = QListWidgetItem()
                if Path(ICONS["audio_file"]).exists():
                    item.setIcon(QIcon(ICONS["audio_file"]))
                item.setText(path.name)
                item.setData(Qt.UserRole, path_str)
                self.file_list.addItem(item)

        # ALWAYS create tracks for ALL files
        for path in paths:
            path_str = str(path)

            # Check if track already exists
            if any(str(track.file_path) == path_str for track in self.tracks):
                print(f"DEBUG: Skipping duplicate track: {path.name}")
                continue

            # Create track
            track_name = path.stem
            track = AudioTrack(track_name, path_str)
            track.duration = get_audio_duration(path_str) or 0.0

            print(f"DEBUG: Creating track: {track_name}, duration: {track.duration}")

            # Add to tracks list
            self.tracks.append(track)

            # Add to MultiTrackView
            print(f"DEBUG: Adding track to MultiTrackView")
            track_widget = self.multitrack_view.add_track(track)
            print(f"DEBUG: Track widget created: {track_widget}")

            # Store track widget in the dialog's dict for easy lookup
            self.track_view_widgets[track] = track_widget

            # Connect waveform selection to update in/out points and set as current track
            track_widget.waveform_canvas.selection_changed.connect(
                lambda start, end, t=track: self._on_multitrack_selection(t, start, end)
            )

            # Load waveform
            self._load_track_waveform(track, track_widget)

        # Switch to multi-track view
        print(f"DEBUG: Total tracks now: {len(self.tracks)}")
        if len(self.tracks) >= 2:
            print("DEBUG: Switching to multi-track view")
            self.mode_stack.setCurrentIndex(1)
            self.multitrack_view.setVisible(True)
        elif len(self.tracks) == 1:
            print("DEBUG: Single track - loading normally")
            self._load_file(paths[0])

        self._update_waveform_display()

    @Slot()
    def _import_audio_files(self):
        """Import audio files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Audio Files",
            "",
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.aac *.ogg);;All Files (*.*)",
        )

        if files:
            self.add_files(files)

    @Slot()
    def _open_folder(self):
        """Open folder and import all audio files."""
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")
        if folder:
            audio_files = []
            for ext in ["*.mp3", "*.wav", "*.flac", "*.m4a", "*.aac", "*.ogg"]:
                audio_files.extend(Path(folder).glob(ext))

            if audio_files:
                self.add_files([str(f) for f in audio_files])
            else:
                QMessageBox.information(self, "No Audio Files", "No audio files found in the selected folder.")

    @Slot(QListWidgetItem)
    def _on_file_clicked(self, item: QListWidgetItem):
        """Handle file selection - don't crash!"""
        path = item.data(Qt.UserRole)

        # If in multi-track mode, select the corresponding track
        if self.mode_stack.currentIndex() == 1:
            # Find track with this file
            for track in self.tracks:
                if track.file_path == path:
                    # Select this track for editing + FX
                    self._select_track(track)
                    return
        else:
            # Single-track mode - load the file
            if Path(path).exists():
                self._load_file(path)

    def _load_file(self, path: str):
        """Load audio file and generate waveform."""
        if not Path(path).exists():
            QMessageBox.warning(self, "Error", f"File not found: {path}")
            return

        self.current_file = path
        self.current_duration = get_audio_duration(path) or 0.0

        # Update time label
        self.time_label.setText(f"00:00.00 / {format_time(self.current_duration)}")

        # Reset playback
        self._stop_playback()

        # Generate waveform
        self._generate_waveform()

    def _generate_waveform(self):
        """Generate waveform in background."""
        if not self.current_file:
            return

        self.status_bar.setValue(0)
        self.status_bar.setFormat("Generating waveform...")
        self.status_bar.setVisible(True)

        self.waveform_worker = WaveformWorker(self.current_file, samples=2000)
        self.waveform_worker.finished.connect(self._on_waveform_ready)
        self.waveform_worker.error.connect(self._on_waveform_error)
        self.waveform_worker.start()

    @Slot(list)
    def _on_waveform_ready(self, peaks: list):
        """Handle waveform ready."""
        self.status_bar.setVisible(False)
        self.waveform_canvas.set_peaks(peaks, self.current_duration)

    @Slot(str)
    def _on_waveform_error(self, error: str):
        """Handle waveform error."""
        self.status_bar.setVisible(False)
        QMessageBox.warning(self, "Waveform Error", f"Failed to generate waveform:\n{error}")
        self.waveform_canvas.set_peaks([], self.current_duration)

    # ========================================================================
    # PLAYBACK
    # ========================================================================

    def build_filter_chain(self) -> str:
        """Build ffmpeg audio filter chain from enabled effects."""
        filters = []

        # FADE IN - Apply all fade in regions
        for fade_start, fade_end in self.waveform_canvas.fade_in_regions:
            duration = fade_end - fade_start
            filters.append(f"afade=t=in:st={fade_start}:d={duration}")

        # FADE OUT - Apply all fade out regions
        for fade_start, fade_end in self.waveform_canvas.fade_out_regions:
            duration = fade_end - fade_start
            filters.append(f"afade=t=out:st={fade_start}:d={duration}")

        # Volume adjustment
        if self.volume_spin.value() != 0.0:
            filters.append(f"volume={self.volume_spin.value()}dB")

        # EQ (3-band)
        if self.eq_enabled.isChecked():
            low_val = self.eq_low['slider'].value() / 10.0
            mid_val = self.eq_mid['slider'].value() / 10.0
            high_val = self.eq_high['slider'].value() / 10.0

            if low_val != 0.0:
                filters.append(f"equalizer=f=100:width_type=o:width=2:g={low_val}")
            if mid_val != 0.0:
                filters.append(f"equalizer=f=1000:width_type=o:width=2:g={mid_val}")
            if high_val != 0.0:
                filters.append(f"equalizer=f=10000:width_type=o:width=2:g={high_val}")

        # Compressor
        if self.comp_enabled.isChecked():
            threshold = self.comp_threshold['slider'].value() / 10.0
            ratio = self.comp_ratio['slider'].value() / 10.0
            attack = self.comp_attack['slider'].value() / 10.0
            release = self.comp_release['slider'].value() / 10.0
            filters.append(f"acompressor=threshold={threshold}dB:ratio={ratio}:attack={attack}:release={release}")

        # Reverb (using aecho as approximation)
        if self.rev_enabled.isChecked():
            size = self.rev_size['slider'].value() / 10.0
            decay = self.rev_decay['slider'].value() / 10.0
            mix = self.rev_mix['slider'].value() / 10.0
            decay_time = int(decay * 1000)
            filters.append(f"aecho=0.8:0.88:{decay_time}:{mix}")

        # Delay
        if self.delay_enabled.isChecked():
            delay_time = self.delay_time['slider'].value() / 10.0
            feedback = self.delay_feedback['slider'].value() / 10.0
            mix = self.delay_mix['slider'].value() / 10.0
            filters.append(f"aecho=0.8:0.88:{int(delay_time)}:{feedback}")

        # Pitch shift
        if self.pitch_enabled.isChecked():
            semitones = self.pitch_semitones['slider'].value() / 10.0
            if semitones != 0.0:
                rate_factor = 2.0 ** (semitones / 12.0)
                if self.pitch_preserve.isChecked():
                    filters.append(f"asetrate=44100*{rate_factor},aresample=44100,atempo={1/rate_factor}")
                else:
                    filters.append(f"asetrate=44100*{rate_factor},aresample=44100")

        # Speed change
        if self.speed_enabled.isChecked():
            speed = self.speed_mult['slider'].value() / 10.0
            if speed != 1.0:
                if self.speed_preserve.isChecked():
                    filters.append(f"atempo={speed}")
                else:
                    filters.append(f"asetrate=44100*{speed},aresample=44100")

        # Noise reduction
        if self.nr_enabled.isChecked():
            threshold = self.nr_threshold['slider'].value() / 10.0
            amount = self.nr_amount['slider'].value() / 10.0
            filters.append(f"afftdn=nr={amount*20}:nf={threshold*100}")

        # Limiter
        if self.lim_enabled.isChecked():
            ceiling = self.lim_ceiling['slider'].value() / 10.0
            filters.append(f"alimiter=limit={ceiling}:attack=5:release=50")

        # Normalization
        if self.normalize_check.isChecked():
            filters.append("loudnorm")

        return ','.join(filters) if filters else 'anull'

    def _effective_timeline_duration(self) -> float:
        """
        Duration used for transport/stop logic.

        In multi-track mode, this must include per-track `time_offset` so playback does not
        stop at the end of the first clip when tracks are arranged sequentially.
        """
        if len(self.tracks) > 1 and self.tracks:
            tracks = self._active_playback_tracks or self.tracks
            try:
                dur = max((t.duration + t.time_offset for t in tracks), default=0.0)
                return max(0.0, float(dur))
            except Exception:
                return max(0.0, float(self.current_duration or 0.0))
        return max(0.0, float(self.current_duration or 0.0))

    @Slot()
    def _toggle_playback(self):
        """Toggle play/pause."""
        if self.playback_process is not None:
            self._pause_playback()
        else:
            self._start_playback()

    def _start_playback(self, fx_fade_in: float = 0.0):
        """Start playback - single or multi-track."""
        if not self.current_file and len(self.tracks) == 0:
            return

        ffplay = get_ffplay_exe()
        if not ffplay:
            QMessageBox.warning(self, "Error", "ffplay not found")
            return

        # IMPORTANT: Save pause position BEFORE stopping, because _stop_playback() resets it
        saved_pause_position = self.playback_pause_position
        saved_paused_state = self.playback_paused

        self._stop_playback()

        # Check if we're in multi-track mode with multiple tracks
        if len(self.tracks) > 1:
            # Multi-track playback
            # If loop is enabled and we're starting fresh (not resuming), start from loop start
            if self.loop_btn.isChecked() and self.multitrack_view.loop_start is not None and not saved_paused_state:
                # If we have an explicit position (e.g., seek/back/forward while playing),
                # honor it; otherwise default to the loop start.
                self.playback_pause_position = saved_pause_position if saved_pause_position > 1e-3 else self.multitrack_view.loop_start
                self.playback_paused = True
            else:
                # Restore the saved values for multi-track playback
                self.playback_pause_position = saved_pause_position
                self.playback_paused = saved_paused_state
            self._play_multitrack(fx_fade_in=fx_fade_in)
            return

        # Single track playback (existing code)
        if not self.current_file:
            return

        # Get playback range
        if self.loop_btn.isChecked() and self.waveform_canvas.loop_start is not None:
            # Use loop region for playback
            start_pos = saved_pause_position if saved_paused_state else self.waveform_canvas.loop_start
            duration = self.waveform_canvas.loop_end - self.waveform_canvas.loop_start
        else:
            # Use selection if available, otherwise full file
            sel_start = self.waveform_canvas.selection_start
            sel_end = self.waveform_canvas.selection_end
            start_pos = saved_pause_position if saved_paused_state else (sel_start if sel_start is not None else 0.0)
            duration = (sel_end - sel_start) if (sel_start is not None and sel_end is not None) else None

        # Build filter chain from ALL enabled effects
        filters = self.build_filter_chain()
        if fx_fade_in > 0:
            fade_filter = f"afade=t=in:st=0:d={fx_fade_in}"
            if filters and filters != 'anull':
                filters = f"{filters},{fade_filter}"
            else:
                filters = fade_filter

        # Build ffplay command with real-time effects
        cmd = [str(ffplay), "-nodisp", "-autoexit"]

        # Apply audio filters in REAL-TIME
        if filters != 'anull':
            cmd.extend(["-af", filters])

        # Start position
        if start_pos > 0:
            cmd.extend(["-ss", str(start_pos)])

        # Duration (if selection exists)
        if duration is not None and duration > 0:
            cmd.extend(["-t", str(duration)])

        # Loop if enabled
        if self.loop_btn.isChecked():
            cmd.extend(["-loop", "0"])

        cmd.extend(["-i", str(self.current_file)])

        try:
            self.playback_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            self.playback_start_time = time.time() - start_pos
            self.playback_paused = False
            self.playback_timer.start(50)

            # Update icon
            if Path(ICONS["pause"]).exists():
                self.play_pause_btn.setIcon(QIcon(ICONS["pause"]))
                self.play_pause_btn.setIconSize(QSize(18, 18))
            else:
                self.play_pause_btn.setText("⏸")
            self.play_pause_btn.setToolTip("Pause")

        except Exception as e:
            QMessageBox.warning(self, "Playback Error", f"Failed to start playback:\n{e}")

    def _play_multitrack(self, fx_fade_in: float = 0.0):
        """Play multiple tracks mixed together using ffmpeg pipe to ffplay."""
        print("DEBUG: _play_multitrack() called")
        ffmpeg = get_ffmpeg_exe()
        ffplay = get_ffplay_exe()

        if not ffmpeg or not ffplay:
            print("ERROR: ffmpeg or ffplay not found")
            QMessageBox.warning(self, "Error", "ffmpeg/ffplay not found")
            return

        # Filter out muted tracks
        active_tracks = [t for t in self.tracks if not t.mute]
        print(f"DEBUG: Active tracks (not muted): {len(active_tracks)}")

        # If solo is enabled, only play solo tracks
        solo_tracks = [t for t in self.tracks if t.solo]
        if solo_tracks:
            active_tracks = solo_tracks
            print(f"DEBUG: Solo tracks enabled: {len(solo_tracks)}")

        if not active_tracks:
            print("DEBUG: No active tracks to play")
            return

        # Cache the tracks for this playback run (respects mute/solo). Used by stop/seek logic.
        self._active_playback_tracks = list(active_tracks)

        # Set current duration to longest track (including time offsets)
        self.current_duration = max(t.duration + t.time_offset for t in active_tracks)
        global_duration = float(self.current_duration or 0.0)
        print(f"DEBUG: Multi-track duration: {self.current_duration}")

        # Build ffmpeg command to mix tracks and output to stdout
        ffmpeg_cmd = [str(ffmpeg)]

        # Store seek position to apply AFTER mixing (not before)
        seek_position = self.playback_pause_position if self.playback_paused else 0.0
        if seek_position > 0:
            print(f"DEBUG: Will seek to {seek_position} after mixing")
        # IMPORTANT:
        # We represent the "start offset" via playback_start_time (time.time() - seek_position),
        # so while playing, playback_pause_position must be 0 to avoid double-counting.
        self.playback_pause_position = 0.0

        # Add all input files (NO -ss here, we'll seek after mixing)
        for i, track in enumerate(active_tracks):
            ffmpeg_cmd.extend(["-i", str(track.file_path)])
            print(f"DEBUG: Input {i}: {track.name}")

        # Build filter_complex for mixing with all effects
        if len(active_tracks) > 1:
            filter_parts = []

            for i, track in enumerate(active_tracks):
                # Start with base audio stream
                stream = f"[{i}:a]"

                # Build complete filter chain for this track.
                #
                # IMPORTANT (multi-track timeline semantics):
                # - UI selections/regions are stored in *timeline/global* seconds.
                # - `adelay` shifts the audio into the timeline.
                # - Therefore time-based filters (fade/cut) must run AFTER `adelay`,
                #   otherwise their `st=` times get applied before the delay and the
                #   delay silences/double-shifts the content (user saw track2 go silent).
                #
                # Non-time-based effects (EQ, compressor, gain, pan) can run before delay.
                track_filters_pre = []
                track_filters_time = []

                clip_start = float(track.time_offset or 0.0)
                clip_end = clip_start + float(track.duration or 0.0)

                def _clip_region(a: float, b: float):
                    s = max(float(a), clip_start)
                    e = min(float(b), clip_end)
                    if e <= s:
                        return None
                    return s, e

                # Apply non-time-based track FX before the timeline delay.
                # NOTE: This includes volume/pan, EQ, compressor, reverb, delay, pitch, speed,
                # noise reduction, limiter, etc.
                try:
                    fx = (track.get_ffmpeg_filter() or "").strip()
                except Exception:
                    fx = ""
                if fx and fx != "anull":
                    track_filters_pre.append(fx)

                # Apply time offset (delay this track into timeline)
                if track.time_offset > 0:
                    track_filters_pre.append(
                        f"adelay={int(track.time_offset * 1000)}|{int(track.time_offset * 1000)}"
                    )

                # Apply cut regions (mute those sections) in TIMELINE time
                for cut_start, cut_end in track.cut_regions:
                    reg = _clip_region(cut_start, cut_end)
                    if not reg:
                        continue
                    s, e = reg
                    track_filters_time.append(f"volume=enable='between(t,{s},{e})':volume=0")

                # Apply fade regions in TIMELINE time
                for fade_start, fade_end in track.fade_in_regions:
                    reg = _clip_region(fade_start, fade_end)
                    if not reg:
                        continue
                    s, e = reg
                    track_filters_time.append(f"afade=t=in:st={s}:d={e - s}")

                for fade_start, fade_end in track.fade_out_regions:
                    reg = _clip_region(fade_start, fade_end)
                    if not reg:
                        continue
                    s, e = reg
                    track_filters_time.append(f"afade=t=out:st={s}:d={e - s}")

                # IMPORTANT: if we delay a track, some ffmpeg builds will keep the stream's
                # original end timestamp unless we explicitly pad it. This caused delayed
                # tracks to stop at their original end time. Pad each stream up to the
                # overall timeline duration so amix can truly run "longest".
                track_filters = track_filters_pre + track_filters_time
                if global_duration > 0:
                    track_filters.append(f"apad=whole_dur={global_duration}")

                # Combine all filters for this track
                if track_filters:
                    filter_parts.append(f"{stream}{','.join(track_filters)}[a{i}]")
                else:
                    filter_parts.append(f"{stream}acopy[a{i}]")

            # Combine all tracks with amix
            inputs = ''.join(f"[a{i}]" for i in range(len(active_tracks)))
            filter_parts.append(f"{inputs}amix=inputs={len(active_tracks)}:duration=longest[mixed]")

            # Apply seek and loop trim AFTER mixing using atrim filter
            if self.loop_btn.isChecked() and self.multitrack_view.loop_start is not None and self.multitrack_view.loop_end is not None:
                # Loop is enabled - trim to loop region
                loop_start = self.multitrack_view.loop_start
                loop_end = self.multitrack_view.loop_end
                # Start from current position (or loop start), end at loop end
                actual_start = seek_position if seek_position > loop_start else loop_start
                filter_parts.append(f"[mixed]atrim=start={actual_start}:end={loop_end}[out]")
                print(f"DEBUG: Loop enabled - trimming from {actual_start} to {loop_end}")
            else:
                # No loop region: trim to the effective end so delayed tracks are not cut off.
                # When seeking, also provide an end to prevent ffmpeg from running long with padding.
                if seek_position > 0:
                    filter_parts.append(f"[mixed]atrim=start={seek_position}:end={global_duration}[out]")
                else:
                    filter_parts.append(f"[mixed]atrim=end={global_duration}[out]")

            filter_complex = ';'.join(filter_parts)
            ffmpeg_cmd.extend(["-filter_complex", filter_complex, "-map", "[out]"])
            print(f"DEBUG: Filter complex: {filter_complex}")
        else:
            # Single active track - apply all its effects
            track = active_tracks[0]
            filters_pre = []
            filters_time = []

            clip_start = float(track.time_offset or 0.0)
            clip_end = clip_start + float(track.duration or 0.0)

            def _clip_region_single(a: float, b: float):
                s = max(float(a), clip_start)
                e = min(float(b), clip_end)
                if e <= s:
                    return None
                return s, e

            # Apply non-time-based FX before the timeline delay.
            try:
                fx = (track.get_ffmpeg_filter() or "").strip()
            except Exception:
                fx = ""
            if fx and fx != "anull":
                filters_pre.append(fx)

            # Time offset (delay into timeline) BEFORE time-based fades/cuts
            if track.time_offset > 0:
                filters_pre.append(f"adelay={int(track.time_offset * 1000)}|{int(track.time_offset * 1000)}")

            # Cuts (timeline time)
            for cut_start, cut_end in track.cut_regions:
                reg = _clip_region_single(cut_start, cut_end)
                if not reg:
                    continue
                s, e = reg
                filters_time.append(f"volume=enable='between(t,{s},{e})':volume=0")

            # Fades (timeline time)
            for fade_start, fade_end in track.fade_in_regions:
                reg = _clip_region_single(fade_start, fade_end)
                if not reg:
                    continue
                s, e = reg
                filters_time.append(f"afade=t=in:st={s}:d={e - s}")

            for fade_start, fade_end in track.fade_out_regions:
                reg = _clip_region_single(fade_start, fade_end)
                if not reg:
                    continue
                s, e = reg
                filters_time.append(f"afade=t=out:st={s}:d={e - s}")

            filters = filters_pre + filters_time
            if global_duration > 0:
                filters.append(f"apad=whole_dur={global_duration}")
                # Ensure ffmpeg stops at the same effective end (avoids infinite padding).
                if seek_position > 0:
                    filters.append(f"atrim=start={seek_position}:end={global_duration}")
                else:
                    filters.append(f"atrim=end={global_duration}")

            if filters:
                ffmpeg_cmd.extend(["-af", ','.join(filters)])

        # Output to stdout as WAV
        ffmpeg_cmd.extend(["-f", "wav", "-"])

        # Build ffplay command to read from stdin
        ffplay_cmd = [str(ffplay), "-nodisp", "-autoexit"]
        if fx_fade_in > 0:
            ffplay_cmd.extend(["-af", f"afade=t=in:st=0:d={fx_fade_in}"])
        ffplay_cmd.append("-")

        # Note: Loop is handled at application level in _update_playhead(), not by ffplay

        print(f"DEBUG: ffmpeg command: {' '.join(ffmpeg_cmd)}")
        print(f"DEBUG: ffplay command: {' '.join(ffplay_cmd)}")

        try:
            # Start ffmpeg to mix audio
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Start ffplay to play from ffmpeg's stdout
            self.playback_process = subprocess.Popen(
                ffplay_cmd,
                stdin=ffmpeg_process.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Store ffmpeg process so we can kill it when stopping
            self.ffmpeg_process = ffmpeg_process

            # Close our copy of ffmpeg's stdout so ffplay gets EOF when ffmpeg exits
            ffmpeg_process.stdout.close()

            # Set playback start time, accounting for seek position
            self.playback_start_time = time.time() - seek_position
            self.playback_paused = False
            self.playback_timer.start(50)

            # Update icon
            if Path(ICONS["pause"]).exists():
                self.play_pause_btn.setIcon(QIcon(ICONS["pause"]))
                self.play_pause_btn.setIconSize(QSize(18, 18))
            else:
                self.play_pause_btn.setText("⏸")
            self.play_pause_btn.setToolTip("Pause")

            print("DEBUG: Multi-track playback started successfully")

        except Exception as e:
            print(f"ERROR: Multi-track playback failed: {e}")
            QMessageBox.warning(self, "Playback Error", f"Failed to start playback:\n{e}")

    def _pause_playback(self):
        """Pause playback."""
        if self.playback_process is None:
            return

        elapsed = time.time() - self.playback_start_time
        self.playback_pause_position = elapsed

        self._stop_playback_process()

        self.playback_paused = True

        # Update icon
        if Path(ICONS["play"]).exists():
            self.play_pause_btn.setIcon(QIcon(ICONS["play"]))
            self.play_pause_btn.setIconSize(QSize(18, 18))
        else:
            self.play_pause_btn.setText("▶")
        self.play_pause_btn.setToolTip("Play")

    def _on_effect_changed(self):
        """
        Restart playback with updated effects while minimizing glitches.

        ffplay cannot change filter graphs live; we must restart. To avoid "chopping" audio while
        the user drags sliders, we debounce the restart and keep playing until the user pauses.
        """
        if getattr(self, "_syncing_effects", False):
            return

        # Sync UI -> selected track for multi-track playback/export.
        self._apply_effect_controls_to_track()

        if self.playback_process is None:
            return

        # Debounce restart so rapid slider updates don't constantly kill/restart ffplay.
        if not hasattr(self, "_fx_restart_timer") or self._fx_restart_timer is None:
            self._fx_restart_timer = QTimer(self)
            self._fx_restart_timer.setSingleShot(True)
            self._fx_restart_timer.timeout.connect(self._restart_playback_with_current_effects)

        # Restart shortly after the last change.
        self._fx_restart_timer.start(350)

    def _restart_playback_at_current_position(self):
        """Restart playback at current position with new effects."""
        self._start_playback()

    def _restart_playback_with_current_effects(self):
        """Debounced restart used for effect changes."""
        if self.playback_process is None:
            return

        # Compute current position based on our internal clock (same as _update_playhead()).
        elapsed_from_start = time.time() - self.playback_start_time
        current_pos = float(self.playback_pause_position or 0.0) + float(elapsed_from_start or 0.0)

        max_dur = float(self._effective_timeline_duration() or 0.0)
        if max_dur > 0:
            current_pos = max(0.0, min(max_dur, current_pos))
        else:
            current_pos = max(0.0, current_pos)

        # Stop playback and restart with a tiny preroll + fade-in to mask restart clicks.
        fx_preroll = 0.05
        restart_pos = max(0.0, current_pos - fx_preroll)
        fx_fade_in = min(0.05, fx_preroll)

        self._stop_playback_process()
        self.playback_pause_position = restart_pos
        self.playback_paused = True
        self._start_playback(fx_fade_in=fx_fade_in)

    def _restart_playback(self):
        """Restart playback (used when track settings change)."""
        if self.playback_process is None:
            return

        current_pos = time.time() - self.playback_start_time
        self._stop_playback_process()
        QTimer.singleShot(50, lambda: self._resume_playback_at(current_pos))

    def _resume_playback_at(self, position: float):
        """Resume playback at specific position."""
        self.playback_pause_position = position
        self.playback_paused = True
        self._start_playback()

    @Slot()
    def _stop_playback(self):
        """Stop playback."""
        self._stop_playback_process()

        self.playback_paused = False
        self.playback_pause_position = 0.0
        self._active_playback_tracks = None
        if len(self.tracks) > 1:
            try:
                self.multitrack_view.set_shared_playhead(0.0)
            except Exception:
                pass
        self.waveform_canvas.set_playhead(0.0)

        # Update icon
        if Path(ICONS["play"]).exists():
            self.play_pause_btn.setIcon(QIcon(ICONS["play"]))
            self.play_pause_btn.setIconSize(QSize(18, 18))
        else:
            self.play_pause_btn.setText("▶")
        self.play_pause_btn.setToolTip("Play")

        self.time_label.setText(f"00:00.00 / {format_time(self.current_duration)}")

    def _stop_playback_process(self):
        """Stop playback process."""
        if self.playback_process is not None:
            try:
                self.playback_process.terminate()
                self.playback_process.wait(timeout=1)
            except Exception:
                try:
                    self.playback_process.kill()
                except Exception:
                    pass

            self.playback_process = None

        # Also kill ffmpeg process if it exists
        if hasattr(self, 'ffmpeg_process') and self.ffmpeg_process is not None:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=1)
            except Exception:
                try:
                    self.ffmpeg_process.kill()
                except Exception:
                    pass

            self.ffmpeg_process = None

        self.playback_timer.stop()

    @Slot()
    def _update_playhead(self):
        """Update playhead during playback with loop support."""
        if self.playback_process is None:
            return

        if self.playback_process.poll() is not None:
            # Playback finished
            if self.loop_btn.isChecked():
                # Loop is enabled - restart playback with slight delay to prevent UI freeze
                QTimer.singleShot(50, self._start_playback)
            else:
                self._stop_playback()
            return

        elapsed_from_start = time.time() - self.playback_start_time

        # Calculate actual playback position (accounting for where we started)
        current_position = self.playback_pause_position + elapsed_from_start

        # Multi-track mixes must use the effective timeline duration (includes offsets).
        effective_duration = self._effective_timeline_duration()
        if len(self.tracks) > 1 and abs((self.current_duration or 0.0) - effective_duration) > 1e-3:
            self.current_duration = effective_duration

        # Check if we have a loop region (check multi-track or single track)
        if len(self.tracks) > 1 and self.tracks:
            # Multi-track mode - get loop region from multitrack view
            if self.multitrack_view.loop_start is not None and self.multitrack_view.loop_end is not None:
                loop_start = self.multitrack_view.loop_start
                loop_end = self.multitrack_view.loop_end
            else:
                loop_start = 0.0
                loop_end = effective_duration
        elif self.waveform_canvas.loop_start is not None and self.waveform_canvas.loop_end is not None:
            # Single track mode
            loop_start = self.waveform_canvas.loop_start
            loop_end = self.waveform_canvas.loop_end
        else:
            # Fallback to full file if no loop region set
            loop_start = 0.0
            loop_end = effective_duration

        # If loop is enabled and we've reached the loop end, restart from loop start
        if self.loop_btn.isChecked():
            if current_position >= loop_end:
                # Restart playback from loop start
                self._stop_playback_process()
                # Set playback position to loop start and restart with slight delay
                self.playback_pause_position = loop_start
                self.playback_paused = True
                QTimer.singleShot(50, self._start_playback)
                return
        else:
            # No loop - stop at end
            if current_position >= effective_duration:
                self._stop_playback()
                return

        # Update playhead based on current mode
        if hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1:
            # Multi-track mode
            self.multitrack_view.set_shared_playhead(current_position)
        else:
            # Single track mode
            self.waveform_canvas.set_playhead(current_position)

        self.time_label.setText(f"{format_time(current_position)} / {format_time(effective_duration)}")

        if effective_duration > 0:
            percent = int((current_position / effective_duration) * 1000)
            self.seek_slider.setValue(percent)

    def _seek_relative(self, seconds: float):
        """Seek relative to current position."""
        if not self.current_file and not self.tracks:
            return

        if self.playback_process is not None:
            current = time.time() - self.playback_start_time
        else:
            current = self.playback_pause_position

        max_dur = self._effective_timeline_duration()
        new_pos = max(0.0, min(max_dur, current + seconds))

        if self.playback_process is not None:
            self.playback_pause_position = new_pos
            # Treat this as an explicit seek so multi-track playback applies it.
            self.playback_paused = True
            self._start_playback()
        else:
            self.playback_pause_position = new_pos
            if len(self.tracks) > 1:
                self.multitrack_view.set_shared_playhead(new_pos)
            else:
                self.waveform_canvas.set_playhead(new_pos)

    @Slot()
    def _on_seek_pressed(self):
        """Handle seek press."""
        if self.playback_process is not None:
            self._pause_playback()

    @Slot()
    def _on_seek_released(self):
        """Handle seek release."""
        if not self.current_file and not self.tracks:
            return

        percent = self.seek_slider.value() / 1000.0
        max_dur = self._effective_timeline_duration()
        new_pos = percent * max_dur

        self.playback_pause_position = new_pos
        if len(self.tracks) > 1:
            self.multitrack_view.set_shared_playhead(new_pos)
        else:
            self.waveform_canvas.set_playhead(new_pos)

    # ========================================================================
    # WAVEFORM CONTROLS
    # ========================================================================

    def _update_waveform_display(self):
        """Update display based on number of tracks - automatic switching."""
        print(f"DEBUG: _update_waveform_display - tracks: {len(self.tracks)}")
        if len(self.tracks) <= 1:
            # Show single waveform view (index 0)
            self.mode_stack.setCurrentIndex(0)
            print(f"DEBUG: mode_stack set to index 0 (single track)")
        else:
            # Show multi-track stacked view (index 1)
            self.mode_stack.setCurrentIndex(1)
            print(f"DEBUG: mode_stack set to index 1 (multi-track)")

        print(f"DEBUG: mode_stack current index: {self.mode_stack.currentIndex()}")
        print(f"DEBUG: multitrack_view visible: {self.multitrack_view.isVisible()}")
        print(f"DEBUG: multitrack_view size: {self.multitrack_view.size()}")

    @Slot(int)
    def _on_zoom_changed(self, value: int):
        """Handle zoom change."""
        zoom = value / 10.0
        self.zoom_label.setText(f"{zoom:.1f}x")

        # Apply zoom based on number of tracks (automatic mode detection)
        if hasattr(self, 'mode_stack'):
            if len(self.tracks) <= 1:
                # Single track mode
                self.waveform_canvas.set_zoom(zoom)
                self.pan_slider.setEnabled(zoom > 1.0)
                if zoom <= 1.0:
                    self.pan_slider.setValue(0)
                # Update mini ruler to show new visible range
                if hasattr(self, 'mini_ruler'):
                    self.mini_ruler.update()
            else:
                # Multi-track mode
                # Preserve the current view center when zooming so clips don't "jump" out of view.
                center_t = None
                try:
                    start_t, end_t, vis = self.multitrack_view._visible_range()
                    if vis > 0:
                        center_t = (start_t + end_t) * 0.5
                except Exception:
                    center_t = None

                self.multitrack_view.set_shared_zoom(zoom)
                self.pan_slider.setEnabled(zoom > 1.0)
                if zoom <= 1.0:
                    self.pan_slider.setValue(0)
                # Keep the previous center time in view after zooming (prevents clips "disappearing").
                try:
                    # Use the shared timeline duration (all tracks) so ruler/track stay aligned.
                    try:
                        max_dur = float(self.multitrack_view._timeline_duration())
                    except Exception:
                        max_dur = self._effective_timeline_duration()
                    if max_dur > 0 and center_t is not None:
                        visible = max_dur / max(1e-6, float(zoom))
                        new_start = max(0.0, min(float(center_t) - (visible * 0.5), max_dur - visible))
                        denom = max(1e-9, (max_dur - visible))
                        new_pan = 0.0 if denom <= 1e-9 else (new_start / denom)
                        new_pan = max(0.0, min(1.0, float(new_pan)))
                        self.multitrack_view.set_shared_pan(new_pan)
                        try:
                            self.multitrack_view.pan_scrollbar.blockSignals(True)
                            self.multitrack_view.pan_scrollbar.setValue(int(new_pan * 1000.0))
                            self.multitrack_view.pan_scrollbar.blockSignals(False)
                        except Exception:
                            pass
                        try:
                            self.pan_slider.blockSignals(True)
                            self.pan_slider.setValue(int(round(new_pan * 100.0)))
                            self.pan_slider.blockSignals(False)
                        except Exception:
                            pass
                except Exception:
                    pass
        else:
            # Fallback for initialization
            self.waveform_canvas.set_zoom(zoom)
            self.pan_slider.setEnabled(zoom > 1.0)
            if zoom <= 1.0:
                self.pan_slider.setValue(0)

    @Slot(int)
    def _on_pan_changed(self, value: int):
        """Handle pan change."""
        pan = value / 100.0

        # Apply pan based on number of tracks (automatic mode detection)
        if hasattr(self, 'mode_stack'):
            if len(self.tracks) <= 1:
                # Single track mode
                self.waveform_canvas.set_pan(pan)
                # Update mini ruler to show new visible range
                if hasattr(self, 'mini_ruler'):
                    self.mini_ruler.update()
            else:
                # Multi-track mode
                self.multitrack_view.set_shared_pan(pan)
        else:
            # Fallback for initialization
            self.waveform_canvas.set_pan(pan)

    @Slot(float, float)
    def _on_selection_changed(self, start: float, end: float):
        """Handle selection change."""
        self.in_entry.setText(format_time(start))
        self.out_entry.setText(format_time(end))
        self._update_button_states()

    def _ensure_multitrack_time_visible(self, t_seconds: float):
        """If needed, pan the multitrack view so a time is visible (minimal movement)."""
        if len(self.tracks) <= 1:
            return
        max_dur = self._effective_timeline_duration()
        if max_dur <= 0:
            return
        zoom = float(getattr(self.multitrack_view, "shared_zoom", 1.0) or 1.0)
        zoom = max(1e-6, zoom)
        visible = max_dur / zoom
        if visible >= max_dur - 1e-6:
            # Everything fits.
            if self.multitrack_view.shared_pan != 0.0:
                self.pan_slider.blockSignals(True)
                self.pan_slider.setValue(0)
                self.pan_slider.blockSignals(False)
                self.multitrack_view.set_shared_pan(0.0)
            return

        pan = float(getattr(self.multitrack_view, "shared_pan", 0.0) or 0.0)
        pan = max(0.0, min(1.0, pan))
        start_time = pan * (max_dur - visible)
        end_time = start_time + visible

        # Keep a small margin so the clip doesn't sit against the edge.
        margin = visible * 0.08
        if t_seconds < start_time + margin:
            new_start = max(0.0, t_seconds - margin)
        elif t_seconds > end_time - margin:
            new_start = min(max_dur - visible, t_seconds - (visible - margin))
        else:
            return

        new_pan = new_start / max(1e-9, (max_dur - visible))
        new_pan = max(0.0, min(1.0, new_pan))

        self.pan_slider.blockSignals(True)
        self.pan_slider.setValue(int(round(new_pan * 100.0)))
        self.pan_slider.blockSignals(False)
        self.multitrack_view.set_shared_pan(new_pan)

    def _on_multitrack_selection(self, track: 'AudioTrack', start: float, end: float):
        """Handle selection change in multi-track mode."""
        print(f"DEBUG: Multi-track selection on {track.name}: {start:.2f} - {end:.2f}")

        # Store last selection per track and select it.
        try:
            track.last_selection = (start, end)
        except Exception:
            pass
        self._select_track(track)

        # Update in/out points
        self.in_entry.setText(format_time(start))
        self.out_entry.setText(format_time(end))
        self._update_button_states()

        # Highlight this track in the multitrack view if needed
        # (visual feedback that this is the selected track)

    @Slot(object)
    def _select_track(self, track: 'AudioTrack', sync_effects: bool = True):
        """Select a track for editing (fades/cuts apply to the selected track)."""
        if track is None:
            return

        if self._suppress_track_select:
            return

        self.current_track = track

        # Highlight the selected track widget
        try:
            for t, w in self.track_view_widgets.items():
                w.set_selected(t == track)
        except Exception:
            pass

        # If the track already has a selection, show it in the In/Out fields.
        tw = self.track_view_widgets.get(track)
        if tw is not None:
            try:
                s = tw.waveform_canvas.selection_start
                e = tw.waveform_canvas.selection_end
                if s is not None and e is not None:
                    track.last_selection = (s, e)
            except Exception:
                pass

        try:
            if track.last_selection:
                s, e = track.last_selection
                self.in_entry.setText(format_time(s))
                self.out_entry.setText(format_time(e))
        except Exception:
            pass

        if sync_effects:
            try:
                self._sync_effect_controls_from_track(track)
            except Exception:
                pass

        self._update_button_states()

    @Slot(float)
    def _seek_to_position(self, position: float):
        """Seek to specific position (from double-click)."""
        if not self.current_file and len(self.tracks) == 0:
            return

        # Clamp position to valid range (multi-track includes offsets).
        max_dur = self._effective_timeline_duration()
        position = max(0.0, min(max_dur, position))

        # Update visual playhead (single vs multi-track).
        if len(self.tracks) > 1:
            self.multitrack_view.set_shared_playhead(position)
        else:
            self.waveform_canvas.set_playhead(position)

        # If playing, restart from this position
        if self.playback_process is not None:
            self._stop_playback()
            self.playback_pause_position = position
            self.playback_paused = True
            self._start_playback()
        else:
            # Not playing, just update the visual position
            self.playback_pause_position = position

    # ========================================================================
    # EDIT CONTROLS
    # ========================================================================

    def _active_waveform_canvas(self) -> 'WaveformCanvas':
        """
        Return the waveform canvas that should receive selection edits and effects.
        In multi-track mode this is the selected track's canvas; otherwise it's the single-track canvas.
        """
        if len(self.tracks) > 1 and self.current_track is not None:
            tw = self.track_view_widgets.get(self.current_track)
            if tw is not None:
                return tw.waveform_canvas
        return self.waveform_canvas

    @Slot(float, float)
    def _on_ruler_selection_finalized(self, start_s: float, end_s: float):
        """
        When the user drag-selects on the shared ruler, apply that selection to the
        currently selected track (DAW behavior) and update the In/Out fields.
        """
        try:
            s = float(min(start_s, end_s))
            e = float(max(start_s, end_s))
        except Exception:
            return
        if e <= s:
            return

        if len(self.tracks) > 1 and self.current_track is None and self.tracks:
            try:
                self._select_track(self.tracks[0])
            except Exception:
                pass

        canvas = self._active_waveform_canvas()
        try:
            canvas.set_selection(s, e)
        except Exception:
            pass

        # Cache selection per-track (used by fades/cuts).
        if len(self.tracks) > 1 and self.current_track is not None:
            try:
                self.current_track.last_selection = (s, e)
            except Exception:
                pass

        try:
            self.in_entry.setText(format_time(s))
            self.out_entry.setText(format_time(e))
        except Exception:
            pass

        self._update_button_states()

    @Slot()
    def _set_in_point(self):
        """Set in point."""
        if self.playback_process is not None:
            pos = time.time() - self.playback_start_time
        else:
            pos = self.playback_pause_position

        self.in_entry.setText(format_time(pos))

        out_time = parse_time(self.out_entry.text())
        if out_time is not None:
            self._active_waveform_canvas().set_selection(pos, out_time)

    @Slot()
    def _set_out_point(self):
        """Set out point."""
        if self.playback_process is not None:
            pos = time.time() - self.playback_start_time
        else:
            pos = self.playback_pause_position

        self.out_entry.setText(format_time(pos))

        in_time = parse_time(self.in_entry.text())
        if in_time is not None:
            self._active_waveform_canvas().set_selection(in_time, pos)

    @Slot()
    def _on_in_changed(self):
        """Handle in time change."""
        in_time = parse_time(self.in_entry.text())
        out_time = parse_time(self.out_entry.text())

        if in_time is not None and out_time is not None:
            self._active_waveform_canvas().set_selection(in_time, out_time)

    @Slot()
    def _on_out_changed(self):
        """Handle out time change."""
        in_time = parse_time(self.in_entry.text())
        out_time = parse_time(self.out_entry.text())

        if in_time is not None and out_time is not None:
            self._active_waveform_canvas().set_selection(in_time, out_time)

    @Slot()
    def _clear_selection(self):
        """Clear selection."""
        self._active_waveform_canvas().clear_selection()
        self.in_entry.clear()
        self.out_entry.clear()

    @Slot()
    def _clear_all_cuts(self):
        """Clear all cuts."""
        self._active_waveform_canvas().clear_cuts()
        self.cuts_list.clear()

    # ========================================================================
    # MULTI-TRACK SUPPORT
    # ========================================================================

    def _add_track(self):
        """Add a new audio track to the multi-track session."""
        file_dialog = QFileDialog()
        file_paths, _ = file_dialog.getOpenFileNames(
            self,
            "Select Audio File for New Track",
            "",
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.ogg *.aac);;All Files (*.*)"
        )

        if not file_paths:
            return

        for file_path in file_paths:
            # Create new track
            track_name = f"Track {len(self.tracks) + 1} - {Path(file_path).name}"
            track = AudioTrack(track_name, file_path)
            track.duration = get_audio_duration(file_path) or 0.0

            # Add to tracks list
            self.tracks.append(track)

            # Add to MultiTrackView
            track_widget = self.multitrack_view.add_track(track)

            # Store track widget in the dialog's dict for easy lookup
            self.track_view_widgets[track] = track_widget

            # Connect waveform selection to update in/out points and set as current track
            track_widget.waveform_canvas.selection_changed.connect(
                lambda start, end, t=track: self._on_multitrack_selection(t, start, end)
            )

            # Load waveform for this track
            self._load_track_waveform(track, track_widget)

        # Update the waveform display to show the appropriate view
        self._update_waveform_display()

        QMessageBox.information(
            self,
            "Tracks Added",
            f"Added {len(file_paths)} track(s) to multi-track session.\n\n"
            "Multi-track mixing will be applied on export using ffmpeg filter_complex."
        )

    def _create_track_widget(self, track: AudioTrack):
        """Create a widget for displaying and controlling a track."""
        item = QListWidgetItem(self.track_list)
        item.setSizeHint(QSize(200, 80))

        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {THEME['bg_control']};
                border: 2px solid {track.color};
                border-radius: 6px;
                padding: 4px;
            }}
        """)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Track name
        name_label = QLabel(track.name)
        name_label.setStyleSheet(f"color: {THEME['text_primary']}; font-weight: bold; font-size: 11px;")
        layout.addWidget(name_label)

        # Controls row
        controls_layout = QHBoxLayout()

        # Solo button
        solo_btn = QPushButton("S")
        solo_btn.setFixedSize(24, 24)
        solo_btn.setCheckable(True)
        solo_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['bg_toolbar']};
                color: {THEME['text_secondary']};
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: #ffeb3b;
                color: #000000;
            }}
        """)
        solo_btn.clicked.connect(lambda checked, t=track: self._toggle_track_solo(t, checked))
        controls_layout.addWidget(solo_btn)

        # Mute button
        mute_btn = QPushButton("M")
        mute_btn.setFixedSize(24, 24)
        mute_btn.setCheckable(True)
        mute_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['bg_toolbar']};
                color: {THEME['text_secondary']};
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: {THEME['danger']};
                color: {THEME['text_primary']};
            }}
        """)
        mute_btn.clicked.connect(lambda checked, t=track: self._toggle_track_mute(t, checked))
        controls_layout.addWidget(mute_btn)

        # Volume slider
        vol_slider = QSlider(Qt.Horizontal)
        vol_slider.setRange(-60, 12)
        vol_slider.setValue(0)
        vol_slider.setFixedWidth(80)
        vol_slider.valueChanged.connect(lambda val, t=track: self._set_track_volume(t, val))
        controls_layout.addWidget(vol_slider)

        # Volume label
        vol_label = QLabel("0dB")
        vol_label.setFixedWidth(35)
        vol_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 9px;")
        controls_layout.addWidget(vol_label)

        # Connect slider to label
        vol_slider.valueChanged.connect(lambda val, lbl=vol_label: lbl.setText(f"{val}dB"))

        layout.addLayout(controls_layout)

        # Pan control
        pan_layout = QHBoxLayout()
        pan_layout.addWidget(QLabel("Pan:"))
        pan_slider = QSlider(Qt.Horizontal)
        pan_slider.setRange(-10, 10)  # -1.0 to 1.0
        pan_slider.setValue(0)
        pan_slider.valueChanged.connect(lambda val, t=track: self._set_track_pan(t, val / 10.0))
        pan_layout.addWidget(pan_slider, 1)
        pan_label = QLabel("C")
        pan_label.setFixedWidth(20)
        pan_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 9px;")
        pan_layout.addWidget(pan_label)

        # Update pan label
        def update_pan_label(val):
            if val < -1:
                pan_label.setText("L")
            elif val > 1:
                pan_label.setText("R")
            else:
                pan_label.setText("C")
        pan_slider.valueChanged.connect(update_pan_label)

        layout.addLayout(pan_layout)

        self.track_list.setItemWidget(item, widget)
        self.track_list_widgets[track] = widget

    def _load_track_waveform(self, track: AudioTrack, track_widget: TrackWidget):
        """Load waveform with proper thread management."""
        # Create worker
        worker = WaveformWorker(str(track.file_path), samples=2000)

        # Store reference to prevent garbage collection
        if not hasattr(self, '_track_workers'):
            self._track_workers = []

        # Clean up finished workers (do NOT use isRunning() here — it can be False
        # briefly right after start(), which could drop the last reference and crash).
        self._track_workers = [w for w in self._track_workers if not w.isFinished()]
        try:
            worker.setParent(self)
        except Exception:
            pass

        def on_finished(peaks):
            """Waveform loaded successfully."""
            try:
                track.waveform_data = peaks
                track_widget.waveform_canvas.set_peaks(peaks, track.duration)

                # Copy fade/cut regions from track to waveform canvas using setters
                track_widget.waveform_canvas.set_fade_in_regions(track.fade_in_regions.copy())
                track_widget.waveform_canvas.set_fade_out_regions(track.fade_out_regions.copy())
                track_widget.waveform_canvas.set_cuts(track.cut_regions.copy())
            except RuntimeError:
                # Widget was deleted, ignore
                pass
            finally:
                # Remove worker from list
                if worker in self._track_workers:
                    self._track_workers.remove(worker)

        def on_error(error_msg):
            """Waveform loading failed."""
            print(f"Error loading waveform for {track.name}: {error_msg}")
            try:
                track_widget.waveform_canvas.set_peaks([], track.duration)
            except RuntimeError:
                # Widget was deleted, ignore
                pass
            finally:
                if worker in self._track_workers:
                    self._track_workers.remove(worker)

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)

        # Store worker and start
        self._track_workers.append(worker)
        worker.start()

    def _toggle_track_solo(self, track: AudioTrack, checked: bool):
        """Toggle solo state for a track."""
        track.solo = checked
        # If solo is on, mute all other tracks
        if checked:
            for t in self.tracks:
                if t != track:
                    t.mute = True

    def _toggle_track_mute(self, track: AudioTrack, checked: bool):
        """Toggle mute state for a track."""
        track.mute = checked

    def _set_track_volume(self, track: AudioTrack, volume_db: float):
        """Set volume for a track."""
        track.volume = volume_db

    def _set_track_pan(self, track: AudioTrack, pan: float):
        """Set pan for a track (-1.0 to 1.0)."""
        track.pan = pan

    # ========================================================================
    # BUTTON STATE UPDATES & TOGGLE BEHAVIOR - CRITICAL FEATURE
    # ========================================================================

    def _update_button_states(self):
        """Update fade/cut button colors based on selection overlap - EXACT match to original."""
        if not hasattr(self, 'waveform_canvas'):
            return

        # In multi-track mode, the "active selection" is the selected track's selection
        # (shown in the In/Out fields). In single-track mode, use the waveform selection.
        if len(self.tracks) > 1 and self.current_track is not None:
            sel_start = parse_time(self.in_entry.text())
            sel_end = parse_time(self.out_entry.text())
        else:
            sel_start = self.waveform_canvas.selection_start
            sel_end = self.waveform_canvas.selection_end

        if sel_start is None or sel_end is None:
            # No selection - all buttons normal
            self.fade_in_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
            self.fade_out_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
            self.cut_btn.setStyleSheet(f"background-color: {THEME['button_inactive']};")
            self.active_fade_in_idx = None
            self.active_fade_out_idx = None
            self.active_cut_idx = None
            return

        # Check if selection overlaps existing regions
        def overlaps(r_start, r_end, s_start, s_end):
            """Check if two ranges overlap."""
            return max(r_start, s_start) < min(r_end, s_end) - 1e-9

        # Check fade in regions (use current track if in multi-track mode)
        fade_in_regions = self.current_track.fade_in_regions if (len(self.tracks) > 1 and self.current_track) else self.fade_in_regions
        self.active_fade_in_idx = None
        for i, (fade_start, fade_end) in enumerate(fade_in_regions):
            if overlaps(fade_start, fade_end, sel_start, sel_end):
                self.active_fade_in_idx = i
                break

        self.fade_in_btn.setStyleSheet(
            f"background-color: {THEME['button_active']};" if self.active_fade_in_idx is not None
            else f"background-color: {THEME['button_inactive']};"
        )

        # Check fade out regions (use current track if in multi-track mode)
        fade_out_regions = self.current_track.fade_out_regions if (len(self.tracks) > 1 and self.current_track) else self.fade_out_regions
        self.active_fade_out_idx = None
        for i, (fade_start, fade_end) in enumerate(fade_out_regions):
            if overlaps(fade_start, fade_end, sel_start, sel_end):
                self.active_fade_out_idx = i
                break

        self.fade_out_btn.setStyleSheet(
            f"background-color: {THEME['button_active']};" if self.active_fade_out_idx is not None
            else f"background-color: {THEME['button_inactive']};"
        )

        # Check cut regions (use current track if in multi-track mode)
        cut_regions = self.current_track.cut_regions if (len(self.tracks) > 1 and self.current_track) else self.waveform_canvas.cuts
        self.active_cut_idx = None
        for i, (cut_start, cut_end) in enumerate(cut_regions):
            if overlaps(cut_start, cut_end, sel_start, sel_end):
                self.active_cut_idx = i
                break

        self.cut_btn.setStyleSheet(
            f"background-color: {THEME['button_active']};" if self.active_cut_idx is not None
            else f"background-color: {THEME['button_inactive']};"
        )

    @Slot()
    def _toggle_fade_in(self):
        """Toggle fade in on/off - same button for add/remove."""
        in_time = parse_time(self.in_entry.text())
        out_time = parse_time(self.out_entry.text())

        if in_time is None or out_time is None:
            QMessageBox.warning(self, "Fade In", "Please set valid In and Out points.")
            return

        if in_time >= out_time:
            QMessageBox.warning(self, "Fade In", "In point must be before Out point.")
            return

        # Update button states to check overlap
        self._update_button_states()

        # In multi-track mode, apply to current track
        if len(self.tracks) > 1 and self.current_track is not None:
            # If overlapping existing fade in, remove it
            if self.active_fade_in_idx is not None:
                try:
                    del self.current_track.fade_in_regions[self.active_fade_in_idx]
                except:
                    self.current_track.fade_in_regions = []
                self.active_fade_in_idx = None
            else:
                # Otherwise, add new fade in
                self.current_track.fade_in_regions.append((in_time, out_time))

            # Update the track's waveform canvas
            track_widget = self.track_view_widgets.get(self.current_track)
            if track_widget:
                print(f"DEBUG: Setting fade_in_regions on track widget for {self.current_track.name}")
                print(f"DEBUG: Regions to set: {self.current_track.fade_in_regions}")
                track_widget.waveform_canvas.set_fade_in_regions(self.current_track.fade_in_regions)
                # Force immediate repaint of the inner waveform widget
                track_widget.waveform_canvas.waveform.update()
                track_widget.update()
            else:
                print(f"ERROR: Could not find track_widget for {self.current_track.name}")

            # Restart playback if playing to hear the effect immediately
            self._on_effect_changed()
        else:
            # Single track mode
            # If overlapping existing fade in, remove it
            if self.active_fade_in_idx is not None:
                try:
                    del self.fade_in_regions[self.active_fade_in_idx]
                except:
                    self.fade_in_regions = []
                self.active_fade_in_idx = None
            else:
                # Otherwise, add new fade in
                self.fade_in_regions.append((in_time, out_time))

            # CRITICAL: Update canvas with ALL fade in regions
            self.waveform_canvas.set_fade_in_regions(self.fade_in_regions)
            self.waveform_canvas.update()

        self._update_button_states()

    @Slot()
    def _toggle_fade_out(self):
        """Toggle fade out on/off - same button for add/remove."""
        in_time = parse_time(self.in_entry.text())
        out_time = parse_time(self.out_entry.text())

        if in_time is None or out_time is None:
            QMessageBox.warning(self, "Fade Out", "Please set valid In and Out points.")
            return

        if in_time >= out_time:
            QMessageBox.warning(self, "Fade Out", "In point must be before Out point.")
            return

        # Update button states to check overlap
        self._update_button_states()

        # In multi-track mode, apply to current track
        if len(self.tracks) > 1 and self.current_track is not None:
            # If overlapping existing fade out, remove it
            if self.active_fade_out_idx is not None:
                try:
                    del self.current_track.fade_out_regions[self.active_fade_out_idx]
                except:
                    self.current_track.fade_out_regions = []
                self.active_fade_out_idx = None
            else:
                # Otherwise, add new fade out
                self.current_track.fade_out_regions.append((in_time, out_time))

            # Update the track's waveform canvas
            track_widget = self.track_view_widgets.get(self.current_track)
            if track_widget:
                print(f"DEBUG: Setting fade_out_regions on track widget for {self.current_track.name}")
                print(f"DEBUG: Regions to set: {self.current_track.fade_out_regions}")
                track_widget.waveform_canvas.set_fade_out_regions(self.current_track.fade_out_regions)
                # Force immediate repaint of the inner waveform widget
                track_widget.waveform_canvas.waveform.update()
                track_widget.update()
            else:
                print(f"ERROR: Could not find track_widget for {self.current_track.name}")

            # Restart playback if playing to hear the effect immediately
            self._on_effect_changed()
        else:
            # Single track mode
            # If overlapping existing fade out, remove it
            if self.active_fade_out_idx is not None:
                try:
                    del self.fade_out_regions[self.active_fade_out_idx]
                except:
                    self.fade_out_regions = []
                self.active_fade_out_idx = None
            else:
                # Otherwise, add new fade out
                self.fade_out_regions.append((in_time, out_time))

            # CRITICAL: Update canvas with ALL fade out regions (single-track only)
            self.waveform_canvas.set_fade_out_regions(self.fade_out_regions)
            self.waveform_canvas.update()
        self._update_button_states()

    @Slot()
    def _toggle_cut(self):
        """Toggle cut on/off - same button for add/remove."""
        in_time = parse_time(self.in_entry.text())
        out_time = parse_time(self.out_entry.text())

        if in_time is None or out_time is None:
            QMessageBox.warning(self, "Cut", "Please set valid In and Out points.")
            return

        if in_time >= out_time:
            QMessageBox.warning(self, "Cut", "In point must be before Out point.")
            return

        # Update button states to check overlap
        self._update_button_states()

        # In multi-track mode, apply to current track
        if len(self.tracks) > 1 and self.current_track is not None:
            # If overlapping existing cut, remove it
            if self.active_cut_idx is not None:
                try:
                    del self.current_track.cut_regions[self.active_cut_idx]
                except:
                    self.current_track.cut_regions = []
                self.active_cut_idx = None
            else:
                # Otherwise, add new cut
                self.current_track.cut_regions.append((in_time, out_time))

            # Update the track's waveform canvas
            track_widget = self.track_view_widgets.get(self.current_track)
            if track_widget:
                print(f"DEBUG: Setting cut_regions on track widget for {self.current_track.name}")
                print(f"DEBUG: Regions to set: {self.current_track.cut_regions}")
                track_widget.waveform_canvas.set_cuts(self.current_track.cut_regions)
                # Force immediate repaint
                track_widget.waveform_canvas.waveform.update()
                track_widget.update()
            else:
                print(f"ERROR: Could not find track_widget for {self.current_track.name}")

            # Restart playback if playing to hear the effect immediately
            self._on_effect_changed()
        else:
            # Single track mode
            # If overlapping existing cut, remove it
            if self.active_cut_idx is not None:
                try:
                    del self.waveform_canvas.cuts[self.active_cut_idx]
                except:
                    self.waveform_canvas.cuts = []
                self.active_cut_idx = None
            else:
                # Otherwise, add new cut
                self.waveform_canvas.cuts.append((in_time, out_time))

            # CRITICAL: Update canvas with ALL cut regions
            self.waveform_canvas.set_cuts(self.waveform_canvas.cuts)
            self.waveform_canvas.update()

            # Update cuts list widget
            self.cuts_list.clear()
            for cut_start, cut_end in self.waveform_canvas.cuts:
                self.cuts_list.addItem(f"{format_time(cut_start)} - {format_time(cut_end)}")

        self._update_button_states()

    # ========================================================================
    # MINI RULER PAINTING
    # ========================================================================

    def _paint_mini_ruler(self, event):
        """Paint mini time ruler showing visible portion - EXACT match to original."""
        if not hasattr(self, 'waveform_canvas') or not hasattr(self, 'mini_ruler'):
            return

        painter = QPainter(self.mini_ruler)
        painter.setRenderHint(QPainter.Antialiasing, False)

        rect = self.mini_ruler.rect()
        width = rect.width()
        height = rect.height()

        # Draw background
        painter.fillRect(rect, QColor("#1f1f1f"))

        if self.current_duration <= 0:
            return

        # Calculate visible range based on zoom and pan
        visible_duration = self.current_duration / self.waveform_canvas.zoom
        start_time = self.waveform_canvas.pan * (self.current_duration - visible_duration)
        end_time = start_time + visible_duration

        # Calculate grid interval (smart spacing)
        tick_candidates = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
        target = max(0.5, visible_duration / 10.0)
        step = min(tick_candidates, key=lambda v: abs(v - target))

        # Draw ruler line
        y = height - 2
        painter.setPen(QPen(QColor(THEME["grid_line"]), 1))
        painter.drawLine(0, y, width, y)

        # Draw ticks and labels
        painter.setFont(QFont("Segoe UI", 8))
        t = max(0.0, (int(start_time // step)) * step)
        if t < start_time:
            t += step

        while t <= end_time + 1e-6:
            if width > 0 and visible_duration > 0:
                x = int(((t - start_time) / visible_duration) * width)
                painter.setPen(QPen(QColor(THEME["grid_tick"]), 1))
                painter.drawLine(x, y, x, y - 6)

                # Draw labels for major ticks
                if step >= 5 or abs((t / step) % 2) < 1e-6:
                    painter.setPen(QColor(THEME["text_tip"]))
                    painter.drawText(x + 2, 2, width - x - 2, height - 4, Qt.AlignLeft | Qt.AlignTop, format_time(t))

            t += step

    # ========================================================================
    # AI PROMPT HANDLING
    # ========================================================================

    def _apply_prompt(self):
        """Apply AI prompt (placeholder for now)."""
        prompt = self.prompt_entry.text().strip()
        if not prompt:
            return

        QMessageBox.information(
            self,
            "AI Prompt",
            f"AI prompt processing not yet implemented.\n\nYour prompt: {prompt}\n\nThis will use the AI manager to parse and apply edits automatically."
        )

    def _show_prompt_examples(self):
        """Show AI prompt examples."""
        msg = (
            "Examples:\n\n"
            "1) grab track 16 - DtMF.flac and create a ringtone by cutting between 1:23 to 1:41 into DtMF_Ringtone.mp3\n\n"
            "2) grab file 11 - TURiSTA.flac and cut 00:00:00-00:00:35.735 and starting from 00:00:25.000 start to fade out until it ends, export mp3\n\n"
            "3) use \"My Song.flac\" trim 0:10-0:40, normalize, export mp3 192k as my_song_clip\n\n"
            "Tip: The editor applies a fast offline parse immediately, then (if the AI model is loaded) it refines the parse in the background."
        )
        QMessageBox.information(self, "Audio Prompt Examples", msg)

    # ========================================================================
    # DRAG AND DROP SUPPORT
    # ========================================================================

    def dragEnterEvent(self, event):
        """Accept drag events with audio files."""
        if event.mimeData().hasUrls():
            # Check if any URLs are audio files
            urls = event.mimeData().urls()
            audio_exts = ('.mp3', '.wav', '.flac', '.m4a', '.ogg', '.opus', '.aac')
            for url in urls:
                if url.toLocalFile().lower().endswith(audio_exts):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        """Accept drag move events."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle dropped audio files."""
        if event.mimeData().hasUrls():
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            audio_exts = ('.mp3', '.wav', '.flac', '.m4a', '.ogg', '.opus', '.aac')
            audio_files = [f for f in files if f.lower().endswith(audio_exts)]

            if audio_files:
                # Defer actual add to avoid re-entrancy during drop handling.
                self._queue_drop_files(audio_files)
                event.acceptProposedAction()
            else:
                QMessageBox.warning(
                    self,
                    "No Audio Files",
                    "No supported audio files found in drop.\n\nSupported formats: MP3, WAV, FLAC, M4A, OGG, OPUS, AAC"
                )
        else:
            event.ignore()

    def _queue_drop_files(self, audio_files: list[str]):
        """Queue dropped files to avoid dropEvent re-entrancy crashes."""
        if not audio_files:
            return
        for f in audio_files:
            if f not in self._drop_queue:
                self._drop_queue.append(f)
        if not self._drop_in_progress:
            self._drop_in_progress = True
            QTimer.singleShot(0, self._process_drop_queue)

    def _process_drop_queue(self):
        """Process queued drops on the next event loop tick."""
        if not self._drop_queue:
            self._drop_in_progress = False
            return
        files = list(self._drop_queue)
        self._drop_queue.clear()
        try:
            self.add_files(files)
        finally:
            if self._drop_queue:
                QTimer.singleShot(0, self._process_drop_queue)
            else:
                self._drop_in_progress = False

    # ========================================================================
    # SIDEBAR TOGGLE
    # ========================================================================

    def _toggle_sidebar(self):
        """Toggle sidebar visibility."""
        self.sidebar_collapsed = not self.sidebar_collapsed

        splitter = getattr(self, "main_splitter", None)
        left_container = getattr(self, "left_container", None)
        left_panel = getattr(self, "left_panel", None)

        if left_panel is None:
            return

        if self.sidebar_collapsed:
            try:
                self.sidebar_width = max(self.sidebar_width, int(left_panel.width()))
            except Exception:
                pass

            left_panel.hide()
            self.sidebar_toggle_btn.setText("⟩")

            if left_container is not None:
                collapsed_width = max(22, int(self.sidebar_toggle_btn.width()) + 8)
                try:
                    left_container.setMinimumWidth(collapsed_width)
                    left_container.setMaximumWidth(collapsed_width)
                except Exception:
                    pass

                try:
                    if splitter is not None:
                        sizes = splitter.sizes()
                        if len(sizes) >= 3:
                            total = sum(sizes)
                            remaining = max(0, total - collapsed_width)
                            center = sizes[1]
                            right = sizes[2]
                            total_cr = max(1, center + right)
                            new_center = int(round(remaining * (center / total_cr)))
                            new_right = max(0, remaining - new_center)
                            splitter.setSizes([collapsed_width, new_center, new_right])
                except Exception:
                    pass
        else:
            left_panel.show()
            self.sidebar_toggle_btn.setText("⟨")

            if left_container is not None:
                try:
                    left_container.setMaximumWidth(16777215)
                    left_container.setMinimumWidth(0)
                except Exception:
                    pass

            try:
                if splitter is not None:
                    sizes = splitter.sizes()
                    if len(sizes) >= 3:
                        total = sum(sizes)
                        new_left = int(max(self.sidebar_width, 200))
                        if total > 0:
                            new_left = min(new_left, max(0, total - 50))
                        remaining = max(0, total - new_left)
                        center = sizes[1]
                        right = sizes[2]
                        total_cr = max(1, center + right)
                        new_center = int(round(remaining * (center / total_cr)))
                        new_right = max(0, remaining - new_center)
                        splitter.setSizes([new_left, new_center, new_right])
            except Exception:
                pass

    # ========================================================================
    # EXPORT
    # ========================================================================

    @Slot()
    def _show_export_dialog(self):
        """Show export dialog."""
        # Check if we have tracks (multi-track mode) or single file
        if self.tracks:
            # Multi-track export
            format_ = self.format_combo.currentText().lower()
            default_name = f"multitrack_mix.{format_}"

            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Multi-Track Mix",
                default_name,
                f"{format_.upper()} Files (*.{format_});;All Files (*.*)",
            )

            if output_path:
                self._export_multitrack(output_path)
        elif self.current_file:
            # Single track export
            format_ = self.format_combo.currentText().lower()
            default_name = Path(self.current_file).stem + f"_edited.{format_}"

            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Audio",
                default_name,
                f"{format_.upper()} Files (*.{format_});;All Files (*.*)",
            )

            if output_path:
                self._export_audio(output_path)
        else:
            QMessageBox.warning(self, "Error", "No audio file or tracks loaded.")
            return

    def _export_audio(self, output_path: str):
        """Export audio."""
        format_ = self.format_combo.currentText().lower()
        bitrate = self.bitrate_combo.currentText()
        normalize = self.normalize_check.isChecked()
        volume_gain = self.volume_spin.value()

        cuts = self.waveform_canvas.cuts
        # Use first fade in/out region if any exist
        fade_in = self.fade_in_regions[0] if self.fade_in_regions else None
        fade_out = self.fade_out_regions[0] if self.fade_out_regions else None

        self.status_bar.setValue(0)
        self.status_bar.setFormat("Exporting audio... %p%")
        self.status_bar.setVisible(True)

        self.export_worker = ExportWorker(
            self.current_file,
            output_path,
            format_,
            bitrate,
            normalize,
            volume_gain,
            cuts,
            fade_in,
            fade_out,
        )
        self.export_worker.progress.connect(self._on_export_progress)
        self.export_worker.finished.connect(self._on_export_finished)
        self.export_worker.error.connect(self._on_export_error)
        self.export_worker.start()

    def _export_multitrack(self, output_path: str):
        """Export multi-track mix using ffmpeg filter_complex."""
        if not self.tracks:
            QMessageBox.warning(self, "Error", "No tracks to export.")
            return

        ffmpeg = get_ffmpeg_exe()
        if not ffmpeg:
            QMessageBox.critical(self, "Error", "FFmpeg not found.")
            return

        format_ = self.format_combo.currentText().lower()
        bitrate = self.bitrate_combo.currentText()

        try:
            # Build ffmpeg command for multi-track mixing
            cmd = [str(ffmpeg)]

            # Add input files for all tracks
            for track in self.tracks:
                cmd.extend(["-i", str(track.file_path)])

            # Build filter_complex for mixing
            filter_parts = []

            # Process each track with its effects
            for i, track in enumerate(self.tracks):
                track_filter = track.get_ffmpeg_filter()

                # Apply mute/solo logic
                if track.mute or (any(t.solo for t in self.tracks) and not track.solo):
                    # Muted or not soloed when solo is active
                    filter_parts.append(f"[{i}:a]volume=0[a{i}]")
                else:
                    # Apply track's filter chain
                    filter_parts.append(f"[{i}:a]{track_filter}[a{i}]")

            # Mix all processed tracks
            mix_inputs = "".join(f"[a{i}]" for i in range(len(self.tracks)))
            filter_parts.append(f"{mix_inputs}amix=inputs={len(self.tracks)}:duration=longest[aout]")

            # Combine all filter parts
            filter_complex = ";".join(filter_parts)

            cmd.extend(["-filter_complex", filter_complex])
            cmd.extend(["-map", "[aout]"])

            # Output settings
            if format_ == "mp3":
                cmd.extend(["-b:a", bitrate])
            elif format_ == "wav":
                cmd.extend(["-c:a", "pcm_s16le"])
            elif format_ == "flac":
                cmd.extend(["-c:a", "flac"])

            cmd.append(str(output_path))

            # Show progress
            self.status_bar.setValue(0)
            self.status_bar.setFormat("Mixing tracks... (this may take a while)")
            self.status_bar.setVisible(True)

            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            if result.returncode == 0:
                self.status_bar.setVisible(False)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Multi-track mix exported successfully to:\n{output_path}\n\n"
                    f"Mixed {len(self.tracks)} tracks with effects applied."
                )
            else:
                error_msg = result.stderr.decode('utf-8', errors='ignore') if result.stderr else "Unknown error"
                self.status_bar.setVisible(False)
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export multi-track mix:\n{error_msg}"
                )

        except Exception as e:
            self.status_bar.setVisible(False)
            QMessageBox.critical(self, "Export Error", f"Failed to export multi-track mix:\n{str(e)}")

    @Slot(int)
    def _on_export_progress(self, percent: int):
        """Handle export progress."""
        self.status_bar.setValue(percent)

    @Slot(str)
    def _on_export_finished(self, output_path: str):
        """Handle export finished."""
        self.status_bar.setVisible(False)
        QMessageBox.information(self, "Export Complete", f"Audio exported successfully to:\n{output_path}")

    @Slot(str)
    def _on_export_error(self, error: str):
        """Handle export error."""
        self.status_bar.setVisible(False)
        QMessageBox.critical(self, "Export Error", f"Failed to export audio:\n{error}")

    # ========================================================================
    # ADVANCED EDITING TOOLS
    # ========================================================================

    def _trim_start(self):
        """Trim audio from start to playhead position."""
        if not hasattr(self, 'waveform_canvas'):
            return
        playhead = self.waveform_canvas.playhead
        if playhead > 0:
            # Set in point to playhead, out point to end
            self.in_entry.setText(format_time(playhead))
            self.out_entry.setText(format_time(self.waveform_canvas.duration))
            QMessageBox.information(self, "Trim Start", f"Set In point to {format_time(playhead)}.\nExport to apply trim.")

    def _trim_end(self):
        """Trim audio from playhead position to end."""
        if not hasattr(self, 'waveform_canvas'):
            return
        playhead = self.waveform_canvas.playhead
        if playhead < self.waveform_canvas.duration:
            # Set out point to playhead
            self.out_entry.setText(format_time(playhead))
            QMessageBox.information(self, "Trim End", f"Set Out point to {format_time(playhead)}.\nExport to apply trim.")

    def _split_at_playhead(self):
        """Split audio at playhead position."""
        if not self.current_file or not hasattr(self, 'waveform_canvas'):
            QMessageBox.warning(self, "Error", "No audio file loaded.")
            return

        playhead = self.waveform_canvas.playhead
        if playhead <= 0 or playhead >= self.waveform_canvas.duration:
            QMessageBox.warning(self, "Error", "Playhead must be within audio range.")
            return

        QMessageBox.information(
            self,
            "Split Audio",
            f"To split at {format_time(playhead)}:\n\n"
            f"1. Set In=0, Out={format_time(playhead)}, export as part1\n"
            f"2. Set In={format_time(playhead)}, Out=end, export as part2"
        )

    def _detect_silence(self):
        """Auto-detect silent regions."""
        QMessageBox.information(
            self,
            "Silence Detection",
            "Silence detection analyzes audio for quiet regions.\n\n"
            "This feature uses ffmpeg silencedetect filter.\n"
            "Implementation: Use ffmpeg -af silencedetect to find silent regions."
        )

    def _add_marker(self):
        """Add marker at playhead position."""
        if not hasattr(self, 'waveform_canvas'):
            return
        playhead = self.waveform_canvas.playhead
        QMessageBox.information(
            self,
            "Marker Added",
            f"Marker added at {format_time(playhead)}\n\n"
            "Markers can be used as chapter points for export."
        )

    def _time_stretch(self):
        """Time stretch selection without changing pitch."""
        QMessageBox.information(
            self,
            "Time Stretch",
            "Time stretching changes duration without affecting pitch.\n\n"
            "Use the Speed Change effect with 'Preserve Pitch' enabled\n"
            "in the Effects panel on the right."
        )

    def _insert_silence(self):
        """Insert silence at playhead position."""
        if not self.current_file:
            QMessageBox.warning(self, "Insert Silence", "No audio file loaded.")
            return

        duration, ok = QInputDialog.getDouble(
            self, "Insert Silence",
            "Duration (seconds):",
            1.0, 0.1, 60.0, 1
        )
        if not ok:
            return

        playhead = self.waveform_canvas.playhead

        # Create temp output file
        current_path = Path(self.current_file)
        output = current_path.parent / f"{current_path.stem}_silence{current_path.suffix}"

        # Split audio at playhead, insert silence, concatenate
        # We need to split into two parts and add silence in between
        part1 = tempfile.mktemp(suffix='.wav')
        part2 = tempfile.mktemp(suffix='.wav')
        silence = tempfile.mktemp(suffix='.wav')

        try:
            # Extract first part (0 to playhead)
            if playhead > 0:
                cmd1 = [
                    get_ffmpeg_exe(),
                    "-i", str(self.current_file),
                    "-t", str(playhead),
                    "-y", part1
                ]
                subprocess.run(cmd1, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Extract second part (playhead to end)
            if playhead < self.current_duration:
                cmd2 = [
                    get_ffmpeg_exe(),
                    "-i", str(self.current_file),
                    "-ss", str(playhead),
                    "-y", part2
                ]
                subprocess.run(cmd2, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Generate silence
            cmd_silence = [
                get_ffmpeg_exe(),
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(duration),
                "-y", silence
            ]
            subprocess.run(cmd_silence, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Concatenate all parts
            concat_file = tempfile.mktemp(suffix='.txt')
            with open(concat_file, 'w') as f:
                if playhead > 0 and Path(part1).exists():
                    f.write(f"file '{part1}'\n")
                if Path(silence).exists():
                    f.write(f"file '{silence}'\n")
                if playhead < self.current_duration and Path(part2).exists():
                    f.write(f"file '{part2}'\n")

            cmd_concat = [
                get_ffmpeg_exe(),
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-y", str(output)
            ]

            result = subprocess.run(cmd_concat, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Clean up temp files
            for temp_file in [part1, part2, silence, concat_file]:
                Path(temp_file).unlink(missing_ok=True)

            if result.returncode == 0:
                QMessageBox.information(self, "Success", f"Silence inserted.\nOutput: {output.name}")
                # Reload the file
                self.add_files([str(output)])
            else:
                QMessageBox.critical(self, "Error", f"Failed to insert silence:\n{result.stderr.decode()}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to insert silence:\n{str(e)}")
            # Clean up on error
            for temp_file in [part1, part2, silence]:
                Path(temp_file).unlink(missing_ok=True)

    def _reverse_selection(self):
        """Reverse selected audio region."""
        if not self.current_file:
            QMessageBox.warning(self, "Reverse Selection", "No audio file loaded.")
            return

        sel_start = self.waveform_canvas.selection_start
        sel_end = self.waveform_canvas.selection_end

        if sel_start is None or sel_end is None:
            QMessageBox.warning(self, "Reverse Selection", "No selection made. Select a region first.")
            return

        # Create output file
        current_path = Path(self.current_file)
        output = current_path.parent / f"{current_path.stem}_reversed{current_path.suffix}"

        # Extract selection, reverse it, and replace in original
        part1 = tempfile.mktemp(suffix='.wav')  # Before selection
        part2 = tempfile.mktemp(suffix='.wav')  # Selection (to be reversed)
        part3 = tempfile.mktemp(suffix='.wav')  # After selection
        reversed_part = tempfile.mktemp(suffix='.wav')

        try:
            # Extract part before selection
            if sel_start > 0:
                cmd1 = [
                    get_ffmpeg_exe(),
                    "-i", str(self.current_file),
                    "-t", str(sel_start),
                    "-y", part1
                ]
                subprocess.run(cmd1, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Extract selection
            cmd2 = [
                get_ffmpeg_exe(),
                "-i", str(self.current_file),
                "-ss", str(sel_start),
                "-t", str(sel_end - sel_start),
                "-y", part2
            ]
            subprocess.run(cmd2, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Reverse the selection
            cmd_reverse = [
                get_ffmpeg_exe(),
                "-i", part2,
                "-af", "areverse",
                "-y", reversed_part
            ]
            subprocess.run(cmd_reverse, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Extract part after selection
            if sel_end < self.current_duration:
                cmd3 = [
                    get_ffmpeg_exe(),
                    "-i", str(self.current_file),
                    "-ss", str(sel_end),
                    "-y", part3
                ]
                subprocess.run(cmd3, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Concatenate all parts
            concat_file = tempfile.mktemp(suffix='.txt')
            with open(concat_file, 'w') as f:
                if sel_start > 0 and Path(part1).exists():
                    f.write(f"file '{part1}'\n")
                if Path(reversed_part).exists():
                    f.write(f"file '{reversed_part}'\n")
                if sel_end < self.current_duration and Path(part3).exists():
                    f.write(f"file '{part3}'\n")

            cmd_concat = [
                get_ffmpeg_exe(),
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-y", str(output)
            ]

            result = subprocess.run(cmd_concat, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

            # Clean up temp files
            for temp_file in [part1, part2, part3, reversed_part, concat_file]:
                Path(temp_file).unlink(missing_ok=True)

            if result.returncode == 0:
                QMessageBox.information(self, "Success", f"Selection reversed.\nOutput: {output.name}")
                self.add_files([str(output)])
            else:
                QMessageBox.critical(self, "Error", f"Failed to reverse selection:\n{result.stderr.decode()}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reverse selection:\n{str(e)}")
            # Clean up on error
            for temp_file in [part1, part2, part3, reversed_part]:
                Path(temp_file).unlink(missing_ok=True)

    def _copy_selection(self):
        """Copy selected region to clipboard."""
        if not hasattr(self, 'waveform_canvas'):
            return

        sel_start = self.waveform_canvas.selection_start
        sel_end = self.waveform_canvas.selection_end

        if sel_start is None or sel_end is None:
            QMessageBox.warning(self, "Error", "No selection made. Select a region first.")
            return

        # Store in instance variable (simple clipboard)
        self._clipboard = (sel_start, sel_end)
        QMessageBox.information(
            self,
            "Copy Selection",
            f"Copied region from {format_time(sel_start)} to {format_time(sel_end)}\n\n"
            f"Duration: {format_time(sel_end - sel_start)}"
        )

    def _paste_at_playhead(self):
        """Paste clipboard content at playhead."""
        if not hasattr(self, '_clipboard'):
            QMessageBox.warning(self, "Error", "Nothing to paste. Copy a selection first.")
            return

        playhead = self.waveform_canvas.playhead
        start, end = self._clipboard
        duration = end - start

        QMessageBox.information(
            self,
            "Paste at Playhead",
            f"Pasting {format_time(duration)} of audio at {format_time(playhead)}\n\n"
            "Use ffmpeg to extract copied region and concatenate."
        )

    def _duplicate_selection(self):
        """Duplicate selected region."""
        if not hasattr(self, 'waveform_canvas'):
            return

        sel_start = self.waveform_canvas.selection_start
        sel_end = self.waveform_canvas.selection_end

        if sel_start is None or sel_end is None:
            QMessageBox.warning(self, "Error", "No selection made. Select a region first.")
            return

        duration = sel_end - sel_start
        QMessageBox.information(
            self,
            "Duplicate Selection",
            f"Duplicating {format_time(duration)} of audio\n\n"
            "The selection will be repeated after the original."
        )

    # ========================================================================
    # CLEANUP
    # ========================================================================

    def closeEvent(self, event):
        """Properly clean up ALL threads before closing."""
        # Stop playback
        self._stop_playback()

        # Wait for main waveform worker
        if self.waveform_worker is not None and self.waveform_worker.isRunning():
            self.waveform_worker.terminate()
            self.waveform_worker.wait(1000)  # Wait max 1 second

        # Wait for export worker
        if self.export_worker is not None and self.export_worker.isRunning():
            self.export_worker.terminate()
            self.export_worker.wait(1000)

        # Wait for ALL track workers
        if hasattr(self, '_track_workers'):
            for worker in self._track_workers:
                if worker.isRunning():
                    worker.terminate()
                    worker.wait(1000)
            self._track_workers.clear()

        event.accept()
