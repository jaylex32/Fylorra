import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _ThreadRecordingModel:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.lock = threading.Lock()

    def create_chat_completion(self, **kwargs):
        with self.lock:
            self.active += 1
            self.calls += 1
            self.max_active = max(self.max_active, self.active)
        try:
            return {"choices": [{"message": {"content": "ok"}}]}
        finally:
            with self.lock:
                self.active -= 1


class _FakeAI:
    MODEL_FILE = "fake-model.gguf"

    def __init__(self):
        self.enabled = True
        self.is_ready = True
        self.is_vision_model = True
        self.calls = []

    def ensure_kind(self, kind, *args, **kwargs):
        self.calls.append(("ensure_kind", kind))
        return True

    def get_active_kind(self):
        return "vision"

    def _prepare_image(self, file_path):
        return "ZmFrZV9pbWFnZQ=="

    def create_chat_completion_safe(self, **kwargs):
        self.calls.append(("chat", kwargs.get("max_tokens")))
        messages = kwargs.get("messages") or []
        text = json.dumps(messages).lower()
        if "document_type" in text or "analyze this document" in text:
            content = json.dumps(
                {
                    "document_type": "invoice",
                    "domain": "finance",
                    "entities": ["Example Office Supply"],
                    "key_date": "2026-08-31",
                    "confidence": 0.91,
                    "explanation": "Sample invoice content.",
                    "suggested_filename": "Example_Office_Supply_Invoice",
                    "suggested_category": "receipts_invoices",
                    "sensitivity": "medium",
                }
            )
        elif "classify this image" in text:
            content = "screenshot"
        else:
            content = json.dumps({"label": "receipts_invoices", "confidence": 0.93})
        return {"choices": [{"message": {"content": content}}]}

    def analyze_file_for_rename(self, file_path, use_ai=False):
        self.calls.append(("rename", Path(file_path).name, bool(use_ai)))
        stem = Path(file_path).stem
        return f"Clean_{stem}"

    def detect_sensitive_content(self, file_path):
        self.calls.append(("security", Path(file_path).name))
        return {"sensitive": "secret" in Path(file_path).name.lower(), "reason": "sample match"}


class _Settings:
    def __init__(self, app_folder):
        self.app_folder = str(app_folder)


class _Backend:
    def __init__(self, app_folder):
        self.ai_manager = _FakeAI()
        self.settings_manager = _Settings(app_folder)

class _FakeDeviceTransferService:
    def status(self):
        return {
            "running": False,
            "device_name": "Office-Test-PC",
            "inbox_dir": str(Path(tempfile.gettempdir()) / "fylorra-test-inbox"),
            "port": 47832,
            "access_code": "TEST-CODE-123",
            "local_addresses": ["127.0.0.1:47832"],
        }

    def peers(self):
        return []

    def activity(self):
        return []

    def update_config(self, **kwargs):
        return None

    def start(self):
        return True

    def stop(self):
        return None

    def rotate_access_code(self):
        return "TEST-CODE-456"


class _FakeCloudProvider:
    def is_connected(self):
        return False


class _FakeCloudSyncManager:
    token_store = object()

    def provider(self, name):
        return _FakeCloudProvider()


class _IsolatedSettings:
    def __init__(self, app_folder):
        from core.settings_manager import SettingsManager

        raw = SettingsManager.__new__(SettingsManager)
        self.settings = SettingsManager._get_default_settings(raw)
        self.app_folder = Path(app_folder)
        self.app_folder.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.app_folder / "settings.json"
        self.monitors_file = self.app_folder / "monitors.json"
        self.scheduled_tasks_file = self.app_folder / "scheduled_tasks.json"
        self.symlinks_file = self.app_folder / "symlinks.json"

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value

    def save_settings(self):
        return None

    def load_monitors(self):
        return []

    def save_monitors(self, monitors):
        return None

    def load_scheduled_tasks(self):
        return []

    def save_scheduled_tasks(self, tasks):
        return None

    def quarantine_legacy_unsafe_cleanup_tasks(self):
        return []

    def get_workflow_settings(self):
        return dict(self.settings.get("automation_workflows") or {})

    def set_workflow_setting(self, key, value):
        data = dict(self.settings.get("automation_workflows") or {})
        data[key] = value
        self.settings["automation_workflows"] = data


class AiStabilityTests(unittest.TestCase):
    def test_ai_manager_serializes_native_inference(self):
        from core.ai_manager import AIManager

        manager = AIManager.__new__(AIManager)
        manager.enabled = True
        manager.is_ready = True
        manager.model = _ThreadRecordingModel()
        manager._model_lock = threading.RLock()
        manager.load_error = None

        errors = []

        def call_model():
            try:
                manager.create_chat_completion_safe(messages=[], max_tokens=1)
            except Exception as exc:  # pragma: no cover - failure details preserved
                errors.append(exc)

        threads = [threading.Thread(target=call_model) for _ in range(25)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual([], errors)
        self.assertEqual(25, manager.model.calls)
        self.assertEqual(1, manager.model.max_active)

    def test_no_ai_feature_bypasses_safe_inference_wrapper(self):
        root = Path(__file__).resolve().parents[1]
        offenders = []
        for base in (root / "core", root / "qt_app"):
            for path in base.rglob("*.py"):
                rel = path.relative_to(root).as_posix()
                text = path.read_text(encoding="utf-8", errors="ignore")
                if rel == "core/ai_manager.py":
                    continue
                if ".model.create_chat_completion(" in text:
                    offenders.append(rel)
        self.assertEqual([], offenders)

    def test_qt_ai_hub_worker_completes_all_operations_with_sample_data(self):
        from PySide6.QtCore import QCoreApplication
        from qt_app.main_window import _QtAiHubWorker

        app = QCoreApplication.instance() or QCoreApplication([])
        _ = app

        with tempfile.TemporaryDirectory(prefix="fylorra_ai_hub_test_") as td:
            root = Path(td)
            target = root / "sample_inbox"
            target.mkdir()
            reports = root / "appdata"
            reports.mkdir()

            (target / "invoice_august.txt").write_text(
                "Invoice from Example Office Supply dated 2026-08-31 for printer paper and toner. " * 3,
                encoding="utf-8",
            )
            (target / "secret_photo.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            )
            (target / "duplicate_a.bin").write_bytes(b"same content for duplicate test")
            (target / "duplicate_b.bin").write_bytes(b"same content for duplicate test")

            backend = _Backend(reports)
            worker = _QtAiHubWorker(
                backend=backend,
                target_folder=str(target),
                operations=[
                    "smart_rename",
                    "auto_categorize",
                    "security_scan",
                    "content_analysis",
                    "duplicate_detection",
                ],
                options={
                    "apply": False,
                    "include_subfolders": True,
                    "filter_key": "all",
                    "use_vision": True,
                    "use_ai_docs": True,
                    "include_other": True,
                },
            )

            errors = []
            finished = []
            logs = []
            worker.error.connect(errors.append)
            worker.finished.connect(lambda ok, report_dir: finished.append((ok, report_dir)))
            worker.log.connect(logs.append)

            worker.run()

            self.assertEqual([], errors)
            self.assertEqual(1, len(finished))
            ok, report_dir = finished[0]
            self.assertTrue(ok)
            report_path = Path(report_dir)
            self.assertTrue((report_path / "smart_rename.json").exists())
            self.assertTrue((report_path / "auto_categorize.json").exists())
            self.assertTrue((report_path / "security_scan.json").exists())
            self.assertTrue((report_path / "content_analysis.json").exists())
            self.assertTrue((report_path / "duplicate_detection.json").exists())
            self.assertTrue(any("Smart Rename" in line for line in logs))
            self.assertTrue(any("Auto-Categorize" in line for line in logs))
            self.assertTrue(any("Duplicate Detection" in line for line in logs))

    def test_main_window_builds_every_section_with_sanitized_backend(self):
        from PySide6.QtWidgets import QApplication
        from core.monitor_manager import MonitorManager
        from qt_app.backend import FylorraBackend
        from qt_app.main_window import FylorraQtMainWindow
        from qt_app.styles import apply_app_theme

        app = QApplication.instance() or QApplication([])
        apply_app_theme(app, theme="dark", accent="blue")

        with tempfile.TemporaryDirectory(prefix="fylorra_ui_test_") as td:
            settings = _IsolatedSettings(Path(td) / "appdata")
            monitor_manager = MonitorManager(settings)
            backend = FylorraBackend(
                settings_manager=settings,
                monitor_manager=monitor_manager,
                ai_manager=_FakeAI(),
                cloud_sync_manager=_FakeCloudSyncManager(),
                device_transfer_service=_FakeDeviceTransferService(),
                loaded_monitors=[],
            )
            window = FylorraQtMainWindow(backend=backend)
            try:
                self.assertGreaterEqual(window.stack.count(), len(window.pages))
                for page in window.pages:
                    window.set_active_page(page.key)
                    self.assertEqual(page.key, window._active_page_key)
                    app.processEvents()
            finally:
                window.close()
                try:
                    backend.shutdown()
                except Exception:
                    pass

if __name__ == "__main__":
    unittest.main()