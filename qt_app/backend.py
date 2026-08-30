from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FylorraBackend:
    settings_manager: Any
    monitor_manager: Any
    ai_manager: Any
    cloud_sync_manager: Any | None = None
    device_transfer_service: Any | None = None

    loaded_monitors: list[dict] | None = None

    def get_cloud_sync_manager(self):
        if self.cloud_sync_manager is not None:
            return self.cloud_sync_manager
        from core.cloud_sync import CloudSyncManager

        self.cloud_sync_manager = CloudSyncManager(settings_manager=self.settings_manager)
        return self.cloud_sync_manager

    def get_device_transfer_service(self):
        if self.device_transfer_service is not None:
            return self.device_transfer_service
        from core.device_transfer import DeviceTransferService

        self.device_transfer_service = DeviceTransferService(self.settings_manager)
        return self.device_transfer_service

    def load(self) -> None:
        # Load saved monitors into the monitor manager, and return metadata for UI creation.
        try:
            self.loaded_monitors = self.monitor_manager.load_monitors()
        except Exception:
            self.loaded_monitors = []

        # Start scheduled tasks while app is open.
        try:
            self.monitor_manager.start_scheduled_tasks()
        except Exception:
            pass

    def shutdown(self) -> None:
        try:
            self.monitor_manager.save_monitors()
        except Exception:
            pass
        try:
            self.monitor_manager.stop_all_monitors()
        except Exception:
            pass
        try:
            self.monitor_manager.stop_scheduled_tasks()
        except Exception:
            pass
        try:
            if self.device_transfer_service is not None:
                self.device_transfer_service.stop()
        except Exception:
            pass
        try:
            if self.ai_manager and getattr(self.ai_manager, "is_ready", False):
                self.ai_manager.unload_model()
        except Exception:
            pass
        try:
            self.settings_manager.save_settings()
        except Exception:
            pass
        try:
            self.monitor_manager.logger.shutdown()
        except Exception:
            pass
