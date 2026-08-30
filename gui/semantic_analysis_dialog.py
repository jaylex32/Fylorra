"""
Fylorra - Semantic Analysis Dialog
Shows intelligent document analysis with confidence-based suggestions
"""

import customtkinter as ctk
from pathlib import Path
from typing import Optional, Callable, List, Dict
import threading
from utils.png_icons import PNGIconLoader
from utils.tooltip import ToolTipHelper
from core.semantic_analyzer import AnalysisResult
from core.bulk_ai_processor import BulkAIProcessor, ProcessingOptions
from utils.intelligent_rename import (
    sanitize_ai_filename, get_unique_filename,
    learn_folder_patterns, apply_learned_pattern
)
from utils.rename_history import get_history_manager, RenameOperation
from utils.universal_undo import get_undo_manager, FileOperation, OperationType
from gui.rename_preview_dialog import RenamePreview, show_rename_preview
from datetime import datetime


class SemanticAnalysisDialog(ctk.CTkToplevel):
    """Dialog showing semantic document analysis with actionable suggestions"""

    def __init__(self, parent, semantic_analyzer, file_path: Optional[Path] = None,
                 on_action: Optional[Callable] = None, folder_mode: bool = False):
        super().__init__(parent)

        self.semantic_analyzer = semantic_analyzer
        self.file_path = file_path  # Single file mode
        self.folder_mode = folder_mode  # Bulk folder mode
        self.on_action = on_action
        self.icon_loader = PNGIconLoader()
        self.bulk_processor = BulkAIProcessor(semantic_analyzer.ai_manager)

        self.result: Optional[AnalysisResult] = None
        self.results: List[tuple[Path, AnalysisResult]] = []  # For bulk mode
        self.result_checkboxes: Dict[Path, ctk.BooleanVar] = {}  # Track which files are selected
        self.processing = False
        self.cancelled = False

        if folder_mode:
            title_text = f"Bulk Analysis - {file_path.name if file_path else 'Select Folder'}"
        else:
            title_text = f"AI Analysis - {file_path.name[:50]}" if file_path else "AI Analysis"

        self.title(title_text)
        self.geometry("800x750")
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 400
        y = (self.winfo_screenheight() // 2) - 375
        self.geometry(f"800x750+{x}+{y}")

        self._create_ui()

        # Start analysis
        if not folder_mode:
            self.after(100, self._start_analysis)
        else:
            self.after(100, self._start_bulk_analysis)

    def _create_ui(self):
        """Create the dialog UI"""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=60)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        header_frame.pack_propagate(False)

        # AI Icon
        ai_icon = self.icon_loader.load_icon("analytics", size=(40, 40))
        icon_label = ctk.CTkLabel(header_frame, image=ai_icon, text="")
        icon_label.image = ai_icon
        icon_label.place(x=0, y=10)

        # Title
        title = ctk.CTkLabel(
            header_frame,
            text="Semantic Document Analysis",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        )
        title.place(x=50, y=5)

        # Subtitle - file name
        subtitle = ctk.CTkLabel(
            header_frame,
            text=self.file_path.name,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray"
        )
        subtitle.place(x=50, y=35)

        # Progress frame (shown during analysis)
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=20, pady=(10, 0))

        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="Analyzing document content with AI...",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="gray"
        )
        self.progress_label.pack(pady=10)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=760, mode="indeterminate")
        self.progress_bar.pack(pady=(0, 10))
        self.progress_bar.start()

        # Results frame (shown after analysis)
        self.results_frame = ctk.CTkScrollableFrame(self, width=760, height=480)
        # Don't pack yet - will show after analysis

        # Bottom controls
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", padx=20, pady=(10, 20))

        # Close button (left)
        self.close_btn = ctk.CTkButton(
            controls_frame,
            text="Close",
            width=100,
            command=self._close,
            fg_color="gray",
            hover_color="#505050"
        )
        self.close_btn.pack(side="left")

        # Action buttons (right) - will be enabled based on confidence
        right_controls = ctk.CTkFrame(controls_frame, fg_color="transparent")
        right_controls.pack(side="right")

        # Undo button (always enabled if history exists)
        self.undo_btn = ctk.CTkButton(
            right_controls,
            text="⏮️ Undo",
            width=90,
            command=self._undo_last_rename,
            fg_color="gray40",
            hover_color="gray30"
        )
        self.undo_btn.pack(side="left", padx=(0, 10))
        self._update_undo_button()

        self.rename_btn = ctk.CTkButton(
            right_controls,
            text="Apply Rename",
            width=130,
            command=self._apply_rename,
            state="disabled",
            fg_color="#4CAF50",
            hover_color="#388E3C"
        )
        self.rename_btn.pack(side="left", padx=(0, 10))

        self.categorize_btn = ctk.CTkButton(
            right_controls,
            text="Apply Category",
            width=130,
            command=self._apply_category,
            state="disabled",
            fg_color="#2196F3",
            hover_color="#1976D2"
        )
        self.categorize_btn.pack(side="left")

    def _start_analysis(self):
        """Start semantic analysis in background"""
        self.processing = True
        thread = threading.Thread(target=self._analyze, daemon=True)
        thread.start()

    def _analyze(self):
        """Perform semantic analysis"""
        try:
            # Analyze document
            self.result = self.semantic_analyzer.analyze_document(self.file_path, use_cache=False)

            # Show results
            if not self.cancelled and self.winfo_exists():
                self.after(0, self._show_results)

        except Exception as e:
            print(f"Analysis error: {e}")
            import traceback
            traceback.print_exc()

            if not self.cancelled and self.winfo_exists():
                self.after(0, lambda: self._show_error(str(e)))

    def _show_results(self):
        """Display analysis results with confidence-based UI"""
        self.processing = False

        # Hide progress
        self.progress_bar.stop()
        self.progress_frame.pack_forget()

        # Show results
        self.results_frame.pack(padx=20, pady=(10, 10), fill="both", expand=True)

        if not self.result:
            self._show_error("Analysis failed - could not extract document intelligence")
            return

        # Confidence indicator at top
        confidence_frame = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        confidence_frame.pack(fill="x", pady=(10, 20))

        # Confidence bar
        conf_value = self.result.confidence
        if conf_value >= 0.85:
            conf_color = "#4CAF50"  # Green - high confidence
            conf_text = "HIGH CONFIDENCE"
        elif conf_value >= 0.60:
            conf_color = "#FF9800"  # Orange - medium
            conf_text = "MEDIUM CONFIDENCE"
        else:
            conf_color = "#F44336"  # Red - low
            conf_text = "LOW CONFIDENCE"

        conf_label = ctk.CTkLabel(
            confidence_frame,
            text=f"{conf_text} ({conf_value:.0%})",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=conf_color
        )
        conf_label.pack()

        # Visual confidence bar
        conf_bar_bg = ctk.CTkFrame(confidence_frame, height=8, fg_color="#2b2b2b", corner_radius=4)
        conf_bar_bg.pack(fill="x", pady=(10, 0), padx=100)

        conf_bar_fill = ctk.CTkFrame(
            conf_bar_bg,
            height=8,
            width=int(600 * conf_value),
            fg_color=conf_color,
            corner_radius=4
        )
        conf_bar_fill.place(x=0, y=0)

        # Main analysis sections
        self._add_section("📄 Document Classification", [
            ("Type", self.result.document_type.title()),
            ("Domain", self.result.domain.title()),
            ("Sensitivity", self.result.sensitivity.upper())
        ])

        if self.result.entities:
            entities_text = ", ".join(self.result.entities[:10])
            if len(self.result.entities) > 10:
                entities_text += f" ... and {len(self.result.entities) - 10} more"
            self._add_section("🔍 Extracted Entities", [
                ("Found", entities_text)
            ])

        if self.result.key_date:
            self._add_section("📅 Key Date", [
                ("Date", self.result.key_date)
            ])

        # AI Reasoning
        self._add_section("💡 AI Reasoning", [
            ("Explanation", self.result.explanation)
        ], explanation_style=True)

        # Suggestions (if high/medium confidence)
        if self.result.confidence >= 0.60:
            suggestions = []

            if self.result.suggested_filename:
                suggestions.append(("Suggested Filename", self.result.suggested_filename))
                # Enable rename button
                self.rename_btn.configure(state="normal")

            if self.result.suggested_category:
                suggestions.append(("Suggested Category", self.result.suggested_category))
                # Enable categorize button
                self.categorize_btn.configure(state="normal")

            if suggestions:
                self._add_section("✨ Smart Suggestions", suggestions, highlight=True)

        # Low confidence warning
        if self.result.confidence < 0.60:
            warning_frame = ctk.CTkFrame(self.results_frame, fg_color="#2b2b2b", corner_radius=8)
            warning_frame.pack(fill="x", pady=10, padx=10)

            warning_icon = ctk.CTkLabel(
                warning_frame,
                text="⚠",
                font=ctk.CTkFont(size=24),
                text_color="#FF9800"
            )
            warning_icon.pack(pady=(15, 5))

            warning_text = ctk.CTkLabel(
                warning_frame,
                text="Low confidence - AI could not confidently classify this document.\nConsider manual review or use rule-based categorization.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="gray",
                justify="center"
            )
            warning_text.pack(pady=(0, 15))

        # Metadata at bottom
        metadata_text = f"Model: {self.result.model_used} • Analyzed: {self.result.analyzed_at[:19]}"
        metadata_label = ctk.CTkLabel(
            self.results_frame,
            text=metadata_text,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#666666"
        )
        metadata_label.pack(pady=(20, 10))

    def _add_section(self, title: str, items: list, highlight: bool = False, explanation_style: bool = False):
        """Add a section to results"""
        section_frame = ctk.CTkFrame(
            self.results_frame,
            fg_color="#2b2b2b" if not highlight else "#1a4d2e",
            corner_radius=8
        )
        section_frame.pack(fill="x", pady=8, padx=10)

        # Section title
        title_label = ctk.CTkLabel(
            section_frame,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            anchor="w"
        )
        title_label.pack(anchor="w", padx=15, pady=(12, 8))

        # Items
        for label, value in items:
            item_frame = ctk.CTkFrame(section_frame, fg_color="transparent")
            item_frame.pack(fill="x", padx=15, pady=3)

            if explanation_style:
                # Multi-line explanation
                value_label = ctk.CTkLabel(
                    item_frame,
                    text=value,
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color="#e0e0e0",
                    anchor="w",
                    justify="left",
                    wraplength=680
                )
                value_label.pack(anchor="w", pady=(0, 10))
            else:
                # Label: Value format
                label_text = ctk.CTkLabel(
                    item_frame,
                    text=f"{label}:",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color="gray",
                    width=120,
                    anchor="w"
                )
                label_text.pack(side="left")

                value_text = ctk.CTkLabel(
                    item_frame,
                    text=value,
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color="#e0e0e0",
                    anchor="w"
                )
                value_text.pack(side="left", fill="x", expand=True)

    def _show_error(self, error_msg: str):
        """Show error message"""
        self.progress_bar.stop()
        self.progress_frame.pack_forget()
        self.results_frame.pack(padx=20, pady=(10, 10), fill="both", expand=True)

        error_icon = ctk.CTkLabel(
            self.results_frame,
            text="❌",
            font=ctk.CTkFont(size=48),
            text_color="#F44336"
        )
        error_icon.pack(pady=(50, 20))

        error_label = ctk.CTkLabel(
            self.results_frame,
            text="Analysis Failed",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#F44336"
        )
        error_label.pack(pady=10)

        error_desc = ctk.CTkLabel(
            self.results_frame,
            text=error_msg,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="gray",
            wraplength=600
        )
        error_desc.pack(pady=10)

    def _apply_rename(self):
        """Apply suggested filename with intelligent validation and preview"""
        from tkinter import messagebox

        # Handle bulk mode
        if self.folder_mode:
            # Get selected files
            selected_files = [(path, result) for path, result in self.results
                            if self.result_checkboxes.get(path, ctk.BooleanVar(value=False)).get()]

            if not selected_files:
                messagebox.showwarning("No Selection", "Please select at least one file to rename.")
                return

            # Learn patterns from existing files in the folder
            folder_path = selected_files[0][0].parent
            pattern_info = learn_folder_patterns(folder_path)

            # Build preview list with intelligent validation
            previews = []
            for file_path, result in selected_files:
                if not result.suggested_filename:
                    continue

                # Apply learned pattern if available
                if pattern_info['template'] and pattern_info['confidence'] > 0.5:
                    ai_analysis = result.to_dict()
                    suggested_name = apply_learned_pattern(
                        pattern_info['template'],
                        ai_analysis,
                        pattern_info['separator']
                    )
                else:
                    suggested_name = result.suggested_filename

                # Sanitize filename
                validation = sanitize_ai_filename(suggested_name, preserve_case=True)
                sanitized_name = validation.sanitized_name

                # AI context for smart duplicate detection
                ai_context = {
                    'new_analysis': result.to_dict()
                }

                # Find unique name with smart duplicate handling
                unique_name, dup_explanation = get_unique_filename(
                    file_path,
                    sanitized_name,
                    ai_context
                )

                # Create preview
                preview = RenamePreview(
                    original_path=file_path,
                    new_name=unique_name,
                    validation_issues=validation.issues_found,
                    confidence=validation.confidence * result.confidence,
                    is_duplicate=(unique_name != sanitized_name),
                    duplicate_explanation=dup_explanation if unique_name != sanitized_name else ""
                )
                previews.append(preview)

            if not previews:
                messagebox.showwarning("No Renames", "No files have rename suggestions.")
                return

            # Show preview dialog
            confirmed = show_rename_preview(self, previews)
            if not confirmed:
                return

            # Perform renames
            success_count = 0
            failed_files = []
            path_mappings = {}
            rename_operations = []

            for preview in previews:
                file_path = preview.original_path
                new_name = preview.new_name + file_path.suffix
                new_path = file_path.parent / new_name

                try:
                    # Perform rename
                    file_path.rename(new_path)
                    path_mappings[file_path] = new_path
                    success_count += 1

                    # Record for history
                    rename_operations.append(
                        RenameOperation(
                            old_path=str(file_path),
                            new_path=str(new_path),
                            timestamp=datetime.now().isoformat(),
                            success=True
                        )
                    )
                except Exception as e:
                    failed_files.append(f"{file_path.name}: {str(e)}")
                    rename_operations.append(
                        RenameOperation(
                            old_path=str(file_path),
                            new_path=str(new_path),
                            timestamp=datetime.now().isoformat(),
                            success=False,
                            error_message=str(e)
                        )
                    )

            # Save to history for undo capability
            history_manager = get_history_manager()
            transaction_id = history_manager.create_transaction(
                rename_operations,
                metadata={
                    'folder': str(folder_path),
                    'pattern_used': pattern_info['template'],
                    'ai_model': selected_files[0][1].model_used
                }
            )

            # Update results list with new paths so categorization still works
            updated_results = []
            for old_path, result in self.results:
                new_path = path_mappings.get(old_path, old_path)
                updated_results.append((new_path, result))
            self.results = updated_results

            # Update checkboxes dictionary with new paths
            updated_checkboxes = {}
            for old_path, checkbox_var in self.result_checkboxes.items():
                new_path = path_mappings.get(old_path, old_path)
                updated_checkboxes[new_path] = checkbox_var
            self.result_checkboxes = updated_checkboxes

            # Show summary with undo option
            summary = f"✓ Successfully renamed {success_count}/{len(previews)} files.\n\n"
            summary += f"💾 Transaction ID: #{transaction_id}\n"
            summary += "💡 You can undo this rename for 30 days"

            if failed_files:
                summary += f"\n\n⚠️ Failed:\n" + "\n".join(failed_files[:5])
                if len(failed_files) > 5:
                    summary += f"\n... and {len(failed_files) - 5} more"

            messagebox.showinfo("Bulk Rename Complete", summary)

            # Disable button after rename
            if success_count > 0:
                self.rename_btn.configure(state="disabled", text="✓ Renamed")

            return

        # Handle single file mode with intelligent validation
        if not self.result or not self.result.suggested_filename:
            return

        # Sanitize AI suggestion
        validation = sanitize_ai_filename(self.result.suggested_filename, preserve_case=True)
        sanitized_name = validation.sanitized_name

        # AI context for smart duplicate detection
        ai_context = {
            'new_analysis': self.result.to_dict()
        }

        # Find unique name
        unique_name, dup_explanation = get_unique_filename(
            self.file_path,
            sanitized_name,
            ai_context
        )

        # Create preview
        preview = RenamePreview(
            original_path=self.file_path,
            new_name=unique_name,
            validation_issues=validation.issues_found,
            confidence=validation.confidence * self.result.confidence,
            is_duplicate=(unique_name != sanitized_name),
            duplicate_explanation=dup_explanation if unique_name != sanitized_name else ""
        )

        # Show preview
        confirmed = show_rename_preview(self, [preview])
        if not confirmed:
            return

        new_name_full = unique_name + self.file_path.suffix
        new_path = self.file_path.parent / new_name_full

        try:
            # Perform rename
            self.file_path.rename(new_path)

            # Save to history
            history_manager = get_history_manager()
            history_manager.create_transaction(
                [RenameOperation(
                    old_path=str(self.file_path),
                    new_path=str(new_path),
                    timestamp=datetime.now().isoformat(),
                    success=True
                )],
                metadata={'ai_model': self.result.model_used}
            )

            self.file_path = new_path  # Update current file path

            # Update dialog title with new name
            self.title(f"AI Analysis - {new_name_full[:50]}")

            # Disable rename button (already renamed)
            self.rename_btn.configure(state="disabled", text="✓ Renamed")

            # Show success message but keep dialog open
            messagebox.showinfo("Success", f"✓ File renamed successfully!\n\nYou can now apply category or close.")
        except Exception as e:
            messagebox.showerror("Rename Failed", f"Could not rename file:\n{e}")

    def _apply_category(self):
        """Apply suggested category - move file to category subfolder"""
        from tkinter import messagebox, filedialog
        import shutil

        # Handle bulk mode
        if self.folder_mode:
            # Get selected files
            selected_files = [(path, result) for path, result in self.results
                            if self.result_checkboxes.get(path, ctk.BooleanVar(value=False)).get()]

            if not selected_files:
                messagebox.showwarning("No Selection", "Please select at least one file to categorize.")
                return

            # Ask user to select base category folder
            base_folder = filedialog.askdirectory(
                title="Select Base Folder for Categories",
                initialdir=str(self.file_path)
            )

            if not base_folder:
                return

            base_folder = Path(base_folder)

            confirm = messagebox.askyesno(
                "Confirm Bulk Categorization",
                f"Move {len(selected_files)} selected files to category subfolders in:\n\n{base_folder}\n\n"
                f"Each file will be moved to its suggested category subfolder.\n"
                f"💡 You can undo this operation for 30 days."
            )

            if not confirm:
                return

            success_count = 0
            failed_files = []
            undo_operations = []

            for file_path, result in selected_files:
                if result.suggested_category:
                    try:
                        # Create category folder
                        category_folder = base_folder / result.suggested_category
                        category_folder.mkdir(parents=True, exist_ok=True)

                        # Move file to category folder
                        dest_path = category_folder / file_path.name

                        # Handle duplicates
                        if dest_path.exists():
                            counter = 1
                            stem = file_path.stem
                            suffix = file_path.suffix
                            while dest_path.exists():
                                dest_path = category_folder / f"{stem}_{counter}{suffix}"
                                counter += 1

                        shutil.move(str(file_path), str(dest_path))
                        success_count += 1

                        # Record for undo
                        undo_operations.append(
                            FileOperation(
                                operation_type=OperationType.CATEGORIZE,
                                source_path=str(file_path),
                                destination_path=str(dest_path),
                                original_content=None,
                                timestamp=datetime.now().isoformat(),
                                success=True,
                                metadata={
                                    'category': result.suggested_category,
                                    'confidence': result.confidence,
                                    'ai_model': result.model_used
                                }
                            )
                        )
                    except Exception as e:
                        failed_files.append(f"{file_path.name}: {str(e)}")
                        undo_operations.append(
                            FileOperation(
                                operation_type=OperationType.CATEGORIZE,
                                source_path=str(file_path),
                                destination_path=str(dest_path),
                                original_content=None,
                                timestamp=datetime.now().isoformat(),
                                success=False,
                                error_message=str(e)
                            )
                        )

            # Save to undo history
            if undo_operations:
                undo_manager = get_undo_manager()
                transaction_id = undo_manager.create_transaction(
                    undo_operations,
                    OperationType.BULK_CATEGORIZE,
                    f"Bulk Categorize: {success_count} files",
                    metadata={'base_folder': str(base_folder)}
                )

            # Show summary with undo info
            summary = f"✓ Successfully categorized {success_count}/{len(selected_files)} files.\n\n"
            if undo_operations:
                summary += f"💾 Transaction ID: #{transaction_id}\n"
                summary += "💡 You can undo this categorization for 30 days"

            if failed_files:
                summary += f"\n\n⚠️ Failed:\n" + "\n".join(failed_files[:5])
                if len(failed_files) > 5:
                    summary += f"\n... and {len(failed_files) - 5} more"

            messagebox.showinfo("Bulk Categorization Complete", summary)

            # Disable button after categorization
            if success_count > 0:
                self.categorize_btn.configure(state="disabled", text="✓ Categorized")

            return

        # Handle single file mode
        if not self.result or not self.result.suggested_category:
            return

        category = self.result.suggested_category

        # Create category folder path (relative to file's parent)
        category_folder = self.file_path.parent / category

        # Ask user for confirmation with option to edit category
        response = messagebox.askyesnocancel(
            "Apply Category",
            f"Move file to category folder:\n\n{category_folder}\n\n"
            f"Confidence: {self.result.confidence:.0%}\n\n"
            f"Yes = Move to this category\n"
            f"No = Choose different folder\n"
            f"Cancel = Don't categorize"
        )

        if response is None:  # Cancel
            return
        elif response is False:  # Choose different folder
            category_folder = filedialog.askdirectory(
                title="Select Category Folder",
                initialdir=self.file_path.parent
            )
            if not category_folder:
                return
            category_folder = Path(category_folder)

        # Perform categorization
        try:
            # Create category folder if it doesn't exist
            category_folder.mkdir(parents=True, exist_ok=True)

            # Move file to category folder
            dest_path = category_folder / self.file_path.name

            # Handle duplicates
            if dest_path.exists():
                counter = 1
                stem = self.file_path.stem
                suffix = self.file_path.suffix
                while dest_path.exists():
                    dest_path = category_folder / f"{stem}_{counter}{suffix}"
                    counter += 1

            shutil.move(str(self.file_path), str(dest_path))
            self.file_path = dest_path

            # Update dialog title
            self.title(f"AI Analysis - {self.file_path.name[:50]}")

            # Disable categorize button
            self.categorize_btn.configure(state="disabled", text="✓ Categorized")

            # Show success
            messagebox.showinfo(
                "Success",
                f"File moved to category:\n\n{category_folder}\n\nYou can now rename or close."
            )

        except Exception as e:
            messagebox.showerror("Categorization Failed", f"Could not move file:\n{e}")

    def _start_bulk_analysis(self):
        """Start bulk folder analysis"""
        if not self.file_path or not self.file_path.exists():
            self.progress_label.configure(text="Invalid folder path")
            return

        self.progress_label.configure(text="Scanning folder for documents...")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()

        # Show results frame immediately (but empty)
        self.results_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Add summary header that will update
        self.summary_frame = ctk.CTkFrame(self.results_frame, fg_color="#2b2b2b", corner_radius=10)
        self.summary_frame.pack(fill="x", pady=(10, 10), padx=10)

        summary_top = ctk.CTkFrame(self.summary_frame, fg_color="transparent")
        summary_top.pack(fill="x", padx=15, pady=(15, 5))

        self.summary_label = ctk.CTkLabel(
            summary_top,
            text="📊 Scanning...",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold")
        )
        self.summary_label.pack(side="left")

        # Selection controls (will be shown after scan completes)
        self.selection_controls = ctk.CTkFrame(self.summary_frame, fg_color="transparent")
        # Don't pack yet - wait for results

        def analyze_bulk():
            # Scan for document files
            options = ProcessingOptions(
                include_subfolders=True,
                file_extensions=BulkAIProcessor.get_document_extensions(),
                batch_size=10
            )

            files = self.bulk_processor.scan_folder(self.file_path, options)

            if not files:
                self.after(0, lambda: self._show_no_files())
                return

            # Update summary with total found
            total = len(files)
            self.after(0, lambda: self.summary_label.configure(text=f"📊 Found {total} documents - analyzing..."))

            # Process each file and show immediately
            for idx, file in enumerate(files):
                if self.cancelled:
                    break

                # Update progress
                progress = (idx + 1) / total
                self.after(0, lambda i=idx, t=total, f=file: self._update_bulk_progress(i, t, f))

                # Analyze file
                result = self.semantic_analyzer.analyze_document(file)
                if result:
                    self.results.append((file, result))
                    # Show result immediately as it comes in
                    self.after(0, lambda f=file, r=result: self._add_bulk_result_card(f, r))

                # Update summary count
                self.after(0, lambda c=idx+1, t=total: self.summary_label.configure(
                    text=f"📊 Analyzed {c}/{t} documents"
                ))

            # Analysis complete
            self.after(0, lambda: self._finish_bulk_analysis(total))

        threading.Thread(target=analyze_bulk, daemon=True).start()

    def _update_bulk_progress(self, current: int, total: int, file: Path):
        """Update bulk analysis progress"""
        self.progress_label.configure(text=f"Analyzing {current + 1}/{total}: {file.name[:40]}")
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set((current + 1) / total)

    def _show_no_files(self):
        """Show no files found message"""
        self.progress_frame.pack_forget()
        self.progress_label.configure(text="No document files found in folder")
        self.progress_frame.pack(fill="x", padx=20, pady=(10, 0))

    def _finish_bulk_analysis(self, total: int):
        """Called when bulk analysis finishes"""
        # Update summary to show completion
        self.summary_label.configure(text=f"✅ Analyzed {len(self.results)}/{total} documents")

        # Update progress to complete
        self.progress_label.configure(text=f"Analysis complete - {len(self.results)} documents analyzed")
        self.progress_bar.set(1.0)
        self.progress_bar.stop()  # Stop indeterminate animation

        # Mark as not processing
        self.processing = False

        # Show selection controls
        self.selection_controls.pack(fill="x", padx=15, pady=(5, 15))

        select_all_btn = ctk.CTkButton(
            self.selection_controls,
            text="Select All",
            width=100,
            height=28,
            command=self._select_all,
            fg_color="#4CAF50",
            hover_color="#388E3C",
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        select_all_btn.pack(side="left", padx=5)

        select_none_btn = ctk.CTkButton(
            self.selection_controls,
            text="Select None",
            width=100,
            height=28,
            command=self._select_none,
            fg_color="gray",
            hover_color="#505050",
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        select_none_btn.pack(side="left", padx=5)

        selected_count = sum(1 for var in self.result_checkboxes.values() if var.get())
        selection_info = ctk.CTkLabel(
            self.selection_controls,
            text=f"({selected_count}/{len(self.result_checkboxes)} selected)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray"
        )
        selection_info.pack(side="left", padx=10)

        # Enable action buttons
        self.close_btn.configure(state="normal")
        self.rename_btn.configure(state="normal")
        self.categorize_btn.configure(state="normal")

    def _select_all(self):
        """Select all checkboxes"""
        for var in self.result_checkboxes.values():
            var.set(True)

    def _select_none(self):
        """Deselect all checkboxes"""
        for var in self.result_checkboxes.values():
            var.set(False)

    def _add_bulk_result_card(self, file_path: Path, result: AnalysisResult):
        """Add a result card for bulk mode"""
        card = ctk.CTkFrame(self.results_frame, fg_color="#1e1e1e", corner_radius=8)
        card.pack(fill="x", pady=5, padx=10)

        # Header with checkbox
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Checkbox
        checkbox_var = ctk.BooleanVar(value=True)  # Default checked
        self.result_checkboxes[file_path] = checkbox_var

        checkbox = ctk.CTkCheckBox(
            header_frame,
            text="",
            variable=checkbox_var,
            width=20,
            checkbox_width=20,
            checkbox_height=20
        )
        checkbox.pack(side="left", padx=(5, 10))

        # File name
        file_label = ctk.CTkLabel(
            header_frame,
            text=f"📄 {file_path.name}",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        file_label.pack(side="left", fill="x", expand=True)

        # Analysis result
        info_text = f"Type: {result.document_type} | Domain: {result.domain} | Confidence: {int(result.confidence * 100)}%"
        info_label = ctk.CTkLabel(
            card,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="gray",
            anchor="w"
        )
        info_label.pack(anchor="w", padx=15, pady=(0, 5))

        # Suggested filename
        if hasattr(result, 'suggested_filename') and result.suggested_filename:
            suggested_label = ctk.CTkLabel(
                card,
                text=f"💡 Suggested: {result.suggested_filename}",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#4CAF50",
                anchor="w"
            )
            suggested_label.pack(anchor="w", padx=15, pady=(0, 10))

    def _update_undo_button(self):
        """Update undo button state based on history"""
        try:
            history_manager = get_history_manager()
            recent = history_manager.get_recent_transactions(limit=1)

            if recent and recent[0].can_undo:
                self.undo_btn.configure(
                    state="normal",
                    text=f"⏮️ Undo ({recent[0].success_count})"
                )
            else:
                self.undo_btn.configure(state="disabled", text="⏮️ Undo")
        except Exception as e:
            self.undo_btn.configure(state="disabled", text="⏮️ Undo")

    def _undo_last_rename(self):
        """Undo the most recent rename transaction"""
        from tkinter import messagebox

        try:
            history_manager = get_history_manager()
            recent = history_manager.get_recent_transactions(limit=1)

            if not recent:
                messagebox.showinfo("No History", "No rename history found.")
                return

            transaction = recent[0]
            if not transaction.can_undo:
                messagebox.showinfo("Already Undone", "The most recent rename has already been undone.")
                return

            # Show confirmation
            confirm = messagebox.askyesno(
                "Confirm Undo",
                f"Undo rename of {transaction.success_count} files?\n\n"
                f"Transaction #{transaction.transaction_id}\n"
                f"Performed: {transaction.timestamp[:19]}\n\n"
                f"This will restore original filenames."
            )

            if not confirm:
                return

            # Perform undo
            success, message, reversed_count = history_manager.undo_transaction(transaction.transaction_id)

            if success:
                messagebox.showinfo(
                    "Undo Complete",
                    f"✓ Successfully reversed {reversed_count} renames.\n\n{message}"
                )
                self._update_undo_button()

                # Re-enable rename button if we're still in the dialog
                if self.rename_btn.cget("text") == "✓ Renamed":
                    self.rename_btn.configure(state="normal", text="Apply Rename")
            else:
                messagebox.showerror("Undo Failed", f"Could not undo rename:\n\n{message}")

        except Exception as e:
            messagebox.showerror("Error", f"Undo failed:\n{e}")

    def _close(self):
        """Close dialog"""
        self.cancelled = True
        self.destroy()
