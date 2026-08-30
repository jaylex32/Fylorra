"""
Fylorra - AI Security Scanner Dialog
Detects sensitive information in files
"""

import customtkinter as ctk
from pathlib import Path
from typing import List, Dict
import threading
from utils.png_icons import PNGIconLoader


class AISecurityScanDialog(ctk.CTkToplevel):
    """Dialog for scanning files for sensitive content"""

    def __init__(self, parent, ai_manager, ai_categorizer, folder_path: Path):
        super().__init__(parent)

        self.ai_manager = ai_manager
        self.ai_categorizer = ai_categorizer
        self.folder_path = folder_path
        self.icon_loader = PNGIconLoader()

        self.sensitive_files: List[Dict] = []
        self.processing = False
        self.cancelled = False

        self.title("AI Security Scanner - Deep Analysis")
        self.geometry("700x600")
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 350
        y = (self.winfo_screenheight() // 2) - 300
        self.geometry(f"700x600+{x}+{y}")

        self._create_ui()

        # Start scanning
        self.after(100, self._start_scanning)

    def _create_ui(self):
        """Create the dialog UI"""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        header_frame.pack_propagate(False)

        ai_icon = self.icon_loader.load_icon("analytics", size=(32, 32))
        icon_label = ctk.CTkLabel(header_frame, image=ai_icon, text="")
        icon_label.image = ai_icon
        icon_label.place(x=0, y=9)

        title = ctk.CTkLabel(
            header_frame,
            text="AI Vision Security Scan",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        )
        title.place(x=40, y=10)

        # Subtitle
        self.subtitle = ctk.CTkLabel(
            self,
            text=f"Using AI vision to detect sensitive info (20-60s per image)...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray"
        )
        self.subtitle.pack(pady=(0, 10))

        # Progress
        self.progress = ctk.CTkProgressBar(self, width=660)
        self.progress.pack(padx=20, pady=(0, 20))
        self.progress.set(0)

        # Results frame
        self.results_frame = ctk.CTkScrollableFrame(self, width=660, height=400)
        self.results_frame.pack(padx=20, pady=(0, 20), fill="both", expand=True)

        # Close button
        self.close_btn = ctk.CTkButton(
            self,
            text="Close",
            width=100,
            command=self._close,
            state="disabled"
        )
        self.close_btn.pack(pady=(0, 20))

    def _start_scanning(self):
        """Start scanning in background"""
        self.processing = True
        thread = threading.Thread(target=self._scan_files, daemon=True)
        thread.start()

    def _scan_files(self):
        """Scan files for sensitive content using AI vision"""
        def progress_callback(message, progress, current, total):
            # Don't update if dialog was closed
            if self.cancelled or not self.winfo_exists():
                return
            try:
                self.after(0, lambda: self._update_progress(message, progress, current, total))
            except Exception:
                pass  # Dialog closed

        # Scan files (AI vision - slow but necessary for security)
        self.sensitive_files = self.ai_categorizer.scan_for_sensitive_files(
            self.folder_path,
            progress_callback=progress_callback
        )

        # Show results only if dialog still exists
        if not self.cancelled and self.winfo_exists():
            self.after(0, self._show_results)

    def _update_progress(self, message: str, progress: float, current: int, total: int):
        """Update progress bar - safe from threading errors"""
        if self.cancelled or not self.winfo_exists():
            return
        try:
            self.subtitle.configure(text=f"{message} ({current}/{total})")
            self.progress.set(progress)
        except Exception:
            pass  # Dialog was closed

    def _show_results(self):
        """Display scan results"""
        self.processing = False
        self.subtitle.configure(text="Scan complete")
        self.progress.set(1.0)

        if not self.sensitive_files:
            # No sensitive files found
            safe_icon = ctk.CTkLabel(
                self.results_frame,
                text="✓",
                font=ctk.CTkFont(family="Segoe UI", size=72),
                text_color="#4CAF50"
            )
            safe_icon.pack(pady=30)

            safe_label = ctk.CTkLabel(
                self.results_frame,
                text="No sensitive information detected",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color="#4CAF50"
            )
            safe_label.pack(pady=10)

            desc_label = ctk.CTkLabel(
                self.results_frame,
                text="All scanned files appear safe.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="gray"
            )
            desc_label.pack()

        else:
            # Sensitive files found - show warning
            warning_icon = ctk.CTkLabel(
                self.results_frame,
                text="⚠",
                font=ctk.CTkFont(family="Segoe UI", size=48),
                text_color="#FF9800"
            )
            warning_icon.pack(pady=20)

            warning_label = ctk.CTkLabel(
                self.results_frame,
                text=f"Found {len(self.sensitive_files)} file(s) with potential sensitive information",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color="#FF9800"
            )
            warning_label.pack(pady=10)

            # List sensitive files
            for item in self.sensitive_files:
                file_frame = ctk.CTkFrame(self.results_frame, fg_color="#2b2b2b", corner_radius=8)
                file_frame.pack(fill="x", pady=5, padx=10)

                file_label = ctk.CTkLabel(
                    file_frame,
                    text=f"📄 {item['file'].name}",
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                    anchor="w"
                )
                file_label.pack(anchor="w", padx=10, pady=(10, 5))

                reason_label = ctk.CTkLabel(
                    file_frame,
                    text=f"Reason: {item['reason']}",
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="gray",
                    anchor="w"
                )
                reason_label.pack(anchor="w", padx=10, pady=(0, 10))

        # Enable close button
        self.close_btn.configure(state="normal")

    def _close(self):
        """Close dialog"""
        self.cancelled = True
        self.destroy()
