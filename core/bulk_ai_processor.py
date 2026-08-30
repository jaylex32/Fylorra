"""
Fylorra - Bulk AI Processing Engine
High-performance batch processing for AI operations with folder recursion
"""

from pathlib import Path
from typing import List, Dict, Callable, Optional, Set
from dataclasses import dataclass
from enum import Enum
import threading
import time
import os


class ProcessingMode(Enum):
    """Processing modes for bulk operations"""
    FAST = "fast"  # Rule-based only, no AI
    SMART = "smart"  # AI for complex cases only
    DEEP = "deep"  # AI for everything (slow)


@dataclass
class ProcessingOptions:
    """Options for bulk processing"""
    include_subfolders: bool = True
    file_extensions: Optional[Set[str]] = None  # None = all files, {"jpg", "png"} = filter
    batch_size: int = 50  # Process N files before updating UI
    mode: ProcessingMode = ProcessingMode.SMART
    skip_errors: bool = True  # Continue on errors vs stop
    max_files: Optional[int] = None  # Limit total files (None = unlimited)


@dataclass
class ProcessingResult:
    """Result of processing a single file"""
    file_path: Path
    success: bool
    data: Optional[Dict] = None  # Operation-specific result data
    error: Optional[str] = None
    processing_time: float = 0.0  # Seconds
    used_ai: bool = False


@dataclass
class ProcessingStats:
    """Statistics for a bulk processing operation"""
    total_files: int = 0
    processed: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    total_time: float = 0.0
    ai_operations: int = 0
    average_time_per_file: float = 0.0


class BulkAIProcessor:
    """
    High-performance bulk processing engine for AI operations

    Features:
    - Folder recursion with subfolder support
    - File extension filtering
    - Batched progress updates
    - Cancelable operations
    - Detailed statistics tracking
    - Thread-safe progress callbacks
    """

    def __init__(self, ai_manager):
        self.ai_manager = ai_manager
        self.cancelled = False
        self.processing = False
        self._lock = threading.Lock()

    def scan_folder(self, folder_path: Path, options: ProcessingOptions) -> List[Path]:
        """
        Scan folder for files matching criteria

        Args:
            folder_path: Root folder to scan
            options: Processing options including subfolder/extension filters

        Returns:
            List of file paths matching criteria
        """
        files = []

        def allow(p: Path) -> bool:
            if options.file_extensions is not None:
                ext = p.suffix.lower().lstrip(".")
                if ext not in options.file_extensions:
                    return False
            return True

        try:
            if not options.include_subfolders:
                for entry in os.scandir(folder_path):
                    if self.cancelled:
                        break
                    if not entry.is_file():
                        continue
                    p = Path(entry.path)
                    if allow(p):
                        files.append(p)
                        if options.max_files and len(files) >= options.max_files:
                            break
                return files

            # Recursive walk (faster than Path.rglob on Windows for large trees)
            for root, dirs, fnames in os.walk(folder_path):
                if self.cancelled:
                    break

                # Skip common internal/output dirs.
                dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".fylorra", "Converted_Media", "Converted_Images", "Converted_Office"}]

                for name in fnames:
                    if self.cancelled:
                        break
                    p = Path(root) / name
                    if not p.is_file():
                        continue
                    if allow(p):
                        files.append(p)
                        if options.max_files and len(files) >= options.max_files:
                            return files

        except Exception as e:
            print(f"Error scanning folder: {e}")

        return files

    def process_files(
        self,
        files: List[Path],
        processor_func: Callable[[Path], ProcessingResult],
        options: ProcessingOptions,
        progress_callback: Optional[Callable[[str, float, ProcessingStats], None]] = None
    ) -> Dict[str, any]:
        """
        Process multiple files in batches with progress tracking

        Args:
            files: List of files to process
            processor_func: Function that processes a single file and returns ProcessingResult
            options: Processing options
            progress_callback: Callback(message, progress, stats) for UI updates

        Returns:
            Dictionary with results and statistics
        """
        with self._lock:
            self.processing = True
            self.cancelled = False

        start_time = time.time()
        stats = ProcessingStats(total_files=len(files))
        results: List[ProcessingResult] = []

        try:
            for idx, file_path in enumerate(files):
                # Check cancellation
                if self.cancelled:
                    stats.skipped = len(files) - idx
                    break

                # Process file
                file_start_time = time.time()
                try:
                    result = processor_func(file_path)
                    results.append(result)

                    if result.success:
                        stats.successful += 1
                    else:
                        stats.failed += 1

                    if result.used_ai:
                        stats.ai_operations += 1

                except Exception as e:
                    # Handle processing error
                    error_result = ProcessingResult(
                        file_path=file_path,
                        success=False,
                        error=str(e),
                        processing_time=time.time() - file_start_time
                    )
                    results.append(error_result)
                    stats.failed += 1

                    # Stop on error if configured
                    if not options.skip_errors:
                        stats.skipped = len(files) - idx - 1
                        break

                stats.processed = idx + 1

                # Update progress at batch intervals or completion
                if (idx + 1) % options.batch_size == 0 or idx == len(files) - 1:
                    progress = (idx + 1) / len(files)
                    elapsed = time.time() - start_time
                    stats.total_time = elapsed
                    stats.average_time_per_file = elapsed / (idx + 1) if idx >= 0 else 0

                    # Calculate ETA
                    if progress > 0 and progress < 1:
                        eta_seconds = (elapsed / progress) - elapsed
                        eta_text = self._format_time(eta_seconds)
                        message = f"Processing {idx + 1}/{len(files)} files (ETA: {eta_text})"
                    else:
                        message = f"Processed {idx + 1}/{len(files)} files"

                    # Callback on main thread (caller's responsibility to schedule)
                    if progress_callback:
                        progress_callback(message, progress, stats)

        finally:
            with self._lock:
                self.processing = False

        # Final statistics
        stats.total_time = time.time() - start_time
        if stats.processed > 0:
            stats.average_time_per_file = stats.total_time / stats.processed

        return {
            "results": results,
            "stats": stats,
            "cancelled": self.cancelled
        }

    def process_folder(
        self,
        folder_path: Path,
        processor_func: Callable[[Path], ProcessingResult],
        options: ProcessingOptions,
        progress_callback: Optional[Callable[[str, float, ProcessingStats], None]] = None
    ) -> Dict[str, any]:
        """
        Scan and process all files in a folder

        Args:
            folder_path: Root folder to process
            processor_func: Function that processes a single file
            options: Processing options
            progress_callback: Callback for progress updates

        Returns:
            Dictionary with results and statistics
        """
        # First, scan for files
        scan_callback_message = f"Scanning {'folder tree' if options.include_subfolders else 'folder'}..."
        if progress_callback:
            progress_callback(scan_callback_message, 0.0, ProcessingStats())

        files = self.scan_folder(folder_path, options)

        if not files:
            return {
                "results": [],
                "stats": ProcessingStats(),
                "cancelled": False,
                "error": "No files found matching criteria"
            }

        # Then process files
        return self.process_files(files, processor_func, options, progress_callback)

    def cancel(self):
        """Cancel ongoing processing"""
        with self._lock:
            self.cancelled = True

    def is_processing(self) -> bool:
        """Check if currently processing"""
        with self._lock:
            return self.processing

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into human-readable time"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"

    @staticmethod
    def get_image_extensions() -> Set[str]:
        """Get common image file extensions"""
        return {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'tif', 'ico', 'svg'}

    @staticmethod
    def get_video_extensions() -> Set[str]:
        """Get common video file extensions"""
        return {'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v', 'mpg', 'mpeg'}

    @staticmethod
    def get_audio_extensions() -> Set[str]:
        """Get common audio file extensions"""
        return {'mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'wma', 'opus', 'ape'}

    @staticmethod
    def get_document_extensions() -> Set[str]:
        """Get common document file extensions"""
        return {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'txt', 'rtf'}

    @staticmethod
    def get_code_extensions() -> Set[str]:
        """Get common code file extensions"""
        return {
            'py', 'js', 'ts', 'jsx', 'tsx', 'java', 'c', 'cpp', 'h', 'hpp',
            'cs', 'go', 'rs', 'rb', 'php', 'swift', 'kt', 'dart', 'scala',
            'html', 'css', 'scss', 'sass', 'vue', 'json', 'xml', 'yaml', 'yml'
        }
