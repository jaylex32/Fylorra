"""
Fylorra - AI Model Loading Dialog
Shows progress while downloading and loading AI model
"""

import customtkinter as ctk
import threading
from typing import Optional


class AILoadingDialog(ctk.CTkToplevel):
    """Dialog for AI model download and loading progress"""

    def __init__(self, parent, ai_manager):
        super().__init__(parent)

        self.ai_manager = ai_manager
        self.loading_complete = False

        self.title("Loading AI Model")
        self.geometry("600x300")
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 300
        y = (self.winfo_screenheight() // 2) - 150
        self.geometry(f"600x300+{x}+{y}")

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._create_ui()

        # Start loading
        self.after(100, self._start_loading)

    def _create_ui(self):
        """Create the dialog UI"""
        # Title
        title = ctk.CTkLabel(
            self,
            text="Preparing AI Model",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        )
        title.pack(pady=(30, 10))

        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="Initializing...",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="gray"
        )
        self.status_label.pack(pady=(0, 20))

        # Progress bar
        self.progress = ctk.CTkProgressBar(self, width=500)
        self.progress.pack(pady=20)
        self.progress.set(0)

        # Details label
        self.details_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        self.details_label.pack(pady=10)

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            self,
            text="Cancel",
            width=100,
            command=self._close,
            fg_color="gray"
        )
        self.cancel_btn.pack(pady=20)

    def _start_loading(self):
        """Start AI model loading in background"""
        thread = threading.Thread(target=self._load_model, daemon=True)
        thread.start()

    def _load_model(self):
        """Load AI model with progress updates"""
        def progress_callback(message, progress, downloaded, speed):
            if self.winfo_exists():
                try:
                    self.after(0, lambda: self._update_progress(message, progress, downloaded, speed))
                except:
                    pass

        try:
            self.ai_manager.load_model(progress_callback)

            if self.winfo_exists():
                self.after(0, self._loading_complete)

        except Exception as e:
            if self.winfo_exists():
                self.after(0, lambda: self._show_error(str(e)))

    def _update_progress(self, message: str, progress: float, downloaded: str, speed: str):
        """Update progress display"""
        if not self.winfo_exists():
            return

        try:
            # Check if widgets still exist before updating
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.status_label.configure(text=message)
            if hasattr(self, 'progress') and self.progress.winfo_exists():
                self.progress.set(progress)
            if hasattr(self, 'details_label') and self.details_label.winfo_exists():
                if downloaded and speed:
                    self.details_label.configure(text=f"{downloaded} • {speed}")
                elif downloaded:
                    self.details_label.configure(text=downloaded)
        except Exception:
            pass

    def _loading_complete(self):
        """Called when loading is complete"""
        if not self.winfo_exists():
            return

        try:
            self.loading_complete = True
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.status_label.configure(text="AI model loaded successfully!")
            if hasattr(self, 'progress') and self.progress.winfo_exists():
                self.progress.set(1.0)
            if hasattr(self, 'details_label') and self.details_label.winfo_exists():
                self.details_label.configure(text="Ready to use")

            # Auto-close after 1 second
            self.after(1000, self._safe_destroy)
        except Exception:
            self._safe_destroy()

    def _show_error(self, error_msg: str):
        """Show error message"""
        if not self.winfo_exists():
            return

        try:
            if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.status_label.configure(text="Failed to load AI model")
            if hasattr(self, 'details_label') and self.details_label.winfo_exists():
                self.details_label.configure(text=error_msg, text_color="red")
            if hasattr(self, 'cancel_btn') and self.cancel_btn.winfo_exists():
                self.cancel_btn.configure(text="Close")
        except Exception:
            pass

    def _safe_destroy(self):
        """Safely destroy dialog"""
        try:
            if self.winfo_exists():
                self.destroy()
        except Exception:
            pass

    def _close(self):
        """Close dialog"""
        self._safe_destroy()
