"""
Fylorra - LibreOffice Download Dialog
Downloads the LibreOffice installer with progress and offers to run it.
"""

from __future__ import annotations

import platform
import subprocess
import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from core.libreoffice_downloader import build_download_url, download_file, get_latest_stable_version


class LibreOfficeDownloadDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self._cancel = threading.Event()
        self._download_path: Path | None = None

        self.title("Download LibreOffice")
        self.geometry("620x320")
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()

        self._create_ui()
        self.after(150, self._start)

    def _create_ui(self):
        ctk.CTkLabel(self, text="Download LibreOffice", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(26, 8))
        self.status = ctk.CTkLabel(self, text="Preparing…", text_color="gray")
        self.status.pack(pady=(0, 14))

        self.progress = ctk.CTkProgressBar(self, width=520)
        self.progress.pack(pady=(0, 8))
        self.progress.set(0.0)

        self.details = ctk.CTkLabel(self, text="", text_color="gray")
        self.details.pack(pady=(0, 14))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(10, 0))

        self.cancel_btn = ctk.CTkButton(btns, text="Cancel", width=120, fg_color="gray", command=self._on_cancel)
        self.cancel_btn.pack(side="left", padx=(0, 10))

        self.open_btn = ctk.CTkButton(btns, text="Open File", width=120, state="disabled", command=self._open_file)
        self.open_btn.pack(side="left", padx=(0, 10))

        self.run_btn = ctk.CTkButton(btns, text="Run Installer", width=140, state="disabled", command=self._run_installer)
        self.run_btn.pack(side="left")

    def _on_cancel(self):
        self._cancel.set()
        try:
            self.cancel_btn.configure(state="disabled")
            self.status.configure(text="Cancelling…")
        except Exception:
            pass

    def _start(self):
        t = threading.Thread(target=self._download, daemon=True)
        t.start()

    def _download(self):
        ver = get_latest_stable_version()
        if not ver:
            self.after(0, lambda: self._fail("Failed to find the latest LibreOffice version."))
            return

        sys_plat = platform.system().lower()
        arch = "x86_64"
        if platform.machine().lower() in {"amd64", "x86_64"}:
            arch = "x86_64"
        elif platform.machine().lower() in {"x86", "i386", "i686"}:
            arch = "x86"

        plat = "windows" if "windows" in sys_plat else "macos" if "darwin" in sys_plat else "linux"
        info = build_download_url(ver, platform=plat, arch=("x64" if arch == "x86_64" else "x86"))
        if not info:
            self.after(0, lambda: self._fail("Automatic download is not available for this platform."))
            return

        url, filename = info
        self.after(0, lambda: self.status.configure(text=f"Downloading LibreOffice {ver}…"))

        out_dir = Path.home() / ".fylorra" / "tools" / "libreoffice"
        dest = out_dir / filename
        self._download_path = dest

        def progress_cb(frac, downloaded, total, speed_bps):
            def ui():
                self.progress.set(frac)
                if total:
                    mb = downloaded / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    sp = speed_bps / (1024 * 1024)
                    self.details.configure(text=f"{mb:.1f} / {mb_t:.1f} MB • {sp:.1f} MB/s")
                else:
                    mb = downloaded / (1024 * 1024)
                    sp = speed_bps / (1024 * 1024)
                    self.details.configure(text=f"{mb:.1f} MB • {sp:.1f} MB/s")

            self.after(0, ui)

        res = download_file(url, dest, cancel_event=self._cancel, progress_cb=progress_cb)
        if not res.ok:
            self.after(0, lambda: self._fail(res.message))
            return

        self.after(0, lambda: self._done(dest))

    def _done(self, path: Path):
        self.progress.set(1.0)
        self.status.configure(text="Download complete.")
        self.details.configure(text=str(path))
        self.open_btn.configure(state="normal")
        # Run installer button only makes sense on Windows
        self.run_btn.configure(state="normal")

    def _fail(self, msg: str):
        self.status.configure(text="Download failed.")
        self.details.configure(text=msg)
        self.open_btn.configure(state="disabled")
        self.run_btn.configure(state="disabled")
        messagebox.showerror("LibreOffice Download", msg, parent=self)

    def _open_file(self):
        if not self._download_path:
            return
        try:
            import os

            os.startfile(str(self._download_path))
        except Exception:
            pass

    def _run_installer(self):
        if not self._download_path:
            return
        p = self._download_path
        if platform.system().lower().startswith("win"):
            try:
                subprocess.Popen(["msiexec", "/i", str(p)])
            except Exception as e:
                messagebox.showerror("LibreOffice", str(e), parent=self)
        else:
            self._open_file()

