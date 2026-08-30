"""
Fylorra - AI Manager
Handles vision-language model for intelligent file analysis
"""

import os
import sys
import json
import threading
import logging
import re
import subprocess
import shutil
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable
import base64
from io import BytesIO

try:
    from huggingface_hub import hf_hub_download, HfApi
    HAS_HF_HUB = True
except ImportError:
    HAS_HF_HUB = False
    hf_hub_download = None
    HfApi = None

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ModelProfile:
    kind: str  # "vision" | "text"
    model_id: str
    model_repo: str
    model_file: str
    mmproj_file: Optional[str] = None
    chat_format: Optional[str] = None


class AIManager:
    """Manages AI model loading, inference, and file analysis"""

    # Qwen3-VL 4B - State-of-the-art vision-language model (requires llama-cpp-python 0.3.17+)
    # Optimized for GPU/CPU with GGUF format
    MODEL_REPO = "Qwen/Qwen3-VL-4B-Instruct-GGUF"
    MODEL_FILE = "Qwen3VL-4B-Instruct-Q4_K_M.gguf"
    MMPROJ_FILE = "mmproj-Qwen3VL-4B-Instruct-F16.gguf"

    # Guardrails
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
    MAX_BATCH_SIZE = 50
    TIMEOUT_PER_FILE = 30
    MAX_FILENAME_LENGTH = 200

    @staticmethod
    def _parse_flash_attn_type(value) -> int:
        """
        llama-cpp flash_attn_type:
        -1 = AUTO, 0 = DISABLED, 1 = ENABLED
        """
        try:
            if isinstance(value, int):
                return int(value)
            s = str(value or "").strip().lower()
            if s in ("-1", "auto", "automatic", "default"):
                return -1
            if s in ("1", "on", "true", "enabled", "enable"):
                return 1
            if s in ("0", "off", "false", "disabled", "disable"):
                return 0
        except Exception:
            pass
        return -1

    def __init__(self, app_folder: Path, settings_manager=None):
        self.app_folder = app_folder
        self.models_folder = app_folder / "ai_models"
        self.models_folder.mkdir(exist_ok=True)
        self.settings_manager = settings_manager

        self.model = None
        self.is_loading = False
        self.is_ready = False
        self.load_error = None
        self._swap_lock = threading.RLock()
        self._profiles: dict[str, _ModelProfile] = {}
        self._active_kind: str = "vision"

        # Settings - load from settings manager or use defaults
        self.enabled = True
        if settings_manager:
            self.n_ctx = settings_manager.get_setting("ai_context_size", 2048)
            self.n_threads = settings_manager.get_setting("ai_threads", os.cpu_count())
            self.n_batch = settings_manager.get_setting("ai_batch_size", 512)
            self.n_gpu_layers = settings_manager.get_setting("ai_gpu_layers", 35)
            self.image_size = settings_manager.get_setting("ai_image_size", 512)
            self.flash_attn_type = self._parse_flash_attn_type(settings_manager.get_setting("ai_flash_attn_type", "auto"))
        else:
            # Defaults for fast inference
            self.n_ctx = 2048
            self.n_threads = os.cpu_count()
            self.n_batch = 512
            self.n_gpu_layers = 35
            self.image_size = 512
            self.flash_attn_type = -1

        self.temperature = 0.1  # Low for consistent naming

        # Active model slot (auto-swapped between text + vision profiles).
        # Defaults to the built-in Qwen3-VL vision model for backward compatibility.
        self.model_id: Optional[str] = None
        self.model_repo: str = self.MODEL_REPO
        self.model_file: str = self.MODEL_FILE
        self.mmproj_file: Optional[str] = self.MMPROJ_FILE
        self.chat_format: Optional[str] = None
        self.is_vision_model: bool = True
        self._load_profiles_from_settings()
        self._apply_profile(self._active_kind)

        # Vision rename prompt tuning (editable via settings.json)
        if settings_manager:
            self.rename_prompt = settings_manager.get_setting(
                "ai_rename_prompt",
                "Create a filename tag for THIS image.\n"
                "Rules:\n"
                "- Output ONE tag only (no lists, no multiple options).\n"
                "- 3 to 8 short keywords.\n"
                "- Lowercase words only.\n"
                "- Use spaces between words.\n"
                "- No punctuation, no quotes, no commas, no full sentences.\n"
                "- Avoid filler words (a, an, the, of, with, in, on, for).\n"
                "- If readable text is important (logo/app name/title), include 1-3 key words from it.\n"
                "- Prefer specific nouns over generic words like: picture, photo, image, logo, screenshot.\n"
                "Example format: keyword keyword keyword\n",
            )
            self.rename_max_keywords = int(settings_manager.get_setting("ai_rename_max_keywords", 8))
        else:
            self.rename_prompt = (
                "Create a filename tag for THIS image.\n"
                "Rules:\n"
                "- Output ONE tag only (no lists, no multiple options).\n"
                "- 3 to 8 short keywords.\n"
                "- Lowercase words only.\n"
                "- Use spaces between words.\n"
                "- No punctuation, no quotes, no commas, no full sentences.\n"
                "- Avoid filler words (a, an, the, of, with, in, on, for).\n"
                "- If readable text is important (logo/app name/title), include 1-3 key words from it.\n"
                "- Prefer specific nouns over generic words like: picture, photo, image, logo, screenshot.\n"
                "Example format: keyword keyword keyword\n"
            )
            self.rename_max_keywords = 8

        logger.info(
            "AI Manager initialized - Backend=llama_cpp "
            f"GPU Layers={self.n_gpu_layers} Threads={self.n_threads} Context={self.n_ctx} Batch={self.n_batch} "
            f"Image Size={self.image_size} Model={self.model_file}"
        )

    def _load_profiles_from_settings(self) -> None:
        """
        Build model profiles (vision + text) from settings.
        Keeps legacy single-slot keys working by treating them as the vision profile.
        """
        settings = self.settings_manager
        if not settings:
            self._profiles = {
                "vision": _ModelProfile(
                    kind="vision",
                    model_id=str(self.model_id or "default"),
                    model_repo=self.model_repo,
                    model_file=self.model_file,
                    mmproj_file=self.mmproj_file,
                    chat_format=self.chat_format,
                )
            }
            return

        try:
            from core.ai_model_catalog import get_model_spec, DEFAULT_MODEL_ID, DEFAULT_TEXT_MODEL_ID

            def _norm_opt(v) -> Optional[str]:
                s = str(v or "").strip()
                return s if s else None

            # Vision profile (defaults to legacy ai_model_* keys).
            legacy_vid = settings.get_setting("ai_model_id", DEFAULT_MODEL_ID)
            vision_id = str(settings.get_setting("ai_vision_model_id", legacy_vid) or legacy_vid).strip() or DEFAULT_MODEL_ID
            v_spec = get_model_spec(vision_id)
            if (v_spec.kind or "text").strip().lower() != "vision":
                v_spec = get_model_spec(DEFAULT_MODEL_ID)
            v_repo = str(settings.get_setting("ai_vision_model_repo", settings.get_setting("ai_model_repo", v_spec.repo) or v_spec.repo) or v_spec.repo)
            v_file = str(settings.get_setting("ai_vision_model_file", settings.get_setting("ai_model_file", v_spec.model_file) or v_spec.model_file) or v_spec.model_file)
            v_mm = settings.get_setting("ai_vision_mmproj_file", settings.get_setting("ai_mmproj_file", v_spec.mmproj_file) or v_spec.mmproj_file)
            v_mmproj = _norm_opt(v_mm)
            v_cf = settings.get_setting("ai_vision_chat_format", settings.get_setting("ai_chat_format", v_spec.chat_format) or v_spec.chat_format)
            v_chat_format = _norm_opt(v_cf) or (v_spec.chat_format or None)

            # Text profile (defaults to catalog default text model).
            text_id = str(settings.get_setting("ai_text_model_id", DEFAULT_TEXT_MODEL_ID) or DEFAULT_TEXT_MODEL_ID).strip() or DEFAULT_TEXT_MODEL_ID
            t_spec = get_model_spec(text_id)
            if (t_spec.kind or "text").strip().lower() != "text":
                t_spec = get_model_spec(DEFAULT_TEXT_MODEL_ID)
            t_repo = str(settings.get_setting("ai_text_model_repo", t_spec.repo) or t_spec.repo)
            t_file = str(settings.get_setting("ai_text_model_file", t_spec.model_file) or t_spec.model_file)
            t_mm = settings.get_setting("ai_text_mmproj_file", t_spec.mmproj_file)
            t_mmproj = _norm_opt(t_mm)
            t_cf = settings.get_setting("ai_text_chat_format", t_spec.chat_format)
            t_chat_format = _norm_opt(t_cf) or (t_spec.chat_format or None)

            self._profiles = {
                "vision": _ModelProfile(
                    kind="vision",
                    model_id=v_spec.id,
                    model_repo=v_repo,
                    model_file=v_file,
                    mmproj_file=v_mmproj or v_spec.mmproj_file,
                    chat_format=v_chat_format,
                ),
                "text": _ModelProfile(
                    kind="text",
                    model_id=t_spec.id,
                    model_repo=t_repo,
                    model_file=t_file,
                    mmproj_file=t_mmproj,
                    chat_format=t_chat_format,
                ),
            }
        except Exception:
            # Conservative fallback: keep current single-slot model config as vision.
            self._profiles = {
                "vision": _ModelProfile(
                    kind="vision",
                    model_id=str(settings.get_setting("ai_model_id", "") or "default"),
                    model_repo=str(settings.get_setting("ai_model_repo", self.MODEL_REPO) or self.MODEL_REPO),
                    model_file=str(settings.get_setting("ai_model_file", self.MODEL_FILE) or self.MODEL_FILE),
                    mmproj_file=str(settings.get_setting("ai_mmproj_file", self.MMPROJ_FILE) or self.MMPROJ_FILE),
                    chat_format=str(settings.get_setting("ai_chat_format", "") or "").strip() or None,
                )
            }

    def refresh_profiles_from_settings(self) -> None:
        """Reload text/vision profiles from Settings (used by Settings UI)."""
        with self._swap_lock:
            self._load_profiles_from_settings()
            # Keep the current profile applied (do not auto-load).
            self._apply_profile(self._active_kind)

    def _apply_profile(self, kind: str) -> None:
        k = (kind or "vision").strip().lower()
        if k not in ("vision", "text"):
            k = "vision"
        prof = self._profiles.get(k) or self._profiles.get("vision")
        if not prof:
            return
        self._active_kind = k
        self.model_id = prof.model_id
        self.model_repo = prof.model_repo
        self.model_file = prof.model_file
        self.mmproj_file = prof.mmproj_file
        self.chat_format = prof.chat_format
        self.is_vision_model = bool(k == "vision" and self.mmproj_file)

    def ensure_kind(self, kind: str, progress_callback: Optional[Callable[[str, float, str, str], None]] = None) -> bool:
        """
        Ensure the requested model kind is loaded (auto-swap).
        Returns True if the model is ready, False otherwise.
        """
        k = (kind or "vision").strip().lower()
        if k not in ("vision", "text"):
            k = "vision"

        with self._swap_lock:
            if self.is_loading:
                return bool(self.is_ready)

            # Already loaded and matches.
            if self.model is not None and self.is_ready and self._active_kind == k and bool(self.is_vision_model) == (k == "vision"):
                return True

            # Swap profile (unload old model if needed).
            try:
                if self.model is not None:
                    self.unload_model()
            except Exception:
                pass

            self._apply_profile(k)
            try:
                self.load_model(progress_callback)
            except Exception:
                return False
            return bool(self.is_ready)

    def select_kind(self, kind: str) -> None:
        """
        Select which profile should be used the next time the model is loaded.
        If a different kind is currently loaded, unload first.
        """
        k = (kind or "vision").strip().lower()
        if k not in ("vision", "text"):
            k = "vision"
        with self._swap_lock:
            if self.model is not None and self.is_ready and self._active_kind != k:
                try:
                    self.unload_model()
                except Exception:
                    pass
            self._apply_profile(k)

    def get_active_kind(self) -> str:
        """Return the currently selected/loaded model kind ('vision' or 'text')."""
        try:
            k = (self._active_kind or "vision").strip().lower()
        except Exception:
            k = "vision"
        return k if k in ("vision", "text") else "vision"

    def _ensure_vision_ready(
        self,
        progress_callback: Optional[Callable[[str, float, str, str], None]] = None,
    ) -> bool:
        """
        Ensure a vision-capable model is loaded.

        After adding a separate text model, some features may call vision-only methods
        while the text model is active. This helper auto-swaps to the vision profile.
        """
        try:
            if not self.enabled:
                return False
            if self.is_ready and self.is_vision_model:
                return True
            return self.ensure_kind("vision", progress_callback=progress_callback)
        except Exception:
            return False

    def ensure_model_downloaded(self, progress_callback: Optional[Callable[[str, float, str, str], None]] = None) -> bool:
        """
        Download model files if not present

        progress_callback(message, progress, downloaded_str, speed_str)
        """
        try:
            def _safe_dir_name(s: str) -> str:
                s = (s or "").strip()
                if not s:
                    return "default"
                return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80] or "default"

            # Store each model in its own subfolder to prevent mmproj filename collisions.
            model_dir = self.models_folder / _safe_dir_name(self.model_id or Path(self.model_file or self.MODEL_FILE).stem)
            try:
                model_dir.mkdir(exist_ok=True)
            except Exception:
                model_dir = self.models_folder

            model_path = model_dir / (self.model_file or self.MODEL_FILE)
            mmproj_path = (model_dir / self.mmproj_file) if self.mmproj_file else None

            # Backward compatible legacy paths (older versions stored files directly in ai_models/)
            legacy_model = self.models_folder / (self.model_file or self.MODEL_FILE)
            legacy_mmproj = (self.models_folder / self.mmproj_file) if self.mmproj_file else None

            # Check if already downloaded
            if (model_path.exists() and (mmproj_path is None or mmproj_path.exists())) or (
                legacy_model.exists() and (legacy_mmproj is None or legacy_mmproj.exists())
            ):
                logger.info("Model files already exist")
                if progress_callback:
                    progress_callback("Model ready", 1.0, "", "")
                return True

            logger.info("Downloading AI model files...")

            # Try to estimate total download size (for progress UI).
            # Use HEAD content-length when available; otherwise fall back to a small non-zero total.
            import requests

            def _head_size(url: str) -> int:
                try:
                    r = requests.head(url, allow_redirects=True, timeout=30)
                    return int(r.headers.get("content-length", 0) or 0)
                except Exception:
                    return 0

            model_url = f"https://huggingface.co/{self.model_repo}/resolve/main/{self.model_file}"
            mmproj_url = (
                f"https://huggingface.co/{self.model_repo}/resolve/main/{self.mmproj_file}"
                if mmproj_path is not None and self.mmproj_file
                else None
            )

            model_size_est = _head_size(model_url) if not model_path.exists() else model_path.stat().st_size
            mmproj_size_est = 0
            if mmproj_url and mmproj_path is not None:
                mmproj_size_est = _head_size(mmproj_url) if not mmproj_path.exists() else mmproj_path.stat().st_size
            total_size_est = max(1, int(model_size_est or 0) + int(mmproj_size_est or 0))

            # Download main model
            if not model_path.exists():
                if progress_callback:
                    progress_callback("Starting model download...", 0.0, "0 MB", "")

                import time

                response = requests.get(model_url, stream=True, timeout=30)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                start_time = time.time()
                last_update = start_time

                with open(model_path, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=65536):  # 64KB chunks for faster download
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Update UI every 0.3 seconds
                            now = time.time()
                            if now - last_update >= 0.3 or downloaded >= total_size:
                                overall_progress = downloaded / total_size_est

                                # Calculate speed
                                elapsed = now - start_time
                                if elapsed > 0:
                                    speed_bps = downloaded / elapsed
                                    speed_mbps = speed_bps / (1024 * 1024)

                                    # Calculate ETA
                                    remaining_bytes = total_size_est - downloaded
                                    eta_seconds = remaining_bytes / speed_bps if speed_bps > 0 else 0
                                    eta_min = int(eta_seconds / 60)
                                    eta_sec = int(eta_seconds % 60)

                                    downloaded_mb = downloaded / (1024 * 1024)
                                    total_mb = total_size_est / (1024 * 1024)

                                    if progress_callback:
                                        progress_callback(
                                            f"Downloading model... ({downloaded_mb:.1f} / {total_mb:.1f} MB)",
                                            overall_progress,
                                            f"{downloaded_mb:.1f} / {total_mb:.1f} MB",
                                            f"{speed_mbps:.1f} MB/s - ETA {eta_min}:{eta_sec:02d}"
                                        )

                                last_update = now

                logger.info(f"Model downloaded to {model_path}")

            # Download multimodal projector (vision models only)
            if mmproj_path is not None and mmproj_url and not mmproj_path.exists():
                if progress_callback:
                    progress_callback("Starting vision processor download...", 0.75, "", "")

                import time

                response = requests.get(mmproj_url, stream=True, timeout=30)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                start_time = time.time()
                last_update = start_time

                with open(mmproj_path, 'wb') as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=65536):  # 64KB chunks
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Update UI every 0.3 seconds
                            now = time.time()
                            if now - last_update >= 0.3 or downloaded >= total_size:
                                overall_progress = (model_size_est + downloaded) / total_size_est

                                elapsed = now - start_time
                                if elapsed > 0:
                                    speed_bps = downloaded / elapsed
                                    speed_mbps = speed_bps / (1024 * 1024)

                                    remaining_bytes = total_size_est - (model_size_est + downloaded)
                                    eta_seconds = remaining_bytes / speed_bps if speed_bps > 0 else 0
                                    eta_min = int(eta_seconds / 60)
                                    eta_sec = int(eta_seconds % 60)

                                    downloaded_mb = (model_size_est + downloaded) / (1024 * 1024)
                                    total_mb = total_size_est / (1024 * 1024)

                                    if progress_callback:
                                        progress_callback(
                                            f"Downloading vision processor... ({downloaded_mb:.1f} / {total_mb:.1f} MB)",
                                            overall_progress,
                                            f"{downloaded_mb:.1f} / {total_mb:.1f} MB",
                                            f"{speed_mbps:.1f} MB/s - ETA {eta_min}:{eta_sec:02d}"
                                        )

                                last_update = now

                logger.info(f"Projector downloaded to {mmproj_path}")

            if progress_callback:
                progress_callback("Download complete!", 1.0, "", "")

            return True

        except Exception as e:
            logger.error(f"Error downloading model: {e}")
            self.load_error = str(e)
            return False

    def load_model(self, progress_callback: Optional[Callable[[str, float, str, str], None]] = None):
        """Load the AI model into memory"""
        if self.is_loading or self.is_ready:
            return

        self.is_loading = True

        def safe_callback(message, value, downloaded="", speed=""):
            """Safely call progress callback, ignoring widget errors"""
            if progress_callback:
                try:
                    progress_callback(message, value, downloaded, speed)
                except Exception:
                    pass  # Ignore UI threading errors

        try:
            # llama-cpp backend
            if not self.ensure_model_downloaded(safe_callback):
                raise Exception("Failed to download model")

            safe_callback("Loading AI model into memory...", 0.95, "", "")

            from llama_cpp import Llama
            import inspect

            # Prefer per-model folder paths (prevents mmproj filename collisions), but fall back to legacy paths.
            def _safe_dir_name(s: str) -> str:
                s = (s or "").strip()
                if not s:
                    return "default"
                return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80] or "default"

            model_dir = self.models_folder / _safe_dir_name(self.model_id or Path(self.model_file or self.MODEL_FILE).stem)
            model_path = model_dir / (self.model_file or self.MODEL_FILE)
            mmproj_path = (model_dir / self.mmproj_file) if self.mmproj_file else None

            legacy_model = self.models_folder / (self.model_file or self.MODEL_FILE)
            legacy_mmproj = (self.models_folder / self.mmproj_file) if self.mmproj_file else None
            if legacy_model.exists() and not model_path.exists():
                model_path = legacy_model
            if legacy_mmproj is not None and legacy_mmproj.exists() and (mmproj_path is None or not mmproj_path.exists()):
                mmproj_path = legacy_mmproj

            logger.info(f"Loading model from {model_path}")
            if mmproj_path is not None:
                logger.info(f"Using vision processor from {mmproj_path}")
            logger.info("")

            from llama_cpp import __version__ as llama_version

            extra_kwargs: Dict[str, Any] = {}
            try:
                if "flash_attn_type" in inspect.signature(Llama.__init__).parameters:
                    extra_kwargs["flash_attn_type"] = self._parse_flash_attn_type(getattr(self, "flash_attn_type", -1))
            except Exception:
                extra_kwargs = {}

            if self.is_vision_model and mmproj_path is not None and mmproj_path.exists():
                from llama_cpp import llama_chat_format as chatfmt

                # Select the best vision chat handler available for the chosen model.
                model_key = (self.model_file or "").lower()
                chat_handler_cls = getattr(chatfmt, "Llava15ChatHandler", None)
                try:
                    if "qwen3" in model_key and hasattr(chatfmt, "Qwen3VLChatHandler"):
                        chat_handler_cls = chatfmt.Qwen3VLChatHandler
                    elif ("qwen2.5" in model_key or "qwen25" in model_key) and hasattr(chatfmt, "Qwen25VLChatHandler"):
                        chat_handler_cls = chatfmt.Qwen25VLChatHandler
                    elif "gemma-3" in model_key and hasattr(chatfmt, "Gemma3ChatHandler"):
                        chat_handler_cls = chatfmt.Gemma3ChatHandler
                    elif "llava-1.6" in model_key and hasattr(chatfmt, "Llava16ChatHandler"):
                        chat_handler_cls = chatfmt.Llava16ChatHandler
                except Exception:
                    pass
                try:
                    from llama_cpp.llama_chat_format import MoondreamChatHandler

                    if "moondream" in (self.model_file or "").lower():
                        chat_handler_cls = MoondreamChatHandler
                except Exception:
                    pass

                if chat_handler_cls is None:
                    raise RuntimeError("No compatible vision chat handler found in llama-cpp-python.")

                logger.info(f"llama-cpp-python {llama_version} - Using chat handler: {chat_handler_cls.__name__}")
                chat_handler = chat_handler_cls(
                    clip_model_path=str(mmproj_path),
                    verbose=False,
                )

                self.model = Llama(
                    model_path=str(model_path),
                    chat_handler=chat_handler,
                    n_ctx=self.n_ctx,
                    n_threads=self.n_threads,
                    n_batch=self.n_batch,
                    n_gpu_layers=self.n_gpu_layers,
                    use_mlock=True,
                    verbose=False,
                    logits_all=True,
                    rope_freq_base=0.0,
                    rope_freq_scale=0.0,
                    **extra_kwargs,
                )
            else:
                logger.info(f"llama-cpp-python {llama_version} - Using chat format: {self.chat_format or '(auto)'}")
                self.model = Llama(
                    model_path=str(model_path),
                    chat_format=self.chat_format or None,
                    n_ctx=self.n_ctx,
                    n_threads=self.n_threads,
                    n_batch=self.n_batch,
                    n_gpu_layers=self.n_gpu_layers,
                    use_mlock=True,
                    verbose=False,
                    logits_all=True,
                    rope_freq_base=0.0,
                    rope_freq_scale=0.0,
                    **extra_kwargs,
                )

            logger.info(
                f"Model loaded with: GPU Layers={self.n_gpu_layers}, Threads={self.n_threads}, Context={self.n_ctx}, Batch={self.n_batch}"
            )

            self.is_ready = True
            logger.info("✓ AI model loaded successfully and ready for inference")

            safe_callback("AI ready", 1.0, "", "")

        except Exception as e:
            logger.error(f"✗ Error loading model: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.load_error = str(e)
            self.is_ready = False
        finally:
            self.is_loading = False

    def load_model_async(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        """Load model in background thread"""
        thread = threading.Thread(
            target=self.load_model,
            args=(progress_callback,),
            daemon=True
        )
        thread.start()


    def analyze_file_for_rename(self, file_path: Path, use_ai: bool = False) -> Optional[str]:
        """
        Analyze file and suggest descriptive filename

        Args:
            file_path: Path to file
            use_ai: If True, use AI vision for single image (SLOW - 20-60 sec!)
                   If False, use fast rule-based cleanup (DEFAULT)
        """
        if not file_path.exists() or not file_path.is_file():
            return None

        try:
            ext = file_path.suffix.lower()

            # Only use AI if explicitly requested AND it's a single image
            if use_ai and ext in self.ALLOWED_EXTENSIONS:
                # Auto-swap to vision if the text model is currently loaded.
                if not self._ensure_vision_ready():
                    use_ai = False

            if use_ai and ext in self.ALLOWED_EXTENSIONS and self.is_ready and self.is_vision_model:
                if self._validate_file(file_path):
                    image_data = self._prepare_image(file_path)
                    if image_data:
                        try:
                            logger.info(f"Using AI vision for {file_path.name}...")

                            def run_vision_prompt(prompt_text: str) -> str:
                                response = self.model.create_chat_completion(
                                    messages=[
                                        {
                                            "role": "system",
                                            "content": "You generate short filename tags for images. Follow the user's format rules exactly.",
                                        },
                                        {
                                            "role": "user",
                                            "content": [
                                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                                                {"type": "text", "text": prompt_text},
                                            ],
                                        },
                                    ],
                                    max_tokens=48,
                                    temperature=0.1,
                                    top_p=1.0,
                                    repeat_penalty=1.1,
                                    frequency_penalty=0.0,
                                    presence_penalty=0.0
                                )
                                content = response.get("choices", [{}])[0].get("message", {}).get("content")
                                return "" if content is None else str(content)

                            def extract_subject_words(text: str) -> Optional[str]:
                                cleaned = (text or "").strip()
                                logger.info(f"AI raw response: '{cleaned}'")

                                # Remove common LLaVA/Llama chat template echoes if the model parrots the prompt.
                                cleaned = re.sub(r"(?is)^.*?ASSISTANT:\\s*", "", cleaned).strip()
                                cleaned = re.sub(r"(?is)^.*?Answer:\\s*", "", cleaned).strip()
                                cleaned = re.sub(r"(?is)^.*?Question:\\s*", "", cleaned).strip()

                                # If the model returns a list (commas/semicolons/newlines), take only the first candidate.
                                first_line = cleaned.splitlines()[0].strip() if cleaned else ""
                                for sep in [",", ";", "|"]:
                                    if sep in first_line:
                                        first_line = first_line.split(sep, 1)[0].strip()
                                cleaned = first_line

                                words = re.findall(r"[A-Za-z0-9]+", cleaned.lower())
                                if not words:
                                    return None

                                # Drop generic filler words so we don't get names like "a_picture_of_a".
                                stopwords = {
                                    "a", "an", "the", "of", "with", "in", "on", "for", "to", "and", "or",
                                    "this", "that", "these", "those", "is", "are", "was", "were",
                                    "picture", "photo", "image", "screenshot", "scene",
                                    "showing", "shows", "depicts", "depiction",
                                    "center", "left", "right", "top", "bottom", "front", "back",
                                    "background", "foreground", "pointing",
                                }
                                filtered: list[str] = []
                                for w in words:
                                    if w in stopwords:
                                        continue
                                    if w in filtered:
                                        continue  # de-dupe globally
                                    filtered.append(w)

                                # If we removed everything, fall back to the raw words.
                                if not filtered:
                                    filtered = words

                                # Reject purely numeric outputs like "1 2 3 4".
                                if not any(any(ch.isalpha() for ch in token) for token in filtered):
                                    return None

                                max_words = max(1, min(int(getattr(self, "rename_max_keywords", 8)), 12))
                                filtered = filtered[:max_words]
                                return "_".join(filtered) if filtered else None

                            raw_1 = run_vision_prompt(self.rename_prompt)
                            suggested_name = extract_subject_words(raw_1)

                            if not suggested_name:
                                prompt_2 = (
                                    "Return ONLY a short filename tag using 1 to 6 lowercase keywords. "
                                    "No punctuation, no quotes, no sentences, no filler words."
                                )
                                raw_2 = run_vision_prompt(prompt_2)
                                suggested_name = extract_subject_words(raw_2)

                            sanitized = self._sanitize_filename(suggested_name or "")
                            if sanitized and len(sanitized) >= 3:
                                logger.info(f"AI suggested: {sanitized}")
                                return sanitized

                            logger.warning(
                                f"AI response invalid after sanitization: '{(suggested_name or '').strip()}' -> '{sanitized}'"
                            )
                            # Fall through to rule-based cleanup
                        except Exception as e:
                            logger.warning(f"AI analysis failed: {e}")
                            import traceback
                            logger.warning(traceback.format_exc())

            # Fast rule-based cleanup (for all files)
            current_name = file_path.stem
            suggested_name = self._smart_cleanup_filename(current_name)
            return suggested_name

        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return None

    def _smart_cleanup_filename(self, filename: str) -> str:
        """MIND BLOWING filename cleanup with advanced pattern recognition"""
        import re

        original = filename
        clean = filename

        # STEP 1: Extract and preserve important suffixes FIRST
        preserved_suffix = ""

        # Preserve version numbers
        version_match = re.search(r'[_\s-]+(v\d+(?:\.\d+)?|version[_\s-]?\d+)', clean, re.IGNORECASE)
        if version_match:
            preserved_suffix = f"_{version_match.group(1).lower().replace(' ', '_').replace('-', '_')}"
            clean = clean[:version_match.start()] + clean[version_match.end():]

        # Preserve special type markers as suffixes
        special_types = {
            r'\(instrumental\)': '_instrumental',
            r'\(acoustic\)': '_acoustic',
            r'\(remix\)': '_remix',
            r'\(live\)': '_live',
            r'\(cover\)': '_cover',
            r'\(radio[_\s-]?edit\)': '_radio_edit',
            r'\(extended\)': '_extended',
            r'\(remaster(?:ed)?\)': '_remastered',
            r'\(clean\)': '_clean',
            r'\(explicit\)': '_explicit'
        }

        for pattern, suffix in special_types.items():
            if re.search(pattern, clean, re.IGNORECASE):
                if suffix not in preserved_suffix:
                    preserved_suffix += suffix
                clean = re.sub(pattern, '', clean, flags=re.IGNORECASE)

        # STEP 2: Remove common junk patterns (download/media artifacts)
        junk_patterns = [
            # Video/audio quality markers
            r'\s*[\[\(]?(?:1080p|720p|480p|2160p|4k|8k|uhd|fhd|hd)[\]\)]?',
            r'\s*[\[\(]?(?:x264|x265|h264|h265|hevc|avc)[\]\)]?',
            r'\s*[\[\(]?(?:aac|mp3|flac|wav|m4a|ogg|wma)[\]\)]?',
            r'\s*[\[\(]?(?:webrip|web-dl|brrip|bluray|blu-ray|dvdrip|hdtv)[\]\)]?',
            r'\s*[\[\(]?(?:\d+kbps|\d+mb|\d+gb)[\]\)]?',

            # Generic media labels
            r'\s*-?\s*(?:official\s+)?(?:music\s+)?(?:video|audio|lyric\s+video)',
            r'\s*-?\s*(?:hd|hq|hi-res|high\s+quality|lossless)',
            r'\s*-?\s*(?:download|free\s+download|mp3\s+download)',
            r'\s*-?\s*(?:new|latest|out\s+now|premiere)',

            # Artist credits in various formats
            r'\s*[\[\(]?(?:by|prod\.?|produced\s+by|ft\.?|feat\.?|featuring)\s+[^\]\)]+[\]\)]?',

            # Year markers
            r'\s*[\[\(]?(?:19|20)\d{2}[\]\)]?',

            # Common brackets content
            r'\s*[\[\(][^\]\)]{0,30}[\]\)]',

            # URLs and watermarks
            r'\s*(?:www\.|https?://)[^\s]+',
            r'\s*@[^\s]+',

            # Album/release type
            r'\s*-?\s*(?:full\s+album|album|single|ep|deluxe|standard)',

            # Track numbers at beginning (01-, 01., 01 )
            r'^(?:\d+[\s._-]+)+',

            # File size indicators
            r'\s*[\[\(]?\d+(?:\.\d+)?\s*(?:mb|gb|kb)[\]\)]?',
        ]

        for pattern in junk_patterns:
            clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)

        # STEP 3: Smart case handling
        # If ALL CAPS, convert to title case first
        if clean.isupper() and len(clean) > 3:
            clean = clean.title()

        # Handle camelCase/PascalCase (add underscores before caps)
        elif re.search(r'[a-z][A-Z]', clean):
            clean = re.sub(r'([a-z])([A-Z])', r'\1_\2', clean)

        # Separate letter/number boundaries (krytonite3 -> krytonite 3)
        clean = re.sub(r'([A-Za-z])(\d)', r'\1 \2', clean)
        clean = re.sub(r'(\d)([A-Za-z])', r'\1 \2', clean)

        # Now lowercase everything
        clean = clean.lower()

        # STEP 4: Normalize separators
        # Replace various separators with space
        clean = re.sub(r'[_\-\.]+', ' ', clean)

        # Remove special characters (keep only alphanumeric and spaces)
        clean = re.sub(r'[^\w\s áéíóúñü]', '', clean)

        # Collapse multiple spaces
        clean = re.sub(r'\s+', ' ', clean).strip()

        # STEP 5: Remove common filler words (but smartly)
        words = clean.split()
        if len(words) > 4:
            # Keep first and last words always, filter middle
            filler_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'from'}
            kept_words = [words[0]]
            kept_words.extend([w for w in words[1:-1] if w not in filler_words or len(w) > 3])
            kept_words.append(words[-1])
            clean = ' '.join(kept_words)

        # STEP 6: Convert to snake_case
        clean = clean.replace(' ', '_')

        # Remove multiple underscores
        clean = re.sub(r'_+', '_', clean)

        # Remove leading/trailing underscores
        clean = clean.strip('_')

        # STEP 7: Add back preserved suffixes
        clean += preserved_suffix

        # STEP 8: Final sanitization
        clean = self._sanitize_filename(clean) or ""

        # STEP 9: Quality check - if too short or lost too much, fallback
        if (not clean) or len(clean) < 3 or (len(original) > 10 and len(clean) < len(original) * 0.25):
            # Simple fallback: just normalize separators
            clean = re.sub(r'[^\w\s-]', '', original.lower())
            clean = re.sub(r'[\s-]+', '_', clean)
            clean = re.sub(r'_+', '_', clean).strip('_')
            clean = self._sanitize_filename(clean) or ""

        # If we still ended up with only digits, prefix to avoid useless numeric-only names.
        if clean.isdigit():
            clean = f"file_{clean}"

        clean = self._sanitize_filename(clean) or ""

        # STEP 10: Length limit (Windows max 255, leave room for extension)
        if len(clean) > 200:
            # Cut at word boundary
            clean = clean[:200]
            if '_' in clean:
                clean = clean.rsplit('_', 1)[0]

        return clean if clean else original.lower().replace(' ', '_')

    def categorize_visual_content(self, file_path: Path) -> Optional[str]:
        """Categorize file - FAST rule-based (AI vision too slow - 20-60 sec per image!)"""
        if not file_path.exists() or not file_path.is_file():
            return None

        try:
            ext = file_path.suffix.lower()

            # Images - fast rule-based categorization
            if ext in self.ALLOWED_EXTENSIONS:
                # GIFs are usually memes/animations
                if ext == '.gif':
                    return "meme"
                # SVG is vector art
                elif ext == '.svg':
                    return "art"
                # Check filename for hints
                elif 'screenshot' in file_path.name.lower() or 'screen' in file_path.name.lower():
                    return "screenshot_other"
                elif 'photo' in file_path.name.lower() or 'img' in file_path.name.lower() or 'camera' in file_path.name.lower():
                    return "photo"
                elif 'meme' in file_path.name.lower() or 'funny' in file_path.name.lower():
                    return "meme"
                elif 'art' in file_path.name.lower() or 'drawing' in file_path.name.lower():
                    return "art"
                # Default for images
                else:
                    return "screenshot_other"

            # Documents
            elif ext in {'.pdf', '.doc', '.docx', '.txt', '.rtf'}:
                return "document"

            # Audio
            elif ext in {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg'}:
                return "audio"

            # Video
            elif ext in {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'}:
                return "video"

            # Code/Scripts
            elif ext in {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.cs', '.go', '.rs', '.php', '.rb', '.sh', '.ps1', '.bat', '.cmd'}:
                return "code"

            # Archives
            elif ext in {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'}:
                return "archive"

            # Executables
            elif ext in {'.exe', '.msi', '.dmg', '.app', '.deb', '.rpm'}:
                return "executable"

            # Configuration
            elif ext in {'.ini', '.cfg', '.conf', '.yaml', '.yml', '.toml', '.json', '.xml'}:
                return "config"

            # Shortcuts
            elif ext in {'.lnk', '.url'}:
                return "shortcut"

            # Databases
            elif ext in {'.db', '.sqlite', '.mdb'}:
                return "database"

            else:
                return "other"

        except Exception as e:
            logger.error(f"Error categorizing file {file_path}: {e}")
            return None

    def detect_sensitive_content(self, file_path: Path) -> Dict[str, Any]:
        """Detect PII and sensitive information in images"""
        if not self.enabled:
            return {"sensitive": False, "reason": None}

        if file_path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            return {"sensitive": False, "reason": None}

        if not self._validate_file(file_path):
            return {"sensitive": False, "reason": None}

        try:
            if not self._ensure_vision_ready():
                return {"sensitive": False, "reason": None}

            image_data = self._prepare_image(file_path)
            if not image_data:
                return {"sensitive": False, "reason": None}

            prompt = """Analyze this image for sensitive information. Does it contain any of:
- Credit card numbers
- Social Security Numbers
- Passwords or API keys
- Bank account information
- Personal identification documents
- Private medical information

Respond in JSON format:
{"sensitive": true/false, "reason": "brief reason if sensitive, otherwise null"}"""

            response = self.model.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                        ]
                    }
                ],
                temperature=0.1,
                max_tokens=100
            )

            result_text = response['choices'][0]['message']['content'].strip()

            # Try to parse JSON
            try:
                result = json.loads(result_text)
            except Exception:
                try:
                    m = re.search(r"\{.*\}", result_text, flags=re.DOTALL)
                    result = json.loads(m.group(0)) if m else {}
                except Exception:
                    result = {}

            if isinstance(result, dict):
                sensitive = bool(result.get("sensitive", False))
                reason = result.get("reason")
                return {"sensitive": sensitive, "reason": str(reason) if reason else None}
            else:
                # Fallback parsing
                if "true" in result_text.lower() or "yes" in result_text.lower():
                    return {"sensitive": True, "reason": "Potential sensitive content detected"}
                return {"sensitive": False, "reason": None}

        except Exception as e:
            logger.error(f"Error detecting sensitive content in {file_path}: {e}")
            return {"sensitive": False, "reason": None}

    def extract_text_description(self, file_path: Path) -> Optional[str]:
        """Extract text content or description from image"""
        if not self.enabled:
            return None

        if not self._validate_file(file_path):
            return None

        if file_path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            return None

        if not self._ensure_vision_ready():
            return None

        try:
            image_data = self._prepare_image(file_path)
            if not image_data:
                return None

            prompt = """Describe the text content visible in this image. If there's significant text (like a document or screenshot), extract key phrases. If it's mainly visual, describe the main subject in one sentence."""

            response = self.model.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=150
            )

            description = response['choices'][0]['message']['content'].strip()
            return description or None

        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return None

    def extract_image_caption_tags(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Generate a semantic caption + search tags for an image (vision model).

        This is intended for indexing/search (e.g. IMG_0001.jpg can match "car in city").
        Returns:
            {"caption": str, "tags": [str, ...]}
        """
        if not self.enabled:
            return None

        if not self._validate_file(file_path):
            return None

        if file_path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            return None

        if not self._ensure_vision_ready():
            return None

        try:
            image_data = self._prepare_image(file_path)
            if not image_data:
                return None

            prompt = (
                "You are generating search metadata for a local file search index.\n"
                "Return ONLY valid JSON with keys: caption (string), tags (array of short strings).\n\n"
                "Rules:\n"
                "- caption: 1 sentence describing the main visible content (objects + scene).\n"
                "- tags: 6-14 lowercase keywords/phrases (1-3 words each) that help semantic search.\n"
                "- Include text that appears in the image as tags if present (e.g. 'duke energy', 'invoice').\n"
                "- If the image is a screenshot/UI, include 'screenshot' and key visible terms.\n"
                "- Do NOT guess sensitive attributes. If age is unclear, use 'person' not 'teen'.\n"
                "- Do NOT include file names/paths.\n\n"
                "JSON example:\n"
                "{\"caption\":\"a red car driving on a city street at night\",\"tags\":[\"car\",\"city street\",\"night\",\"traffic\",\"street lights\"]}"
            )

            response = self.model.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                        ],
                    }
                ],
                temperature=0.2,
                max_tokens=240,
            )

            raw = (response["choices"][0]["message"]["content"] or "").strip()
            try:
                data = json.loads(raw)
            except Exception:
                # Try to salvage JSON if the model wrapped it in text.
                try:
                    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
                    data = json.loads(m.group(0)) if m else {}
                except Exception:
                    data = {}

            caption = (data.get("caption") or "").strip()
            tags = data.get("tags")
            if not isinstance(tags, list):
                tags = []
            tags_out: list[str] = []
            for t in tags:
                if not isinstance(t, str):
                    continue
                t2 = t.strip().lower()
                if len(t2) < 2:
                    continue
                # Keep tags compact and safe.
                t2 = re.sub(r"\s+", " ", t2)
                t2 = re.sub(r"[^\w\s\-/&.]+", "", t2, flags=re.UNICODE).strip()
                if not t2:
                    continue
                if t2 not in tags_out:
                    tags_out.append(t2)
                if len(tags_out) >= 16:
                    break

            if not caption and not tags_out:
                return None

            return {"caption": caption, "tags": tags_out}

        except Exception as e:
            logger.error(f"Error generating image caption/tags for {file_path}: {e}")
            return None

    def _validate_file(self, file_path: Path) -> bool:
        """Validate file against guardrails"""
        # Check existence
        if not file_path.exists():
            return False

        # Check if it's a file (not directory)
        if not file_path.is_file():
            return False

        # Check size - only for vision processing
        if file_path.stat().st_size > self.MAX_FILE_SIZE:
            logger.warning(f"File too large for AI processing: {file_path}")
            return False

        return True

    def _prepare_image(self, file_path: Path) -> Optional[str]:
        """Prepare image for model input (resize and encode to base64)"""
        try:
            # Open and resize image to save memory
            img = Image.open(file_path)

            # Convert to RGB if needed
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Resize based on user settings (smaller = faster inference)
            max_size = self.image_size  # From settings (256-1024)
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.BILINEAR)  # Faster than LANCZOS

            # Convert to base64 with lower quality for speed
            buffered = BytesIO()
            # Slightly higher quality helps text-heavy screenshots without a big perf hit.
            img.save(buffered, format="JPEG", quality=85, optimize=False)
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            return img_base64

        except Exception as e:
            logger.error(f"Error preparing image {file_path}: {e}")
            return None

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize AI-suggested filename"""
        # Remove quotes and extra whitespace
        name = name.strip().strip('"').strip("'")

        # Replace spaces with underscores
        name = name.replace(' ', '_')

        # Remove any path separators
        name = name.replace('/', '_').replace('\\', '_')

        # Keep only safe characters
        safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.')
        name = ''.join(c if c in safe_chars else '_' for c in name)

        # Remove multiple consecutive underscores
        while '__' in name:
            name = name.replace('__', '_')

        # Limit length
        if len(name) > self.MAX_FILENAME_LENGTH:
            name = name[:self.MAX_FILENAME_LENGTH]

        # Ensure not empty - return None instead of 'unnamed_file' so caller can use fallback
        if not name or name == '_' or len(name) < 3:
            return None

        return name.lower()

    def model_files_exist(self) -> bool:
        """Check if model files exist on disk"""
        def _safe_dir_name(s: str) -> str:
            s = (s or "").strip()
            if not s:
                return "default"
            return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80] or "default"

        model_dir = self.models_folder / _safe_dir_name(self.model_id or Path(self.model_file or self.MODEL_FILE).stem)
        model_path = model_dir / (self.model_file or self.MODEL_FILE)
        mmproj_path = (model_dir / self.mmproj_file) if self.mmproj_file else None

        legacy_model = self.models_folder / (self.model_file or self.MODEL_FILE)
        legacy_mmproj = (self.models_folder / self.mmproj_file) if self.mmproj_file else None

        ok_primary = model_path.exists() and (mmproj_path is None or mmproj_path.exists())
        ok_legacy = legacy_model.exists() and (legacy_mmproj is None or legacy_mmproj.exists())
        return ok_primary or ok_legacy

    def get_status(self) -> Dict[str, Any]:
        """Get current AI manager status"""
        def _safe_dir_name(s: str) -> str:
            s = (s or "").strip()
            if not s:
                return "default"
            return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80] or "default"

        model_dir = self.models_folder / _safe_dir_name(self.model_id or Path(self.model_file or self.MODEL_FILE).stem)
        model_path = model_dir / (self.model_file or self.MODEL_FILE)
        mmproj_path = (model_dir / self.mmproj_file) if self.mmproj_file else None
        if not model_path.exists():
            model_path = self.models_folder / (self.model_file or self.MODEL_FILE)
        if mmproj_path is not None and not mmproj_path.exists():
            legacy_mmproj = (self.models_folder / self.mmproj_file) if self.mmproj_file else None
            if legacy_mmproj is not None and legacy_mmproj.exists():
                mmproj_path = legacy_mmproj

        return {
            "enabled": self.enabled,
            "backend": "llama_cpp",
            "is_ready": self.is_ready,
            "is_loading": self.is_loading,
            "load_error": self.load_error,
            "model_files_exist": self.model_files_exist(),
            "model_dir": str(model_dir),
            "model_path": str(model_path) if model_path.exists() else None,
            "mmproj_path": str(mmproj_path) if (mmproj_path is not None and mmproj_path.exists()) else None,
            "model_file": self.model_file,
            "model_repo": self.model_repo,
            "mmproj_file": self.mmproj_file,
            "chat_format": self.chat_format,
            "is_vision_model": self.is_vision_model,
        }

    def execute_with_context(
        self,
        *,
        system_prompt: str,
        user_message: str,
        context: dict | None = None,
        response_format: str = "text",
        max_tokens: int = 512,
        model_kind: str | None = None,
        temperature: float | None = None,
    ) -> dict:
        """
        Execute the LLM with a custom system prompt and optional context.
        response_format: "text" | "json"
        """
        if model_kind:
            # Auto-swap (text model for Workflow Automation / writing; vision model for image tasks).
            self.ensure_kind(str(model_kind), None)
        if not self.enabled or not self.is_ready or not self.model:
            return {"ok": False, "error": "AI model not loaded."}

        sys_prompt = str(system_prompt or "").strip()
        user_msg = str(user_message or "").strip()
        if context:
            try:
                ctx_text = json.dumps(context, indent=2, ensure_ascii=False)
            except Exception:
                ctx_text = str(context)
            user_msg = f"{user_msg}\n\nContext:\n{ctx_text}"

        if str(response_format or "").lower() == "json":
            user_msg = f"{user_msg}\n\nReturn ONLY valid JSON."

        temp = float(self.temperature if temperature is None else temperature)
        response = self.model.create_chat_completion(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=temp,
            max_tokens=int(max_tokens),
        )
        text = (response.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        return {"ok": True, "text": text}

    def unload_model(self):
        """Unload model from memory"""
        if self.model:
            try:
                del self.model
            except Exception:
                pass
            self.model = None
            self.is_ready = False
            logger.info("AI model unloaded")
