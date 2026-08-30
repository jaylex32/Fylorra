"""
Fylorra - Undo History Dialog
Shows all recent operations that can be undone
"""

import customtkinter as ctk
from pathlib import Path
from typing import Optional
from tkinter import messagebox
from utils.universal_undo import get_undo_manager, UndoTransaction


class UndoHistoryDialog(ctk.CTkToplevel):
    """Dialog showing undo history with ability to undo any transaction"""

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Undo History - Fylorra")
        self.geometry("800x600")
        self.resizable(True, True)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 400
        y = (self.winfo_screenheight() // 2) - 300
        self.geometry(f"800x600+{x}+{y}")

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._setup_ui()
        self._load_history()

    def _setup_ui(self):
        """Create UI elements"""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="⏮️ Undo History",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left")

        refresh_btn = ctk.CTkButton(
            header_frame,
            text="🔄 Refresh",
            command=self._load_history,
            width=100,
            height=32
        )
        refresh_btn.pack(side="right")

        # Statistics
        self.stats_label = ctk.CTkLabel(
            self,
            text="Loading...",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.stats_label.pack(padx=20, pady=(0, 10))

        # Scrollable history list
        self.history_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.history_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Footer buttons
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.pack(fill="x", padx=20, pady=(0, 20))

        close_btn = ctk.CTkButton(
            footer_frame,
            text="Close",
            command=self.destroy,
            width=120,
            height=36
        )
        close_btn.pack(side="right")

    def _load_history(self):
        """Load and display undo history"""
        # Clear existing items
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        # Get undo manager
        undo_manager = get_undo_manager()

        # Get statistics
        stats = undo_manager.get_statistics()
        self.stats_label.configure(
            text=f"📊 Total: {stats['total_transactions']} transactions | "
                 f"✓ Success: {stats['total_success']} operations | "
                 f"⏮️ Undoable: {stats['undoable_transactions']} | "
                 f"📈 Success Rate: {stats['success_rate']:.1f}%"
        )

        # Get recent transactions
        transactions = undo_manager.get_recent_transactions(limit=50)

        if not transactions:
            no_history_label = ctk.CTkLabel(
                self.history_frame,
                text="No undo history found.\n\nFile operations will appear here and can be undone for 30 days.",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            no_history_label.pack(pady=50)
            return

        # Display each transaction
        for trans in transactions:
            self._create_transaction_card(trans)

    def _create_transaction_card(self, trans: UndoTransaction):
        """Create a card for a single transaction"""
        # Determine card color based on status
        if not trans.can_undo:
            bg_color = "gray25"  # Already undone
        elif trans.failed_count > 0:
            bg_color = "#4A2020"  # Had errors
        else:
            bg_color = "gray22"  # Normal

        card = ctk.CTkFrame(self.history_frame, fg_color=bg_color, corner_radius=8)
        card.pack(fill="x", pady=5)

        # Header row
        header_row = ctk.CTkFrame(card, fg_color="transparent")
        header_row.pack(fill="x", padx=15, pady=(12, 5))

        # Transaction icon and description
        icon = self._get_operation_icon(trans.operation_type)
        desc_label = ctk.CTkLabel(
            header_row,
            text=f"{icon} {trans.description}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        desc_label.pack(side="left")

        # Transaction ID
        id_label = ctk.CTkLabel(
            header_row,
            text=f"#{trans.transaction_id}",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        id_label.pack(side="right", padx=10)

        # Details row
        details_row = ctk.CTkFrame(card, fg_color="transparent")
        details_row.pack(fill="x", padx=15, pady=(0, 5))

        timestamp = trans.timestamp[:19].replace('T', ' ')
        details_text = f"🕒 {timestamp}  |  "
        details_text += f"✓ {trans.success_count} success"
        if trans.failed_count > 0:
            details_text += f"  |  ✗ {trans.failed_count} failed"

        details_label = ctk.CTkLabel(
            details_row,
            text=details_text,
            font=ctk.CTkFont(size=10),
            text_color="gray60",
            anchor="w"
        )
        details_label.pack(side="left")

        # Status badge
        if not trans.can_undo:
            status_text = "Already Undone"
            status_color = "gray40"
        elif trans.success_count == 0:
            status_text = "No Changes"
            status_color = "gray40"
        else:
            status_text = "Can Undo"
            status_color = "#4CAF50"

        status_label = ctk.CTkLabel(
            details_row,
            text=status_text,
            font=ctk.CTkFont(size=9),
            text_color=status_color
        )
        status_label.pack(side="right")

        # Undo button
        if trans.can_undo and trans.success_count > 0:
            button_row = ctk.CTkFrame(card, fg_color="transparent")
            button_row.pack(fill="x", padx=15, pady=(5, 12))

            undo_btn = ctk.CTkButton(
                button_row,
                text=f"⏮️ Undo ({trans.success_count} operations)",
                command=lambda t=trans: self._undo_transaction(t),
                width=180,
                height=28,
                fg_color="#FF6B6B",
                hover_color="#ff5252"
            )
            undo_btn.pack(side="right")

        else:
            # Just add padding
            ctk.CTkLabel(card, text="", height=5).pack()

    def _get_operation_icon(self, operation_type: str) -> str:
        """Get emoji icon for operation type"""
        icons = {
            'rename': '✏️',
            'bulk_rename': '✏️',
            'move': '📁',
            'bulk_move': '📁',
            'copy': '📋',
            'delete': '🗑️',
            'categorize': '🏷️',
            'bulk_categorize': '🏷️',
            'create_folder': '📂'
        }
        return icons.get(operation_type, '📄')

    def _undo_transaction(self, trans: UndoTransaction):
        """Undo a specific transaction"""
        # Confirm
        confirm = messagebox.askyesno(
            "Confirm Undo",
            f"Undo this operation?\n\n"
            f"{trans.description}\n"
            f"Transaction #{trans.transaction_id}\n"
            f"Performed: {trans.timestamp[:19]}\n\n"
            f"This will reverse {trans.success_count} operations."
        )

        if not confirm:
            return

        # Perform undo
        undo_manager = get_undo_manager()
        success, message, reversed_count = undo_manager.undo_transaction(trans.transaction_id)

        if success:
            messagebox.showinfo(
                "Undo Complete",
                f"✓ Successfully reversed {reversed_count} operations.\n\n{message}"
            )
            # Reload history
            self._load_history()
        else:
            messagebox.showerror(
                "Undo Failed",
                f"Could not undo operation:\n\n{message}"
            )


def show_undo_history(parent):
    """Show undo history dialog"""
    dialog = UndoHistoryDialog(parent)
    dialog.wait_window()
