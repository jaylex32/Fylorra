"""
Fylorra - Media Editors Dialog
Simple launcher for Video Editor + Audio Editor.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES  # type: ignore
except Exception:  # pragma: no cover
    TkinterDnD = None  # type: ignore
    DND_FILES = None  # type: ignore


def _is_audio(path: Path) -> bool:
    return path.suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


_DND_AVAILABLE = TkinterDnD is not None and DND_FILES is not None


class MediaEditorsView(ctk.CTkFrame):
    """Embeddable Media Editors view (used in MainWindow)."""

    def __init__(self, parent, ai_manager=None):
        super().__init__(parent, fg_color="transparent")
        self._app_root = self.winfo_toplevel()
        self.ai_manager = ai_manager
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=16, pady=(16, 12), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(header, text="Media Editors", font=ctk.CTkFont(size=22, weight="bold"))
        title.grid(row=0, column=0, padx=14, pady=(14, 2), sticky="w")
        subtitle = ctk.CTkLabel(
            header,
            text="Open Audio or Video editor directly (no File Tools needed).",
            text_color=("#a7abb3", "#a7abb3"),
        )
        subtitle.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="w")

        quick = ctk.CTkFrame(header, fg_color="transparent")
        quick.grid(row=0, column=1, rowspan=2, padx=14, pady=14, sticky="e")

        ctk.CTkButton(quick, text="Open File…", width=120, command=self._open_any_file).pack(side="left", padx=(0, 10))
        ctk.CTkButton(quick, text="Video Editor", width=120, command=lambda: self._open_video_editor(None)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(quick, text="Audio Editor", width=120, command=lambda: self._open_audio_editor(None)).pack(side="left")

        body = ctk.CTkFrame(self, corner_radius=12)
        body.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.video_card = self._make_card(
            body,
            title="Video Editor",
            desc="Edit videos, images (slideshow), audio lanes and render with presets.",
            primary=("Open Video Editor", lambda: self._open_video_editor(None)),
            secondary=("Import Video / Images…", self._import_video_or_images),
        )
        self.video_card.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="nsew")

        self.audio_card = self._make_card(
            body,
            title="Audio Editor",
            desc="Waveform editing: select range, cut, normalize, fade in/out, export presets.",
            primary=("Open Audio Editor", lambda: self._open_audio_editor(None)),
            secondary=("Import Audio…", self._import_audio),
        )
        self.audio_card.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="nsew")

    def _make_card(self, parent, *, title: str, desc: str, primary: tuple[str, callable], secondary: tuple[str, callable]):
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=18, pady=(18, 6), sticky="w")
        ctk.CTkLabel(card, text=desc, text_color=("#a7abb3", "#a7abb3"), wraplength=360, justify="left").grid(
            row=1, column=0, padx=18, pady=(0, 16), sticky="w"
        )

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="ew")
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(btns, text=primary[0], height=42, command=primary[1]).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(btns, text=secondary[0], height=42, fg_color="#444", command=secondary[1]).grid(row=0, column=1, padx=(8, 0), sticky="ew")
        return card

    def _open_any_file(self):
        f = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Open a media file",
            filetypes=[("Media files", "*.*"), ("All files", "*.*")],
        )
        if not f:
            return
        p = Path(f)
        if _is_audio(p):
            self._open_audio_editor(p)
        elif _is_video(p) or _is_image(p):
            self._open_video_editor(p)

    def _import_video_or_images(self):
        files = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="Import video/images",
            filetypes=[("Video/Images", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"), ("All files", "*.*")],
        )
        if not files:
            return
        self._open_video_editor(Path(files[0]))

    def _import_audio(self):
        files = filedialog.askopenfilenames(
            parent=self.winfo_toplevel(),
            title="Import audio",
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus"), ("All files", "*.*")],
        )
        if not files:
            return
        self._open_audio_editor(Path(files[0]))

    def _open_video_editor(self, path: Path | None):
        import subprocess
        import sys
        import json

        root = Path(__file__).resolve().parents[1]
        p = str(path) if path else ""
        p_lit = json.dumps(p)
        code = (
            "import sys; from PySide6.QtWidgets import QApplication; "
            "from core.settings_manager import SettingsManager; from core.ai_manager import AIManager; "
            "from gui.video_editor_dialog import VideoEditorDialog; "
            "app=QApplication(sys.argv); s=SettingsManager(); ai=AIManager(s.app_folder, s); "
            f"dlg=VideoEditorDialog(None, ai, initial_file=({p_lit} or None)); "
            "app.setQuitOnLastWindowClosed(True); dlg.show(); sys.exit(app.exec())"
        )
        subprocess.Popen([sys.executable, "-c", code], cwd=str(root))

    def _open_audio_editor(self, path: Path | None):
        from gui.audio_editor_dialog import AudioEditorDialog

        AudioEditorDialog(self.winfo_toplevel(), self.ai_manager, initial_file=path)


class MediaEditorsDialog(ctk.CTkToplevel, TkinterDnD.DnDWrapper if _DND_AVAILABLE else object):
    def __init__(self, parent, ai_manager=None):
        super().__init__(parent)
        self._app_root = parent
        self.ai_manager = ai_manager
        self.title("Media Editors")
        self.geometry("980x640")
        self.minsize(900, 580)
        try:
            self.attributes("-toolwindow", False)
        except Exception:
            pass
        try:
            self.overrideredirect(False)
        except Exception:
            pass

        self._build_ui()

        # Optional DnD (only if tkinterdnd2 is installed and active)
        if _DND_AVAILABLE:
            try:
                TkinterDnD.DnDWrapper.__init__(self)  # type: ignore[misc]
            except Exception:
                pass
        self._setup_dnd()

        # Ensure this launcher opens in front of the main window.
        self.after(0, self._bring_to_front)
        self.after(200, self._bring_to_front)

    def _bring_to_front(self):
        try:
            self.lift()
        except Exception:
            pass
        try:
            # Temporarily toggle topmost to reliably raise on Windows.
            self.attributes("-topmost", True)
            self.after(150, lambda: self.attributes("-topmost", False))
        except Exception:
            pass
        try:
            self.focus_force()
        except Exception:
            pass

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=16, pady=(16, 12), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(header, text="Media Editors", font=ctk.CTkFont(size=22, weight="bold"))
        title.grid(row=0, column=0, padx=14, pady=(14, 2), sticky="w")
        subtitle = ctk.CTkLabel(
            header,
            text="Open Audio or Video editor directly (no File Tools needed).",
            text_color=("#a7abb3", "#a7abb3"),
        )
        subtitle.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="w")

        quick = ctk.CTkFrame(header, fg_color="transparent")
        quick.grid(row=0, column=1, rowspan=2, padx=14, pady=14, sticky="e")

        ctk.CTkButton(quick, text="Open File…", width=120, command=self._open_any_file).pack(side="left", padx=(0, 10))
        ctk.CTkButton(quick, text="Video Editor", width=120, command=lambda: self._open_video_editor(None)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(quick, text="Audio Editor", width=120, command=lambda: self._open_audio_editor(None)).pack(side="left")

        body = ctk.CTkFrame(self, corner_radius=12)
        body.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.video_card = self._make_card(
            body,
            title="Video Editor",
            desc="Edit videos, images (slideshow), audio lanes and render with presets.",
            primary=("Open Video Editor", lambda: self._open_video_editor(None)),
            secondary=("Import Video / Images…", self._import_video_or_images),
        )
        self.video_card.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="nsew")

        self.audio_card = self._make_card(
            body,
            title="Audio Editor",
            desc="Waveform editing: select range, cut, normalize, fade in/out, export presets.",
            primary=("Open Audio Editor", lambda: self._open_audio_editor(None)),
            secondary=("Import Audio…", self._import_audio),
        )
        self.audio_card.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="nsew")

        # Drop zone (optional, best-effort)
        drop = ctk.CTkFrame(self, corner_radius=12)
        drop.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        drop.grid_columnconfigure(0, weight=1)
        self.drop_hint = ctk.CTkLabel(
            drop,
            text="Tip: drag & drop a media file here to open the right editor (optional).",
            text_color=("#a7abb3", "#a7abb3"),
        )
        self.drop_hint.grid(row=0, column=0, padx=14, pady=10, sticky="w")

    def _make_card(self, parent, *, title: str, desc: str, primary: tuple[str, callable], secondary: tuple[str, callable]):
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=18, pady=(18, 6), sticky="w")
        ctk.CTkLabel(card, text=desc, text_color=("#a7abb3", "#a7abb3"), wraplength=360, justify="left").grid(
            row=1, column=0, padx=18, pady=(0, 16), sticky="w"
        )

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="ew")
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(btns, text=primary[0], height=42, command=primary[1]).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(btns, text=secondary[0], height=42, fg_color="#444", command=secondary[1]).grid(row=0, column=1, padx=(8, 0), sticky="ew")
        return card

    def _open_any_file(self):
        f = filedialog.askopenfilename(
            parent=self,
            title="Open a media file",
            filetypes=[("Media", "*.*")],
        )
        if not f:
            return
        self._open_path(Path(f))

    def _import_audio(self):
        files = filedialog.askopenfilenames(
            parent=self,
            title="Import audio",
            filetypes=[("Audio files", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus"), ("All files", "*.*")],
        )
        if not files:
            return
        self._open_audio_editor(Path(files[0]))

    def _import_video_or_images(self):
        files = filedialog.askopenfilenames(
            parent=self,
            title="Import video/images",
            filetypes=[
                ("Video / Images", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if not files:
            return
        self._open_video_editor(Path(files[0]))

    def _open_path(self, path: Path):
        if _is_audio(path):
            self._open_audio_editor(path)
            return
        if _is_video(path) or _is_image(path):
            self._open_video_editor(path)
            return
        # Default to video editor for unknown media extensions.
        self._open_video_editor(path)

    def _open_video_editor(self, path: Path | None):
        import subprocess
        import sys
        import json

        root = Path(__file__).resolve().parents[1]
        p = str(path) if path else ""
        p_lit = json.dumps(p)
        code = (
            "import sys; from PySide6.QtWidgets import QApplication; "
            "from core.settings_manager import SettingsManager; from core.ai_manager import AIManager; "
            "from gui.video_editor_dialog import VideoEditorDialog; "
            "app=QApplication(sys.argv); s=SettingsManager(); ai=AIManager(s.app_folder, s); "
            f"dlg=VideoEditorDialog(None, ai, initial_file=({p_lit} or None)); "
            "app.setQuitOnLastWindowClosed(True); dlg.show(); sys.exit(app.exec())"
        )
        subprocess.Popen([sys.executable, "-c", code], cwd=str(root))

    def _open_audio_editor(self, path: Path | None):
        from gui.audio_editor_dialog import AudioEditorDialog

        AudioEditorDialog(self._app_root, self.ai_manager, initial_file=path)

    def _setup_dnd(self):
        if not _DND_AVAILABLE:
            return
        try:
            if not hasattr(self, "drop_target_register") or not hasattr(self, "dnd_bind"):
                return
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            return

    def _on_drop(self, event):
        try:
            data = (getattr(event, "data", "") or "").strip()
            if not data:
                return
            # DND strings can be "{path}" or space-separated list.
            if data.startswith("{") and data.endswith("}"):
                data = data[1:-1]
            p = Path(data)
            if p.exists() and p.is_file():
                self._open_path(p)
        except Exception:
            return
