"""
Fylorra - Rename Preview Dialog
Shows before/after preview with validation warnings
"""

import customtkinter as ctk
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass


@dataclass
class RenamePreview:
    """Single file rename preview"""
    original_path: Path
    new_name: str  # Without extension
    validation_issues: List[str]
    confidence: float
    is_duplicate: bool
    duplicate_explanation: str


class RenamePreviewDialog(ctk.CTkToplevel):
    """
    Professional rename preview with before/after table
    Shows validation warnings and allows user to confirm/cancel
    """

    def __init__(self, parent, previews: List[RenamePreview],
                 on_confirm: Optional[Callable] = None,
                 on_cancel: Optional[Callable] = None):
        super().__init__(parent)

        self.previews = previews
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.confirmed = False

        self.title(f"Rename Preview - {len(previews)} files")
        self.geometry("900x650")
        self.resizable(True, True)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 450
        y = (self.winfo_screenheight() // 2) - 325
        self.geometry(f"900x650+{x}+{y}")

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._setup_ui()
        self._populate_preview()

    def _setup_ui(self):
        """Create UI elements"""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="📋 Rename Preview",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left")

        info_label = ctk.CTkLabel(
            header_frame,
            text=f"{len(self.previews)} files will be renamed",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        info_label.pack(side="left", padx=20)

        # Warning banner if issues found
        total_issues = sum(len(p.validation_issues) for p in self.previews)
        if total_issues > 0:
            warning_frame = ctk.CTkFrame(self, fg_color="#FF6B6B", corner_radius=8)
            warning_frame.pack(fill="x", padx=20, pady=(0, 10))

            warning_label = ctk.CTkLabel(
                warning_frame,
                text=f"⚠️ {total_issues} validation issues found - review before confirming",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="white"
            )
            warning_label.pack(pady=8)

        # Scrollable preview area
        preview_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        preview_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.preview_container = preview_frame

        # Statistics footer
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=10)

        high_confidence = sum(1 for p in self.previews if p.confidence >= 0.85)
        duplicates = sum(1 for p in self.previews if p.is_duplicate)

        stats_text = f"✓ High Confidence: {high_confidence}  |  "
        stats_text += f"⚠️ Validation Issues: {total_issues}  |  "
        stats_text += f"🔄 Smart Duplicates: {duplicates}"

        stats_label = ctk.CTkLabel(
            stats_frame,
            text=stats_text,
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        stats_label.pack()

        # Buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.cancel_btn = ctk.CTkButton(
            button_frame,
            text="✗ Cancel",
            command=self._on_cancel,
            width=140,
            height=40,
            fg_color="gray40",
            hover_color="gray30"
        )
        self.cancel_btn.pack(side="right", padx=5)

        self.confirm_btn = ctk.CTkButton(
            button_frame,
            text="✓ Confirm Rename",
            command=self._on_confirm,
            width=140,
            height=40,
            fg_color="#4CAF50",
            hover_color="#45a049"
        )
        self.confirm_btn.pack(side="right", padx=5)

        # Undo info
        undo_label = ctk.CTkLabel(
            button_frame,
            text="💡 Tip: You can undo this rename for 30 days",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        undo_label.pack(side="left")

    def _populate_preview(self):
        """Populate preview table with rename operations"""
        # Header row
        header_frame = ctk.CTkFrame(self.preview_container, fg_color="gray20", height=40)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)

        headers = [
            ("Original Name", 0.40),
            ("→", 0.05),
            ("New Name", 0.40),
            ("Status", 0.15)
        ]

        for text, width in headers:
            label = ctk.CTkLabel(
                header_frame,
                text=text,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            label.place(relx=sum(h[1] for h in headers[:headers.index((text, width))]),
                       rely=0.5, anchor="w", relwidth=width)

        # Preview rows
        for idx, preview in enumerate(self.previews):
            self._create_preview_row(preview, idx)

    def _create_preview_row(self, preview: RenamePreview, index: int):
        """Create a single preview row"""
        # Determine row color based on issues
        if preview.validation_issues:
            row_color = "#4A2020"  # Red tint for issues
        elif preview.is_duplicate:
            row_color = "#3A3A20"  # Yellow tint for duplicates
        elif preview.confidence >= 0.85:
            row_color = "#204A20"  # Green tint for high confidence
        else:
            row_color = "gray25" if index % 2 == 0 else "gray22"

        row_frame = ctk.CTkFrame(self.preview_container, fg_color=row_color)
        row_frame.pack(fill="x", pady=2)

        # Original name
        original_label = ctk.CTkLabel(
            row_frame,
            text=preview.original_path.name,
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        original_label.place(relx=0, rely=0.5, anchor="w", relwidth=0.40)

        # Arrow
        arrow_label = ctk.CTkLabel(
            row_frame,
            text="→",
            font=ctk.CTkFont(size=14)
        )
        arrow_label.place(relx=0.40, rely=0.5, anchor="w", relwidth=0.05)

        # New name
        new_name_full = f"{preview.new_name}{preview.original_path.suffix}"
        new_label = ctk.CTkLabel(
            row_frame,
            text=new_name_full,
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w"
        )
        new_label.place(relx=0.45, rely=0.5, anchor="w", relwidth=0.40)

        # Status indicator
        if preview.validation_issues:
            status_text = f"⚠️ {len(preview.validation_issues)} issues"
            status_color = "#FF6B6B"
        elif preview.is_duplicate:
            status_text = "🔄 Smart dup"
            status_color = "#FFB84D"
        elif preview.confidence >= 0.85:
            status_text = f"✓ {preview.confidence:.0%}"
            status_color = "#4CAF50"
        else:
            status_text = f"~ {preview.confidence:.0%}"
            status_color = "gray"

        status_label = ctk.CTkLabel(
            row_frame,
            text=status_text,
            font=ctk.CTkFont(size=10),
            text_color=status_color
        )
        status_label.place(relx=0.85, rely=0.5, anchor="w", relwidth=0.15)

        # Expandable details if there are issues or duplicates
        if preview.validation_issues or preview.is_duplicate:
            row_frame.configure(height=60)

            details_text = ""
            if preview.validation_issues:
                details_text = "• " + "\n• ".join(preview.validation_issues[:2])
            elif preview.duplicate_explanation:
                details_text = f"• {preview.duplicate_explanation}"

            details_label = ctk.CTkLabel(
                row_frame,
                text=details_text,
                font=ctk.CTkFont(size=9),
                text_color="gray60",
                anchor="w",
                justify="left"
            )
            details_label.place(relx=0, rely=0.7, anchor="w", relwidth=0.95, x=5)
        else:
            row_frame.configure(height=35)

    def _on_confirm(self):
        """User confirmed rename"""
        self.confirmed = True
        if self.on_confirm:
            self.on_confirm()
        self.destroy()

    def _on_cancel(self):
        """User cancelled rename"""
        self.confirmed = False
        if self.on_cancel:
            self.on_cancel()
        self.destroy()

    def wait_for_response(self) -> bool:
        """
        Wait for user to confirm or cancel

        Returns:
            True if confirmed, False if cancelled
        """
        self.wait_window()
        return self.confirmed


def show_rename_preview(parent, previews: List[RenamePreview]) -> bool:
    """
    Show rename preview dialog and wait for user response

    Args:
        parent: Parent window
        previews: List of rename previews

    Returns:
        True if user confirmed, False if cancelled
    """
    dialog = RenamePreviewDialog(parent, previews)
    return dialog.wait_for_response()
