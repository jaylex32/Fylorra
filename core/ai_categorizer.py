"""
Fylorra - AI Categorization Engine
Auto-organizes files based on visual content
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable
import threading
import shutil

logger = logging.getLogger(__name__)


class AICategorizer:
    """Handles automatic file categorization and organization"""

    # Category folder mappings
    CATEGORY_FOLDERS = {
        "screenshot_code": "Screenshots/Code",
        "screenshot_ui": "Screenshots/UI",
        "screenshot_other": "Screenshots",
        "photo": "Photos",
        "diagram": "Diagrams",
        "document": "Documents",
        "receipt": "Receipts",
        "meme": "Memes",
        "art": "Art",
        "audio": "Audio",
        "video": "Videos",
        "code": "Code",
        "archive": "Archives",
        "executable": "Executables",
        "config": "Config",
        "shortcut": "Shortcuts",
        "database": "Databases",
        "other": "Other"
    }

    def __init__(self, ai_manager):
        self.ai_manager = ai_manager

    def categorize_folder(self, folder_path: Path,
                         progress_callback: Optional[Callable[[str, float, int, int], None]] = None,
                         create_folders: bool = True,
                         move_files: bool = False) -> Dict[str, List[Path]]:
        """
        Categorize all files in a folder (runs in background thread - won't freeze UI)

        Args:
            folder_path: Path to folder to categorize
            progress_callback: Callback(message, progress, current, total)
            create_folders: Whether to create category folders
            move_files: Whether to actually move files (False = dry run)

        Returns:
            Dict mapping categories to file lists
        """
        # Don't need AI to be ready for rule-based categorization
        # if not self.ai_manager.is_ready:
        #     logger.error("AI manager not ready")
        #     return {}

        # Collect ALL files recursively (including subfolders) - NO LIMIT
        # Use generator to avoid blocking during collection
        if progress_callback:
            progress_callback("Scanning folder...", 0.0, 0, 0)

        files_to_process = []
        file_count = 0
        for item in folder_path.rglob("*"):
            if item.is_file():
                # Check file size without blocking
                try:
                    if item.stat().st_size <= self.ai_manager.MAX_FILE_SIZE:
                        files_to_process.append(item)
                        file_count += 1
                        # Update every 100 files during scan
                        if file_count % 100 == 0 and progress_callback:
                            progress_callback(f"Found {file_count} files...", 0.0, 0, file_count)
                except OSError:
                    # Skip files we can't access
                    continue

        if not files_to_process:
            logger.info("No files to categorize")
            return {}

        # Process ALL files - no batch limit for auto categorize
        total_files = len(files_to_process)
        logger.info(f"Categorizing {total_files} files")

        # Results
        categorized: Dict[str, List[Path]] = {}

        for idx, file_path in enumerate(files_to_process):
            # Throttle progress updates - only update every 10 files or at completion
            if progress_callback and (idx % 10 == 0 or idx == total_files - 1):
                progress_callback(
                    f"Analyzing files...",
                    (idx + 1) / total_files,
                    idx + 1,
                    total_files
                )

            # Categorize file (fast rule-based)
            category = self.ai_manager.categorize_visual_content(file_path)

            if category and category in self.CATEGORY_FOLDERS:
                if category not in categorized:
                    categorized[category] = []
                categorized[category].append(file_path)

        # Move files if requested
        if move_files:
            self._organize_files(folder_path, categorized, create_folders)

        return categorized

    def _organize_files(self, base_path: Path, categorized: Dict[str, List[Path]],
                       create_folders: bool = True) -> int:
        """Move files into category folders"""
        moved_count = 0

        for category, files in categorized.items():
            # Get target folder
            target_folder = base_path / self.CATEGORY_FOLDERS[category]

            # Create folder if needed
            if create_folders:
                target_folder.mkdir(parents=True, exist_ok=True)
            elif not target_folder.exists():
                continue

            # Move files
            for file_path in files:
                try:
                    target_path = target_folder / file_path.name

                    # Handle duplicates
                    if target_path.exists():
                        stem = file_path.stem
                        suffix = file_path.suffix
                        counter = 1
                        while target_path.exists():
                            target_path = target_folder / f"{stem}_{counter}{suffix}"
                            counter += 1

                    # Move file
                    shutil.move(str(file_path), str(target_path))
                    moved_count += 1
                    logger.info(f"Moved {file_path.name} to {category}")

                except Exception as e:
                    logger.error(f"Error moving {file_path}: {e}")

        return moved_count

    def scan_for_sensitive_files(self, folder_path: Path,
                                 progress_callback: Optional[Callable[[str, float, int, int], None]] = None) -> List[Dict]:
        """
        Scan folder for files containing sensitive information

        Returns:
            List of {"file": Path, "reason": str} dicts
        """
        if not self.ai_manager.is_ready:
            return []

        # Collect files
        files_to_scan = []
        for ext in self.ai_manager.ALLOWED_EXTENSIONS:
            files_to_scan.extend(folder_path.glob(f"*{ext}"))

        files_to_scan = files_to_scan[:self.ai_manager.MAX_BATCH_SIZE]
        total_files = len(files_to_scan)

        sensitive_files = []

        for idx, file_path in enumerate(files_to_scan):
            if progress_callback:
                progress_callback(
                    f"Scanning {file_path.name}...",
                    (idx + 1) / total_files,
                    idx + 1,
                    total_files
                )

            # Check for sensitive content
            result = self.ai_manager.detect_sensitive_content(file_path)

            if result.get("sensitive", False):
                sensitive_files.append({
                    "file": file_path,
                    "reason": result.get("reason", "Sensitive content detected")
                })

        return sensitive_files
