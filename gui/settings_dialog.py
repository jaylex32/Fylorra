"""Settings Dialog - Application settings interface"""

import customtkinter as ctk
from typing import Callable
import sys
from pathlib import Path
from tkinter import filedialog, messagebox
from utils.png_icons import PNGIconLoader
from core.tool_manager import ToolManager


class _SettingsUI:
    """Shared UI/logic for Settings (dialog + embedded view)."""

    def _init_common(self, parent, settings_manager, monitor_manager=None, *, on_close=None, embedded: bool = False):
        self.settings_manager = settings_manager
        self.monitor_manager = monitor_manager
        self.parent = parent
        self.icon_loader = PNGIconLoader()
        self._on_close = on_close or (lambda: None)
        self._embedded = bool(embedded)

        self._setup_ui()

    def _top(self):
        try:
            return self.winfo_toplevel()
        except Exception:
            return self

    def _bring_to_front(self):
        """Bring dialog to front"""
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()

    def _setup_ui(self):
        """Setup dialog UI"""
        # Main container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title with icon
        title_frame = ctk.CTkFrame(container, fg_color="transparent", height=40)
        title_frame.pack(pady=(0, 20), fill="x")
        title_frame.pack_propagate(False)

        # Load settings icon
        settings_icon = self.icon_loader.load_icon("settings", size=(28, 28))

        # Icon positioned absolutely
        if settings_icon:
            icon_label = ctk.CTkLabel(
                title_frame,
                text="",
                image=settings_icon
            )
            icon_label.place(x=305, y=6)

        # Title text
        title = ctk.CTkLabel(
            title_frame,
            text="Settings",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.place(x=340, y=8)

        # Scrollable settings area
        scrollable = ctk.CTkScrollableFrame(
            container,
            fg_color=("gray90", "gray13")
        )
        scrollable.pack(fill="both", expand=True)

        # Appearance section
        self._create_section(scrollable, "Appearance")

        self.theme_var = ctk.StringVar(
            value=self.settings_manager.get_setting("theme", "dark")
        )
        self._create_option_menu(
            scrollable,
            "Theme",
            self.theme_var,
            ["dark", "light", "system"],
            self._on_theme_changed
        )

        self.color_var = ctk.StringVar(
            value=self.settings_manager.get_setting("color_theme", "blue")
        )
        self._create_option_menu(
            scrollable,
            "Color Theme",
            self.color_var,
            ["blue", "green", "dark-blue"],
            self._on_color_changed
        )

        # Notifications section
        self._create_section(scrollable, "Notifications")

        self.notif_enabled_var = ctk.BooleanVar(
            value=self.settings_manager.get_setting("notifications_enabled", True)
        )
        self._create_checkbox(
            scrollable,
            "Enable Windows notifications",
            self.notif_enabled_var
        )

        self.notif_sound_var = ctk.BooleanVar(
            value=self.settings_manager.get_setting("notification_sound", True)
        )
        self._create_checkbox(
            scrollable,
            "Enable notification sound",
            self.notif_sound_var
        )

        # Behavior section
        self._create_section(scrollable, "Behavior")

        self.tray_var = ctk.BooleanVar(
            value=self.settings_manager.get_setting("minimize_to_tray", True)
        )
        self._create_checkbox(
            scrollable,
            "Minimize to system tray when closing",
            self.tray_var
        )

        self.auto_start_var = ctk.BooleanVar(
            value=self.settings_manager.get_setting("auto_start_monitors", True)
        )
        self._create_checkbox(
            scrollable,
            "Auto-start monitors on application launch",
            self.auto_start_var
        )

        # Email Notifications section
        self._create_section(scrollable, "Email Notifications")

        email_info = ctk.CTkLabel(
            scrollable,
            text="Configure SMTP settings for email notifications (optional)",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        email_info.pack(anchor="w", padx=20, pady=(0, 10))

        self._create_entry(
            scrollable,
            "SMTP Server",
            "smtp_server",
            "e.g., smtp.gmail.com",
            self.settings_manager.get_setting("smtp_server", "")
        )

        self._create_entry(
            scrollable,
            "SMTP Port",
            "smtp_port",
            "587",
            str(self.settings_manager.get_setting("smtp_port", 587))
        )

        self._create_entry(
            scrollable,
            "SMTP Username",
            "smtp_username",
            "your-email@example.com",
            self.settings_manager.get_setting("smtp_username", "")
        )

        self._create_entry(
            scrollable,
            "SMTP Password",
            "smtp_password",
            "Your SMTP password",
            self.settings_manager.get_setting("smtp_password", ""),
            show="•"
        )

        self._create_entry(
            scrollable,
            "Sender Email",
            "sender_email",
            "sender@example.com",
            self.settings_manager.get_setting("sender_email", "")
        )

        # Test connection button
        test_btn_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
        test_btn_frame.pack(fill="x", padx=20, pady=(5, 10))

        self.test_smtp_btn = ctk.CTkButton(
            test_btn_frame,
            text="Test SMTP Connection",
            width=160,
            command=self._test_smtp_connection,
            fg_color="#2fa572",
            hover_color="#106a43"
        )
        self.test_smtp_btn.pack(anchor="w")

        # AI Settings section
        self._create_section(scrollable, "AI Features")

        # Check if AI manager is available
        if hasattr(self.parent, 'ai_manager'):
            ai_manager = self.parent.ai_manager
            ai_status = ai_manager.get_status()

            # AI status display
            status_frame = ctk.CTkFrame(scrollable, fg_color=("#e8e8e8", "#2b2b2b"), corner_radius=8)
            status_frame.pack(fill="x", padx=20, pady=(5, 10))

            if ai_status["is_ready"]:
                status_color = "#4CAF50"
                status_text = "✓ AI Model Loaded"
                detail_text = "Qwen3-VL-4B (Q4_K_M) - Ready for use"
            elif ai_status["is_loading"]:
                status_color = "#FF9800"
                status_text = "⏳ AI Model Loading..."
                detail_text = "Please wait..."
            else:
                status_color = "gray"
                status_text = "○ AI Model Not Loaded"
                detail_text = "Click 'Load AI Model' to enable AI features"

            ctk.CTkLabel(
                status_frame,
                text=status_text,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=status_color
            ).pack(anchor="w", padx=15, pady=(10, 5))

            ctk.CTkLabel(
                status_frame,
                text=detail_text,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="gray"
            ).pack(anchor="w", padx=15, pady=(0, 10))

            # AI control buttons
            ai_btn_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
            ai_btn_frame.pack(fill="x", padx=20, pady=(5, 10))

            if not ai_status["is_ready"] and not ai_status["is_loading"]:
                load_ai_btn = ctk.CTkButton(
                    ai_btn_frame,
                    text="🤖 Load AI Model",
                    width=180,
                    height=38,
                    command=self._load_ai_model,
                    fg_color="#9C27B0",
                    hover_color="#7B1FA2",
                    corner_radius=8
                )
                load_ai_btn.pack(side="left", padx=(0, 10))
            elif ai_status["is_ready"]:
                # Reload button for applying new settings
                reload_ai_btn = ctk.CTkButton(
                    ai_btn_frame,
                    text="🔄 Reload AI Model",
                    width=180,
                    height=38,
                    command=self._reload_ai_model,
                    fg_color="#FF9800",
                    hover_color="#F57C00",
                    corner_radius=8
                )
                reload_ai_btn.pack(side="left", padx=(0, 10))

                unload_ai_btn = ctk.CTkButton(
                    ai_btn_frame,
                    text="❌ Unload AI Model",
                    width=180,
                    height=38,
                    command=self._unload_ai_model,
                    fg_color="#F44336",
                    hover_color="#D32F2F",
                    corner_radius=8
                )
                unload_ai_btn.pack(side="left", padx=(0, 10))

            # Performance Settings
            perf_header = ctk.CTkLabel(
                scrollable,
                text="Performance Settings",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
            )
            perf_header.pack(anchor="w", padx=20, pady=(10, 5))

            # Backend selection (llama-cpp vs Transformers)
            self.ai_backend_var = ctk.StringVar(
                value=self.settings_manager.get_setting("ai_backend", "llama_cpp")
            )
            # GPU Layers slider
            self._create_slider_with_label(
                scrollable,
                "GPU Layers (0=CPU only, 35=Full GPU)",
                "ai_gpu_layers",
                0, 35,
                self.settings_manager.get_setting("ai_gpu_layers", 35)
            )

            # Threads slider
            import os
            max_threads = os.cpu_count() or 8
            self._create_slider_with_label(
                scrollable,
                f"CPU Threads (1-{max_threads})",
                "ai_threads",
                1, max_threads,
                self.settings_manager.get_setting("ai_threads", max_threads)
            )

            # Context size dropdown
            self.ai_context_var = ctk.StringVar(
                value=str(self.settings_manager.get_setting("ai_context_size", 2048))
            )
            self._create_option_menu(
                scrollable,
                "Context Size (lower=faster)",
                self.ai_context_var,
                ["512", "1024", "2048", "4096"],
                None
            )

            # Batch size dropdown
            self.ai_batch_var = ctk.StringVar(
                value=str(self.settings_manager.get_setting("ai_batch_size", 512))
            )
            self._create_option_menu(
                scrollable,
                "Batch Size (higher=faster)",
                self.ai_batch_var,
                ["128", "256", "512", "1024"],
                None
            )

            # Image resize dropdown
            self.ai_image_size_var = ctk.StringVar(
                value=str(self.settings_manager.get_setting("ai_image_size", 512))
            )
            self._create_option_menu(
                scrollable,
                "Image Processing Size (lower=faster)",
                self.ai_image_size_var,
                ["256", "384", "512", "768", "1024"],
                None
            )

            # Performance hint
            hint_label = ctk.CTkLabel(
                scrollable,
                text="💡 Tip: Higher GPU layers = faster if you have NVIDIA GPU\n    Lower context/image size = faster processing",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#FF9800",
                justify="left",
                anchor="w"
            )
            hint_label.pack(anchor="w", padx=20, pady=(5, 5))

            # Restart notice
            restart_label = ctk.CTkLabel(
                scrollable,
                text="⚠️ Changes require reloading AI model to take effect",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#F44336",
                justify="left",
                anchor="w"
            )
            restart_label.pack(anchor="w", padx=20, pady=(0, 10))

            # Features description
            features_label = ctk.CTkLabel(
                scrollable,
                text="AI Features:\n• Smart Rename - AI-powered file renaming\n• Auto-Categorize - Organize by visual content\n• Security Scan - Detect sensitive information",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="gray",
                justify="left",
                anchor="w"
            )
            features_label.pack(anchor="w", padx=20, pady=(0, 10))

        # Tools section
        self._create_section(scrollable, "Tools")

        tools_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
        tools_frame.pack(fill="x", padx=20, pady=(5, 10))

        # Analytics button
        analytics_btn = ctk.CTkButton(
            tools_frame,
            text="📊 View Analytics Dashboard",
            width=200,
            height=38,
            command=self._open_analytics,
            fg_color=("#1976D2", "#1565C0"),
            hover_color=("#1565C0", "#0D47A1"),
            corner_radius=8
        )
        analytics_btn.pack(side="left", padx=(0, 10))

        # Export logs button
        export_btn = ctk.CTkButton(
            tools_frame,
            text="📤 Export Activity Logs",
            width=200,
            height=38,
            command=self._export_logs,
            fg_color=("#388E3C", "#2E7D32"),
            hover_color=("#2E7D32", "#1B5E20"),
            corner_radius=8
        )
        export_btn.pack(side="left")

        # External Tools section
        self._create_section(scrollable, "External Tools")
        self._build_external_tools(scrollable)

        # About section
        self._create_section(scrollable, "About")

        about_text = (
            "Fylorra - File Intake Automation\n"
            "Version 1.0.0\n\n"
            "Intelligent automation for your file system"
        )
        about_label = ctk.CTkLabel(
            scrollable,
            text=about_text,
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left"
        )
        about_label.pack(anchor="w", padx=20, pady=10)

        # Buttons
        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))

        reset_btn = ctk.CTkButton(
            button_frame,
            text="Reset to Defaults",
            width=140,
            command=self._reset_settings,
            fg_color="transparent",
            border_width=2
        )
        reset_btn.pack(side="left")

        close_btn = ctk.CTkButton(
            button_frame,
            text="Close",
            width=100,
            command=self._save_and_close,
            fg_color="#2fa572"
        )
        close_btn.pack(side="right")

    def _create_section(self, parent, title: str):
        """Create a section header"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=(15, 5))

        label = ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold")
        )
        label.pack(anchor="w")

    def _build_external_tools(self, parent):
        tools = ToolManager()
        soffice = tools.soffice_path()

        card = ctk.CTkFrame(parent, fg_color=("#e8e8e8", "#2b2b2b"), corner_radius=8)
        card.pack(fill="x", padx=20, pady=(5, 10))

        ok = bool(soffice)
        status_text = "✓ LibreOffice detected" if ok else "○ LibreOffice not configured"
        status_color = "#4CAF50" if ok else "gray"
        detail = soffice or "Office→PDF requires LibreOffice (soffice). Install it or point Fylorra to your soffice binary."

        ctk.CTkLabel(
            card,
            text=status_text,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=status_color,
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self._soffice_path_var = ctk.StringVar(value=detail)
        entry = ctk.CTkEntry(card, textvariable=self._soffice_path_var)
        entry.pack(fill="x", padx=15, pady=(0, 10))

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 10))

        def browse():
            initial = None
            try:
                if soffice:
                    initial = str(Path(soffice).parent)
            except Exception:
                initial = None
            p = filedialog.askopenfilename(
                title="Select LibreOffice soffice",
                initialdir=initial,
                filetypes=[("LibreOffice", "soffice.exe soffice"), ("All files", "*.*")],
            )
            if not p:
                return
            tools.set_soffice(p)
            self._soffice_path_var.set(p)
            messagebox.showinfo("LibreOffice", "LibreOffice path saved. Office→PDF should work now.", parent=self)

        def clear():
            tools.clear_soffice()
            self._soffice_path_var.set("")
            messagebox.showinfo("LibreOffice", "Cleared saved LibreOffice path. Fylorra will auto-detect if installed.", parent=self)

        ctk.CTkButton(btns, text="Browse…", width=140, command=browse).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btns, text="Clear", width=110, command=clear).pack(side="left", padx=(0, 10))
        def download():
            try:
                from gui.libreoffice_download_dialog import LibreOfficeDownloadDialog

                dlg = LibreOfficeDownloadDialog(self)
                self.wait_window(dlg)
            except Exception as e:
                messagebox.showerror("LibreOffice", str(e), parent=self)

        ctk.CTkButton(btns, text="Download LibreOffice", width=180, command=download).pack(side="left")

    def _create_checkbox(self, parent, text: str, variable: ctk.BooleanVar):
        """Create a checkbox option"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=5)

        checkbox = ctk.CTkCheckBox(frame, text=text, variable=variable)
        checkbox.pack(anchor="w")

    def _create_option_menu(self, parent, label: str, variable: ctk.StringVar,
                           values: list, command: Callable = None):
        """Create an option menu"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=5)

        label_widget = ctk.CTkLabel(
            frame,
            text=label + ":",
            font=ctk.CTkFont(size=12)
        )
        label_widget.pack(anchor="w", pady=(0, 5))

        menu = ctk.CTkOptionMenu(
            frame,
            variable=variable,
            values=values,
            command=command
        )
        menu.pack(fill="x")

    def _create_entry(self, parent, label: str, setting_key: str,
                     placeholder: str, default_value: str, show: str = None):
        """Create an entry field for settings"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=5)

        label_widget = ctk.CTkLabel(
            frame,
            text=label + ":",
            font=ctk.CTkFont(size=12)
        )
        label_widget.pack(anchor="w", pady=(0, 5))

        entry = ctk.CTkEntry(
            frame,
            placeholder_text=placeholder,
            show=show
        )
        entry.insert(0, default_value)
        entry.pack(fill="x")

        # Store reference to entry widget using setting_key
        setattr(self, f"{setting_key}_entry", entry)

    def _create_slider_with_label(self, parent, label: str, setting_key: str,
                                  from_: int, to: int, default_value: int):
        """Create a slider with value label"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=5)

        # Header with label and value
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 5))

        label_widget = ctk.CTkLabel(
            header,
            text=label + ":",
            font=ctk.CTkFont(size=12)
        )
        label_widget.pack(side="left")

        value_label = ctk.CTkLabel(
            header,
            text=str(int(default_value)),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4CAF50"
        )
        value_label.pack(side="right")

        # Slider
        slider = ctk.CTkSlider(
            frame,
            from_=from_,
            to=to,
            number_of_steps=to - from_
        )
        slider.set(default_value)
        slider.pack(fill="x")

        # Update value label when slider changes
        def on_slider_change(value):
            value_label.configure(text=str(int(value)))

        slider.configure(command=on_slider_change)

        # Store references
        setattr(self, f"{setting_key}_slider", slider)
        setattr(self, f"{setting_key}_label", value_label)

    def _on_theme_changed(self, value):
        """Handle theme change"""
        ctk.set_appearance_mode(value)
        self.settings_manager.set_setting("theme", value)

    def _on_color_changed(self, value):
        """Handle color theme change"""
        ctk.set_default_color_theme(value)
        self.settings_manager.set_setting("color_theme", value)

    def _test_smtp_connection(self):
        """Test SMTP connection"""
        from tkinter import messagebox
        from utils.email_notifier import EmailNotifier

        # Get current values from entry fields
        smtp_settings = {
            "smtp_server": self.smtp_server_entry.get().strip(),
            "smtp_port": int(self.smtp_port_entry.get().strip()) if self.smtp_port_entry.get().strip().isdigit() else 587,
            "smtp_username": self.smtp_username_entry.get().strip(),
            "smtp_password": self.smtp_password_entry.get().strip(),
            "sender_email": self.sender_email_entry.get().strip()
        }

        if not all([smtp_settings["smtp_server"], smtp_settings["smtp_username"],
                   smtp_settings["smtp_password"], smtp_settings["sender_email"]]):
            messagebox.showwarning(
                "Incomplete Configuration",
                "Please fill in all SMTP fields before testing"
            )
            return

        # Disable button during test
        self.test_smtp_btn.configure(state="disabled", text="Testing...")
        self.update()

        # Test connection
        email_notifier = EmailNotifier(smtp_settings)
        success, message = email_notifier.test_connection()

        # Re-enable button
        self.test_smtp_btn.configure(state="normal", text="Test SMTP Connection")

        # Show result
        if success:
            messagebox.showinfo("Connection Successful", message)
        else:
            messagebox.showerror("Connection Failed", message)

    def _reset_settings(self):
        """Reset settings to defaults"""
        from tkinter import messagebox

        result = messagebox.askyesno(
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?"
        )

        if result:
            self.settings_manager.reset_settings()
            messagebox.showinfo("Settings Reset", "Settings have been reset. Please restart the application.")
            if not getattr(self, "_embedded", False):
                self._on_close()

    def _open_analytics(self):
        """Open analytics dashboard"""
        if self.monitor_manager:
            from gui.analytics_dashboard import AnalyticsDashboard
            AnalyticsDashboard(self.parent, self.monitor_manager.analytics_manager, self.monitor_manager)

    def _export_logs(self):
        """Export activity logs"""
        from tkinter import filedialog, messagebox
        import shutil
        from pathlib import Path

        # Ask user for save location
        file_path = filedialog.asksaveasfilename(
            parent=self._top(),
            title="Export Activity Logs",
            defaultextension=".log",
            filetypes=[("Log Files", "*.log"), ("All Files", "*.*")]
        )

        # Bring dialog back to front
        self._bring_to_front()

        if file_path:
            try:
                # Get log file path from settings manager
                log_file = self.settings_manager.app_folder / "activity.log"

                if log_file.exists():
                    # Copy log file to selected location
                    shutil.copy(log_file, file_path)
                    messagebox.showinfo(
                        "Export Successful",
                        f"Activity logs exported to:\n{file_path}"
                    )
                else:
                    messagebox.showwarning(
                        "No Logs Found",
                        "No activity logs found to export"
                    )
            except Exception as e:
                messagebox.showerror(
                    "Export Failed",
                    f"Failed to export logs:\n{str(e)}"
                )

    def _save_and_close(self):
        """Save settings and close"""
        # Save all settings
        self.settings_manager.set_setting("notifications_enabled", self.notif_enabled_var.get())
        self.settings_manager.set_setting("notification_sound", self.notif_sound_var.get())
        self.settings_manager.set_setting("minimize_to_tray", self.tray_var.get())
        self.settings_manager.set_setting("auto_start_monitors", self.auto_start_var.get())

        # Save SMTP settings
        self.settings_manager.set_setting("smtp_server", self.smtp_server_entry.get().strip())
        smtp_port = self.smtp_port_entry.get().strip()
        self.settings_manager.set_setting("smtp_port", int(smtp_port) if smtp_port.isdigit() else 587)
        self.settings_manager.set_setting("smtp_username", self.smtp_username_entry.get().strip())
        self.settings_manager.set_setting("smtp_password", self.smtp_password_entry.get().strip())
        self.settings_manager.set_setting("sender_email", self.sender_email_entry.get().strip())

        # Save AI performance settings (if they exist)
        if hasattr(self, 'ai_gpu_layers_slider'):
            self.settings_manager.set_setting("ai_gpu_layers", int(self.ai_gpu_layers_slider.get()))
            self.settings_manager.set_setting("ai_threads", int(self.ai_threads_slider.get()))
            self.settings_manager.set_setting("ai_context_size", int(self.ai_context_var.get()))
            self.settings_manager.set_setting("ai_batch_size", int(self.ai_batch_var.get()))
            self.settings_manager.set_setting("ai_image_size", int(self.ai_image_size_var.get()))

        # Save AI backend settings (if present)
        if hasattr(self, 'ai_backend_var'):
            self.settings_manager.set_setting("ai_backend", "llama_cpp")

        if getattr(self, "_embedded", False):
            try:
                messagebox.showinfo("Settings", "Saved.", parent=self._top())
            except Exception:
                pass
            return
        self._on_close()

    def _load_ai_model(self):
        """Load AI model in background"""
        if not hasattr(self.parent, 'ai_manager'):
            return

        ai_manager = self.parent.ai_manager

        # Create loading dialog
        loading_dialog = ctk.CTkToplevel(self)
        loading_dialog.title("Loading AI Model")
        loading_dialog.geometry("450x250")
        loading_dialog.resizable(False, False)

        # Center
        loading_dialog.update_idletasks()
        x = (loading_dialog.winfo_screenwidth() // 2) - 225
        y = (loading_dialog.winfo_screenheight() // 2) - 125
        loading_dialog.geometry(f"450x250+{x}+{y}")

        # Make modal
        loading_dialog.transient(self)
        loading_dialog.grab_set()

        ctk.CTkLabel(
            loading_dialog,
            text="Loading AI Model",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        ).pack(pady=20)

        status_label = ctk.CTkLabel(
            loading_dialog,
            text="Initializing...",
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        status_label.pack(pady=10)

        progress = ctk.CTkProgressBar(loading_dialog, width=410)
        progress.pack(pady=10)
        progress.set(0)

        # Download stats
        downloaded_label = ctk.CTkLabel(
            loading_dialog,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        downloaded_label.pack(pady=5)

        speed_label = ctk.CTkLabel(
            loading_dialog,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        speed_label.pack(pady=5)

        info_label = ctk.CTkLabel(
            loading_dialog,
            text="First run: ~2.5GB download required",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        info_label.pack(pady=10)

        dialog_destroyed = [False]

        def update_progress(message, value, downloaded_str, speed_str):
            if dialog_destroyed[0]:
                return

            try:
                if not loading_dialog.winfo_exists():
                    dialog_destroyed[0] = True
                    return

                status_label.configure(text=message)
                progress.set(value)

                if downloaded_str:
                    downloaded_label.configure(text=downloaded_str)

                if speed_str:
                    speed_label.configure(text=speed_str)

                if value >= 1.0:
                    dialog_destroyed[0] = True
                    loading_dialog.destroy()
                    from tkinter import messagebox
                    messagebox.showinfo(
                        "AI Model Ready",
                        "AI model loaded successfully!\n\nYou can now use AI features on your monitor cards."
                    )
            except Exception:
                dialog_destroyed[0] = True

        def on_close():
            dialog_destroyed[0] = True
            loading_dialog.destroy()

        loading_dialog.protocol("WM_DELETE_WINDOW", on_close)

        # Start loading
        ai_manager.load_model_async(update_progress)

    def _reload_ai_model(self):
        """Reload AI model with new settings"""
        if not hasattr(self.parent, 'ai_manager'):
            return

        ai_manager = self.parent.ai_manager

        from tkinter import messagebox
        result = messagebox.askyesno(
            "Reload AI Model",
            "This will reload the AI model with your new performance settings.\n\nContinue?"
        )

        if not result:
            return

        # Unload first
        if ai_manager.is_ready:
            ai_manager.unload_model()

        # Reload settings from settings manager
        if self.settings_manager:
            ai_manager.n_ctx = self.settings_manager.get_setting("ai_context_size", 2048)
            ai_manager.n_threads = self.settings_manager.get_setting("ai_threads", os.cpu_count())
            ai_manager.n_batch = self.settings_manager.get_setting("ai_batch_size", 512)
            ai_manager.n_gpu_layers = self.settings_manager.get_setting("ai_gpu_layers", 35)
            ai_manager.image_size = self.settings_manager.get_setting("ai_image_size", 512)

        # Reload
        self._load_ai_model()

    def _unload_ai_model(self):
        """Unload AI model to free memory"""
        if not hasattr(self.parent, 'ai_manager'):
            return

        ai_manager = self.parent.ai_manager

        from tkinter import messagebox
        result = messagebox.askyesno(
            "Unload AI Model",
            "This will unload the AI model and free ~2.5GB of RAM.\n\nContinue?"
        )

        if result and ai_manager.is_ready:
            ai_manager.unload_model()
            messagebox.showinfo(
                "AI Model Unloaded",
                "AI model has been unloaded. Memory freed."
            )
            if not getattr(self, "_embedded", False):
                self._on_close()  # Close settings to refresh
            else:
                try:
                    messagebox.showinfo("Settings", "AI settings updated.", parent=self._top())
                except Exception:
                    pass


class SettingsView(_SettingsUI, ctk.CTkFrame):
    """Embeddable Settings view (used in MainWindow)."""

    def __init__(self, parent, settings_manager, monitor_manager=None, *, on_close=None):
        super().__init__(parent, fg_color="transparent")
        self._init_common(parent, settings_manager, monitor_manager=monitor_manager, on_close=on_close, embedded=True)


class SettingsDialog(_SettingsUI, ctk.CTkToplevel):
    """Settings dialog window (kept for compatibility)."""

    def __init__(self, parent, settings_manager, monitor_manager=None):
        super().__init__(parent)

        # Configure window
        self.title("Settings - Fylorra")
        self.geometry("750x650")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (750 // 2)
        y = (self.winfo_screenheight() // 2) - (650 // 2)
        self.geometry(f"750x650+{x}+{y}")

        self._init_common(parent, settings_manager, monitor_manager=monitor_manager, on_close=self.destroy, embedded=False)

        # Bring to front AFTER UI is created
        self.after(10, self._bring_to_front)
