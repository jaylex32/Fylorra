"""Add FTP Monitor Dialog - Dialog for adding FTP server monitors"""

import customtkinter as ctk
from typing import Callable, Dict
from utils.png_icons import PNGIconLoader


class AddFTPDialog(ctk.CTkToplevel):
    """Dialog for adding FTP monitor"""

    def __init__(self, parent, callback: Callable):
        super().__init__(parent)

        self.callback = callback
        self.icon_loader = PNGIconLoader()

        # Configure window
        self.title("Add FTP Monitor")
        self.geometry("600x550")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._setup_ui()

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.winfo_screenheight() // 2) - (550 // 2)
        self.geometry(f"600x550+{x}+{y}")

    def _setup_ui(self):
        """Setup dialog UI"""
        # Main container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title with icon
        title_frame = ctk.CTkFrame(container, fg_color="transparent", height=40)
        title_frame.pack(pady=(0, 10), fill="x")
        title_frame.pack_propagate(False)

        # Load FTP icon
        ftp_icon = self.icon_loader.load_icon("ftp", size=(28, 28))

        # Icon positioned absolutely
        if ftp_icon:
            icon_label = ctk.CTkLabel(
                title_frame,
                text="",
                image=ftp_icon
            )
            icon_label.place(x=170, y=6)

        # Title text
        title = ctk.CTkLabel(
            title_frame,
            text="Add FTP Monitor",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.place(x=205, y=8)

        # Info message
        info = ctk.CTkLabel(
            container,
            text="Monitor FTP servers for file changes (polling-based)",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info.pack(pady=(0, 15))

        # FTP Settings
        settings_frame = ctk.CTkFrame(container, fg_color=("gray90", "gray13"))
        settings_frame.pack(fill="both", expand=True, pady=10)
        settings_frame.pack_propagate(False)

        inner = ctk.CTkFrame(settings_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        # Host
        self._create_field(inner, "FTP Host:", "ftp.example.com")
        self.host_entry = self.last_entry

        # Port
        port_frame = ctk.CTkFrame(inner, fg_color="transparent")
        port_frame.pack(fill="x", pady=5)

        port_label = ctk.CTkLabel(
            port_frame,
            text="Port:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        port_label.pack(side="left", padx=(0, 10))

        self.port_entry = ctk.CTkEntry(port_frame, width=100)
        self.port_entry.insert(0, "21")
        self.port_entry.pack(side="left")

        # Use TLS
        self.tls_var = ctk.BooleanVar(value=False)
        tls_cb = ctk.CTkCheckBox(
            port_frame,
            text="Use TLS/SSL (FTPS)",
            variable=self.tls_var
        )
        tls_cb.pack(side="left", padx=20)

        # Username
        self._create_field(inner, "Username:", "username")
        self.username_entry = self.last_entry

        # Password
        password_frame = ctk.CTkFrame(inner, fg_color="transparent")
        password_frame.pack(fill="x", pady=5)

        password_label = ctk.CTkLabel(
            password_frame,
            text="Password:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        password_label.pack(anchor="w")

        self.password_entry = ctk.CTkEntry(
            password_frame,
            placeholder_text="password",
            show="*"
        )
        self.password_entry.pack(fill="x", pady=(5, 0))

        # Remote path
        self._create_field(inner, "Remote Path:", "/path/to/monitor")
        self.path_entry = self.last_entry

        # Poll interval
        poll_frame = ctk.CTkFrame(inner, fg_color="transparent")
        poll_frame.pack(fill="x", pady=5)

        poll_label = ctk.CTkLabel(
            poll_frame,
            text="Poll Interval (seconds):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        poll_label.pack(side="left", padx=(0, 10))

        self.poll_entry = ctk.CTkEntry(poll_frame, width=100)
        self.poll_entry.insert(0, "30")
        self.poll_entry.pack(side="left")

        poll_info = ctk.CTkLabel(
            poll_frame,
            text="(How often to check for changes)",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        poll_info.pack(side="left", padx=10)

        # Auto-start
        self.auto_start_var = ctk.BooleanVar(value=True)
        auto_start_cb = ctk.CTkCheckBox(
            inner,
            text="Start monitoring immediately",
            variable=self.auto_start_var
        )
        auto_start_cb.pack(anchor="w", pady=10)

        # Buttons
        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))

        test_btn = ctk.CTkButton(
            button_frame,
            text="Test Connection",
            width=130,
            command=self._test_connection,
            fg_color="transparent",
            border_width=2
        )
        test_btn.pack(side="left")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            command=self.destroy,
            fg_color="transparent",
            border_width=2
        )
        cancel_btn.pack(side="right", padx=5)

        add_btn = ctk.CTkButton(
            button_frame,
            text="Add Monitor",
            width=120,
            command=self._add_monitor,
            fg_color="#2fa572",
            hover_color="#106a43"
        )
        add_btn.pack(side="right", padx=5)

    def _create_field(self, parent, label: str, placeholder: str):
        """Create a labeled entry field"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=5)

        label_widget = ctk.CTkLabel(
            frame,
            text=label,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        label_widget.pack(anchor="w")

        entry = ctk.CTkEntry(frame, placeholder_text=placeholder)
        entry.pack(fill="x", pady=(5, 0))

        self.last_entry = entry

    def _test_connection(self):
        """Test FTP connection"""
        from tkinter import messagebox
        import ftplib

        host = self.host_entry.get().strip()
        port = self.port_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        use_tls = self.tls_var.get()

        if not all([host, port, username, password]):
            messagebox.showerror("Error", "Please fill in all required fields")
            return

        try:
            port_num = int(port)
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return
        if port_num < 1 or port_num > 65535:
            messagebox.showerror("Error", "Port must be between 1 and 65535")
            return

        try:
            if use_tls:
                ftp = ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()

            ftp.connect(host, port_num, timeout=10)
            ftp.login(username, password)

            if use_tls:
                ftp.prot_p()

            ftp.quit()

            messagebox.showinfo("Success", "Connection successful!")

        except Exception as e:
            messagebox.showerror("Connection Failed", f"Failed to connect:\n{str(e)}")

    def _add_monitor(self):
        """Add the FTP monitor"""
        from tkinter import messagebox

        host = self.host_entry.get().strip()
        port = self.port_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        remote_path = self.path_entry.get().strip()
        poll_interval = self.poll_entry.get().strip()

        # Validation
        if not all([host, port, username, password, remote_path]):
            messagebox.showerror("Error", "Please fill in all required fields")
            return

        try:
            port_num = int(port)
            poll_num = int(poll_interval)
        except ValueError:
            messagebox.showerror("Error", "Port and poll interval must be numbers")
            return
        if port_num < 1 or port_num > 65535:
            messagebox.showerror("Error", "Port must be between 1 and 65535")
            return
        if poll_num < 5:
            messagebox.showerror("Error", "Poll interval must be at least 5 seconds")
            return
        if "\r" in remote_path or "\n" in remote_path:
            messagebox.showerror("Error", "Remote path cannot contain line breaks")
            return
        remote_parts = [p for p in remote_path.replace("\\", "/").split("/") if p]
        if any(p in (".", "..") for p in remote_parts):
            messagebox.showerror("Error", "Remote path cannot contain . or .. segments")
            return

        # Create monitor data
        monitor_data = {
            "type": "ftp",
            "host": host,
            "port": port_num,
            "username": username,
            "password": password,
            "remote_path": remote_path,
            "poll_interval": poll_num,
            "use_tls": self.tls_var.get(),
            "auto_start": self.auto_start_var.get()
        }

        self.callback(monitor_data)
        self.destroy()
