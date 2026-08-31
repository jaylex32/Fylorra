"""Settings Manager - Handles application settings and persistence"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List

from core.branding import APP_DATA_DIR_NAME


class SettingsManager:
    """Manages application settings and data persistence"""

    def __init__(self):
        self.app_folder = Path.home() / APP_DATA_DIR_NAME
        self.app_folder.mkdir(exist_ok=True)

        self.settings_file = self.app_folder / "settings.json"
        self.monitors_file = self.app_folder / "monitors.json"
        self.scheduled_tasks_file = self.app_folder / "scheduled_tasks.json"
        self.symlinks_file = self.app_folder / "symlinks.json"

        self.settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from file"""
        if not self.settings_file.exists():
            return self._get_default_settings()

        try:
            with open(self.settings_file, 'r') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._get_default_settings()
            return self._normalize_settings(data)
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self._get_default_settings()

    def _normalize_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Merge missing defaults and migrate old unsafe AI performance defaults."""
        defaults = self._get_default_settings()
        changed = False
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
                changed = True

        # Older builds defaulted llama-cpp to GPU layers=35 and FlashAttention=auto.
        # On machines without a matching native backend this can terminate the Qt process.
        # Reset only once for pre-profile settings; users can opt back into GPU from Edit.
        try:
            profile_version = int(data.get("ai_performance_profile_version", 0) or 0)
        except Exception:
            profile_version = 0
        if profile_version < 2:
            try:
                old_gpu = int(data.get("ai_gpu_layers", 0) or 0)
            except Exception:
                old_gpu = 0
            old_flash = str(data.get("ai_flash_attn_type", "") or "").strip().lower()
            if old_gpu == 35:
                data["ai_gpu_layers"] = 0
                changed = True
            if old_flash in ("", "auto"):
                data["ai_flash_attn_type"] = "disabled"
                changed = True
            data["ai_performance_profile_version"] = 2
            changed = True

        if changed:
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(data, f, indent=4)
            except Exception:
                pass
        return data

    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default settings"""
        return {
            "theme": "dark",
            "color_theme": "blue",
            "minimize_to_tray": True,
            "start_with_windows": False,
            "notifications_enabled": True,
            "notification_sound": True,
            "show_startup_notification": True,
            "auto_start_monitors": True,
            "window_width": 1200,
            "window_height": 700,
            "language": "en",
            "media_use_gpu": False,
            "media_max_parallel": 1,
            "media_queue_autostart": False,
            "automation_workflows": {
                "max_concurrent": 1,
                "auto_start": True,
                "history_limit": 50,
                "allow_web_research": False,
                "web_max_results": 5,
                "max_output_tokens": 4096,
                # Which AI model to use for workflow automation: "auto" | "text" | "vision"
                "model_preference": "auto",
                "last_output_folder": "",
            },
            # AI settings (llama-cpp backend only)
            "ai_backend": "llama_cpp",
            # Model selection (Fylorra built-in catalog)
            # Backward compatible (legacy single-slot model keys)
            "ai_model_id": "qwen3vl-4b-q4km",
            # Backward-compatible direct fields (used by the AIManager if set explicitly)
            "ai_model_repo": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
            "ai_model_file": "Qwen3VL-4B-Instruct-Q4_K_M.gguf",
            "ai_mmproj_file": "mmproj-Qwen3VL-4B-Instruct-F16.gguf",
            "ai_chat_format": "",
            # New: separate vision + text model slots (auto-swap depending on feature use)
            "ai_vision_model_id": "qwen3vl-4b-q4km",
            "ai_vision_model_repo": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
            "ai_vision_model_file": "Qwen3VL-4B-Instruct-Q4_K_M.gguf",
            "ai_vision_mmproj_file": "mmproj-Qwen3VL-4B-Instruct-F16.gguf",
            "ai_vision_chat_format": "",
            "ai_text_model_id": "qwen3-4b-instruct-2507-q8",
            "ai_text_model_repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF",
            "ai_text_model_file": "Qwen3-4B-Instruct-2507-Q8_0.gguf",
            "ai_text_mmproj_file": "",
            "ai_text_chat_format": "qwen",
            "ai_gpu_layers": 0,
            "ai_threads": 8,
            "ai_context_size": 2048,
            "ai_batch_size": 512,
            "ai_image_size": 512,
            # llama-cpp FlashAttention: "auto" | "enabled" | "disabled"
            "ai_flash_attn_type": "disabled",
            "ai_performance_profile_version": 2,
            "ai_rename_max_keywords": 8,
            # Writing Assistant: which model to use ("auto" | "text" | "vision")
            "writing_assistant_model_preference": "text",
            # Email notification settings
            "smtp_server": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "sender_email": ""
            ,
            # Cloud Sync (OAuth credentials; tokens are stored separately)
            "onedrive_client_id": "",
            "onedrive_tenant": "common",
            "gdrive_client_secrets_path": "",
            # Device Transfer (direct PC-to-PC transfer; access code is generated on first use)
            "device_transfer": {},
        }

    def save_settings(self):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: Any):
        """Set a setting value"""
        self.settings[key] = value
        self.save_settings()

    def save_monitors(self, monitors_data: List[Dict]):
        """Save monitors configuration"""
        try:
            with open(self.monitors_file, 'w') as f:
                json.dump(monitors_data, f, indent=4)
        except Exception as e:
            print(f"Error saving monitors: {e}")

    def load_monitors(self) -> List[Dict]:
        """Load monitors configuration"""
        if not self.monitors_file.exists():
            return []

        try:
            with open(self.monitors_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading monitors: {e}")
            return []

    def save_scheduled_tasks(self, tasks: List[Dict]):
        """Save scheduled tasks configuration"""
        try:
            with open(self.scheduled_tasks_file, "w") as f:
                json.dump(tasks, f, indent=4)
        except Exception as e:
            print(f"Error saving scheduled tasks: {e}")

    def load_scheduled_tasks(self) -> List[Dict]:
        """Load scheduled tasks configuration"""
        if not self.scheduled_tasks_file.exists():
            return []
        try:
            with open(self.scheduled_tasks_file, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading scheduled tasks: {e}")
            return []

    def quarantine_legacy_unsafe_cleanup_tasks(self) -> List[str]:
        """
        Disable old FlowGuard cleanup tasks that can delete active downloads.

        Fylorra stores data under ~/.fylorra, but older builds used
        ~/.flowguard_pro. If an old build is launched later, its enabled
        clean_folder tasks can still run with unsafe empty parameters.
        """
        legacy_file = Path.home() / ".flowguard_pro" / "scheduled_tasks.json"
        if not legacy_file.exists():
            return []

        try:
            with open(legacy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        if isinstance(data, dict):
            tasks = [data]
            single = True
        elif isinstance(data, list):
            tasks = data
            single = False
        else:
            return []

        temp_paths = {
            os.path.normcase(os.path.abspath(os.environ.get("TEMP", ""))),
            os.path.normcase(os.path.abspath(os.environ.get("TMP", ""))),
            os.path.normcase(os.path.abspath(str(Path.home() / "AppData" / "Local" / "Temp"))),
        }

        changed = False
        messages: List[str] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            if not bool(task.get("enabled", True)):
                continue
            if str(task.get("action_type") or "").strip().lower() != "clean_folder":
                continue

            params = task.get("action_params") or {}
            if not isinstance(params, dict):
                params = {}
            target = str(task.get("target_path") or "").strip()
            target_norm = os.path.normcase(os.path.abspath(target)) if target else ""
            target_name = Path(target).name.lower() if target else ""
            is_temp_or_downloads = (
                target_norm in temp_paths
                or target_name in {"temp", "tmp", "downloads", "download"}
                or "\\temp\\" in target_norm
                or target_norm.endswith("\\temp")
            )
            has_download_guard = bool(params.get("skip_active_downloads", False))
            try:
                min_age = float(params.get("min_age_seconds", 0) or 0)
            except Exception:
                min_age = 0

            if is_temp_or_downloads and (not has_download_guard or min_age <= 0):
                task["enabled"] = False
                task["disabled_reason"] = (
                    "Disabled by Fylorra safety audit: legacy cleanup could delete active "
                    "downloads or fresh temp files."
                )
                changed = True
                messages.append(f"Disabled legacy unsafe cleanup task: {task.get('title') or target}")

        if changed:
            try:
                payload = tasks[0] if single else tasks
                with open(legacy_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4)
            except Exception:
                return []
        return messages

    def save_symlinks(self, links_data: List[Dict]):
        """Save user-created symbolic link records."""
        try:
            with open(self.symlinks_file, "w") as f:
                json.dump(links_data, f, indent=4)
        except Exception as e:
            print(f"Error saving symbolic links: {e}")

    def load_symlinks(self) -> List[Dict]:
        """Load user-created symbolic link records."""
        if not self.symlinks_file.exists():
            return []
        try:
            with open(self.symlinks_file, "r") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"Error loading symbolic links: {e}")
            return []

    def reset_settings(self):
        """Reset settings to defaults"""
        self.settings = self._get_default_settings()
        self.save_settings()

    def get_workflow_settings(self) -> Dict[str, Any]:
        return self.settings.get("automation_workflows", {})

    def save_workflow_settings(self, workflow_settings: Dict[str, Any]):
        self.settings["automation_workflows"] = dict(workflow_settings or {})
        self.save_settings()
