from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from core.pipeline.pipeline import AutomationPipeline


def _pipeline_root(settings_manager=None) -> Path:
    base = Path(getattr(settings_manager, "app_folder", Path.home() / ".fylorra"))
    return base / "pipelines"


def ensure_pipeline_dirs(settings_manager=None) -> dict[str, Path]:
    root = _pipeline_root(settings_manager)
    templates = root / "templates"
    custom = root / "custom"
    executions = root / "executions"
    for p in (templates, custom, executions):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return {"root": root, "templates": templates, "custom": custom, "executions": executions}


def _builtin_templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "pipeline_templates"


def _parse_version(value: str) -> tuple[int, ...]:
    raw = str(value or "").strip()
    if not raw:
        return (0,)
    parts: list[int] = []
    for chunk in raw.split("."):
        try:
            parts.append(int(chunk))
        except Exception:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def install_builtin_templates(settings_manager=None) -> None:
    dirs = ensure_pipeline_dirs(settings_manager)
    src_dir = _builtin_templates_dir()
    if not src_dir.exists():
        return
    for src in src_dir.glob("*.json"):
        dest = dirs["templates"] / src.name
        if dest.exists():
            try:
                src_data = json.loads(src.read_text(encoding="utf-8"))
                dest_data = json.loads(dest.read_text(encoding="utf-8"))
            except Exception:
                continue
            src_meta = src_data.get("metadata") or {}
            dest_meta = dest_data.get("metadata") or {}
            src_author = str(src_meta.get("author") or "")
            dest_author = str(dest_meta.get("author") or "")
            src_ver = _parse_version(src_meta.get("version") or "0")
            dest_ver = _parse_version(dest_meta.get("version") or "0")
            if src_author and dest_author and src_author != dest_author:
                continue
            if src_ver <= dest_ver:
                continue
            try:
                dest.write_bytes(src.read_bytes())
            except Exception:
                continue
            continue
        try:
            dest.write_bytes(src.read_bytes())
        except Exception:
            continue


def load_pipelines_from_dir(folder: Path) -> list["AutomationPipeline"]:
    from core.pipeline.pipeline import AutomationPipeline

    pipelines: list[AutomationPipeline] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pipelines.append(AutomationPipeline.from_json(data))
        except Exception:
            continue
    return pipelines


def load_all_pipelines(settings_manager=None) -> list["AutomationPipeline"]:
    dirs = ensure_pipeline_dirs(settings_manager)
    install_builtin_templates(settings_manager)
    pipelines = []
    pipelines.extend(load_pipelines_from_dir(dirs["templates"]))
    pipelines.extend(load_pipelines_from_dir(dirs["custom"]))
    return pipelines


def save_custom_pipeline(pipeline: "AutomationPipeline", settings_manager=None) -> Path:
    dirs = ensure_pipeline_dirs(settings_manager)
    path = dirs["custom"] / f"{pipeline.metadata.pipeline_id}.json"
    data = pipeline.to_json()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
    return path


def save_execution(execution_id: str, payload: dict[str, Any], settings_manager=None) -> Path:
    dirs = ensure_pipeline_dirs(settings_manager)
    path = dirs["executions"] / f"{execution_id}.json"
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass
    return path
