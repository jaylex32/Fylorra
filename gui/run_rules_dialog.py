"""
Fylorra - Run Rules Now Dialog
Applies automation rules to existing files immediately
"""

import customtkinter as ctk
from pathlib import Path
from typing import List, Dict
import threading
import logging

logger = logging.getLogger(__name__)


class RunRulesDialog(ctk.CTkToplevel):
    """Dialog for running rules on existing files"""

    def __init__(self, parent, monitor, folder_path: Path, rules: List[Dict]):
        super().__init__(parent)

        self.monitor = monitor
        self.folder_path = folder_path
        self.rules = rules
        self.cancelled = False
        self.processed_count = 0
        self.success_count = 0

        self.title("Running Rules on Existing Files")
        self.geometry("600x350")
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 300
        y = (self.winfo_screenheight() // 2) - 175
        self.geometry(f"600x350+{x}+{y}")

        # Make modal
        self.transient(parent)
        self.grab_set()

        self._create_ui()

        # Start processing
        self.after(100, self._start_processing)

    def _create_ui(self):
        """Create the dialog UI"""
        # Title
        title = ctk.CTkLabel(
            self,
            text="Running Rules Now",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold")
        )
        title.pack(pady=(30, 10))

        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="Scanning folder...",
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

        # Results label
        self.results_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#4CAF50"
        )
        self.results_label.pack(pady=10)

        # Close button
        self.close_btn = ctk.CTkButton(
            self,
            text="Cancel",
            width=100,
            command=self._close,
            fg_color="gray"
        )
        self.close_btn.pack(pady=20)

    def _start_processing(self):
        """Start processing in background"""
        thread = threading.Thread(target=self._process_files, daemon=True)
        thread.start()

    def _process_files(self):
        """Process all files in folder with rules"""
        was_running = False
        try:
            # CRITICAL: Stop monitor to prevent infinite loop from file events
            was_running = self.monitor.is_running
            if was_running:
                self.monitor.stop()
                logger.info(f"[Run Rules Now] Temporarily stopped monitor for {self.monitor.path}")

            # Get destination folders from all rules to exclude them
            destination_paths = set()
            for rule in self.rules:
                if rule.get("action_type") in ["move", "copy"]:
                    dest = rule.get("action_params", {}).get("destination", "")
                    if dest:
                        try:
                            dest_path = Path(dest).resolve()
                            destination_paths.add(dest_path)
                            logger.info(f"[Run Rules Now] Excluding destination: {dest_path}")
                        except:
                            pass

            # Collect all files BUT exclude destination folders
            all_files = []
            for item in self.folder_path.rglob("*"):
                if item.is_file():
                    # CRITICAL: Skip files already in destination folders
                    skip = False
                    try:
                        item_resolved = item.resolve()
                        for dest_path in destination_paths:
                            # Check if file is IN destination folder or IS the destination
                            if dest_path in item_resolved.parents or item_resolved.parent == dest_path:
                                skip = True
                                break
                    except:
                        pass

                    if not skip:
                        all_files.append(item)

            if not all_files:
                self.after(0, lambda: self._update_status("No files found to process", 1.0))
                self.after(0, self._complete)
                return

            total_files = len(all_files)
            self.after(0, lambda: self._update_status(f"Found {total_files} files to process", 0.0))
            logger.info(f"[Run Rules Now] Processing {total_files} files (excluded files in destination folders)")

            # Process each file with each rule
            for idx, file_path in enumerate(all_files):
                if self.cancelled:
                    break

                # Update progress
                progress = (idx + 1) / total_files
                self.after(0, lambda p=progress, c=idx+1, t=total_files: self._update_progress(p, c, t))

                # Try to apply rules
                for rule in self.rules:
                    if self.cancelled:
                        break

                    try:
                        # Check if rule matches file
                        if self._rule_matches_file(rule, file_path):
                            # Execute action
                            success = self.monitor.action_engine.execute_action(
                                rule["action_type"],
                                str(file_path),
                                rule.get("action_params", {})
                            )

                            if success:
                                self.success_count += 1

                    except Exception as e:
                        logger.error(f"Error processing {file_path.name}: {e}")

                self.processed_count += 1

            # Complete
            self.after(0, self._complete)

        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))

        finally:
            # CRITICAL: Restart monitor if it was running
            if was_running:
                self.monitor.start()
                logger.info(f"[Run Rules Now] Restarted monitor for {self.monitor.path}")

    def _rule_matches_file(self, rule: Dict, file_path: Path) -> bool:
        """Check if rule matches file"""
        # Check file extensions
        extensions = rule.get("file_extensions", ["*"])
        if "*" not in extensions:
            if file_path.suffix.lower() not in [ext.lower() for ext in extensions]:
                return False

        # CRITICAL: Check filename pattern if specified
        name_pattern = rule.get("name_pattern")
        if name_pattern:
            import re
            try:
                if not re.search(name_pattern, file_path.name, re.IGNORECASE):
                    return False
            except re.error:
                logger.error(f"Invalid regex pattern: {name_pattern}")
                return False

        return True

    def _update_progress(self, progress: float, current: int, total: int):
        """Update progress display"""
        if not self.winfo_exists():
            return

        try:
            self.progress.set(progress)
            self.details_label.configure(text=f"Processing: {current}/{total} files")
            self.results_label.configure(text=f"✓ Applied: {self.success_count} actions")
        except:
            pass

    def _update_status(self, message: str, progress: float):
        """Update status message"""
        if not self.winfo_exists():
            return

        try:
            self.status_label.configure(text=message)
            self.progress.set(progress)
        except:
            pass

    def _complete(self):
        """Called when processing is complete"""
        if not self.winfo_exists():
            return

        self.status_label.configure(text="✓ Complete!")
        self.progress.set(1.0)
        self.details_label.configure(text=f"Processed {self.processed_count} files")
        self.results_label.configure(
            text=f"✓ Successfully applied {self.success_count} actions",
            text_color="#4CAF50"
        )

        self.close_btn.configure(text="Close", fg_color="#4CAF50")

        # Auto-close after 3 seconds
        self.after(3000, self.destroy)

    def _show_error(self, error_msg: str):
        """Show error message"""
        if not self.winfo_exists():
            return

        self.status_label.configure(text="❌ Error", text_color="#F44336")
        self.details_label.configure(text=error_msg, text_color="#F44336")
        self.close_btn.configure(text="Close")

    def _close(self):
        """Close dialog"""
        self.cancelled = True
        self.destroy()
