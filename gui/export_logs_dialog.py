"""Export Logs Dialog - Dialog for exporting activity logs"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
import os


class ExportLogsDialog(ctk.CTkToplevel):
    """Dialog for exporting logs"""

    def __init__(self, parent, logger):
        super().__init__(parent)

        self.logger = logger

        # Configure window
        self.title("Export Activity Logs")
        self.geometry("600x500")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._setup_ui()

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.winfo_screenheight() // 2) - (500 // 2)
        self.geometry(f"600x500+{x}+{y}")

    def _setup_ui(self):
        """Setup dialog UI"""
        # Main container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title = ctk.CTkLabel(
            container,
            text="📊 Export Activity Logs",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(0, 10))

        # Info
        info_text = (
            f"Total log entries: {len(self.logger.activity_buffer)}\n"
            f"Log folder: {self.logger.get_log_folder()}"
        )
        info = ctk.CTkLabel(
            container,
            text=info_text,
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info.pack(pady=(0, 20))

        # Export options frame
        options_frame = ctk.CTkFrame(container, fg_color=("gray90", "gray13"))
        options_frame.pack(fill="both", expand=True)

        # Format selection
        format_label = ctk.CTkLabel(
            options_frame,
            text="Export Format:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        format_label.pack(anchor="w", padx=20, pady=(20, 10))

        # Format buttons
        self.format_var = ctk.StringVar(value="text")

        formats = [
            ("text", "📄 Text File (.txt)", "Human-readable text format"),
            ("json", "🔧 JSON (.json)", "Machine-readable JSON format"),
            ("csv", "📊 CSV (.csv)", "Spreadsheet-compatible CSV format")
        ]

        for value, label, description in formats:
            radio_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
            radio_frame.pack(fill="x", padx=20, pady=5)

            radio = ctk.CTkRadioButton(
                radio_frame,
                text=label,
                variable=self.format_var,
                value=value,
                font=ctk.CTkFont(size=12)
            )
            radio.pack(anchor="w")

            desc_label = ctk.CTkLabel(
                radio_frame,
                text=description,
                font=ctk.CTkFont(size=10),
                text_color="gray"
            )
            desc_label.pack(anchor="w", padx=30)

        # Quick actions
        quick_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        quick_frame.pack(fill="x", padx=20, pady=(20, 10))

        quick_label = ctk.CTkLabel(
            quick_frame,
            text="Quick Actions:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        quick_label.pack(anchor="w", pady=(0, 10))

        open_folder_btn = ctk.CTkButton(
            quick_frame,
            text="📂 Open Log Folder",
            command=self._open_log_folder,
            fg_color="transparent",
            border_width=2
        )
        open_folder_btn.pack(fill="x", pady=2)

        clear_old_btn = ctk.CTkButton(
            quick_frame,
            text="🗑️ Clear Old Logs (30+ days)",
            command=self._clear_old_logs,
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "gray90")
        )
        clear_old_btn.pack(fill="x", pady=2)

        # Buttons
        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))

        close_btn = ctk.CTkButton(
            button_frame,
            text="Close",
            width=100,
            command=self.destroy,
            fg_color="transparent",
            border_width=2
        )
        close_btn.pack(side="right", padx=5)

        export_btn = ctk.CTkButton(
            button_frame,
            text="Export Logs",
            width=120,
            command=self._export,
            fg_color="#2fa572",
            hover_color="#106a43"
        )
        export_btn.pack(side="right", padx=5)

    def _export(self):
        """Export logs in selected format"""
        format_type = self.format_var.get()

        # File dialog
        file_types = {
            "text": [("Text files", "*.txt")],
            "json": [("JSON files", "*.json")],
            "csv": [("CSV files", "*.csv")]
        }

        extensions = {
            "text": ".txt",
            "json": ".json",
            "csv": ".csv"
        }

        default_name = f"fylorra_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extensions[format_type]}"

        file_path = filedialog.asksaveasfilename(
            title="Export Logs",
            defaultextension=extensions[format_type],
            filetypes=file_types[format_type],
            initialfile=default_name
        )

        if not file_path:
            return

        # Export based on format
        try:
            if format_type == "text":
                success = self.logger.export_logs_text(file_path)
            elif format_type == "json":
                success = self.logger.export_logs_json(file_path)
            elif format_type == "csv":
                success = self.logger.export_logs_csv(file_path)
            else:
                success = False

            if success:
                result = messagebox.askyesno(
                    "Export Successful",
                    f"Logs exported successfully to:\n{file_path}\n\nOpen the file?",
                    icon='info'
                )

                if result:
                    os.startfile(file_path)

                self.destroy()
            else:
                messagebox.showerror(
                    "Export Failed",
                    "Failed to export logs. Check the console for errors."
                )

        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting logs:\n{str(e)}")

    def _open_log_folder(self):
        """Open the log folder in Windows Explorer"""
        try:
            log_folder = self.logger.get_log_folder()
            os.startfile(log_folder)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open log folder:\n{str(e)}")

    def _clear_old_logs(self):
        """Clear old log files"""
        result = messagebox.askyesno(
            "Clear Old Logs",
            "This will delete log files older than 30 days.\n\nContinue?",
            icon='warning'
        )

        if result:
            try:
                self.logger.clear_old_logs(days_to_keep=30)
                messagebox.showinfo("Success", "Old log files cleared successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear old logs:\n{str(e)}")
