from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PipelineContext:
    pipeline_id: str
    user_request: str
    initial_parameters: dict[str, Any]
    services: dict[str, Any]

    stage_outputs: dict[str, Any]
    stage_metadata: dict[str, dict]

    working_directory: Path
    temp_files: list[Path]

    current_stage: int
    total_stages: int
    should_abort: bool
    abort_reason: str | None

    approval_pending: bool
    approval_data: dict | None

    def get_previous_output(self, stage_id: str) -> Any:
        return self.stage_outputs.get(stage_id)

    def get_all_outputs(self) -> dict:
        return dict(self.stage_outputs or {})

    def add_temp_file(self, file_path: Path) -> None:
        try:
            self.temp_files.append(Path(file_path))
        except Exception:
            pass

    def cleanup(self) -> None:
        for fp in list(self.temp_files or []):
            try:
                if fp.exists():
                    fp.unlink()
            except Exception:
                continue
