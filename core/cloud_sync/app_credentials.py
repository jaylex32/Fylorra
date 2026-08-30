from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CloudAppCredentials:
    onedrive_client_id: str = ""
    onedrive_tenant: str = "common"
    gdrive_client_secrets_path: str = ""


def _app_folder() -> Path:
    p = Path.home() / ".fylorra"
    p.mkdir(exist_ok=True)
    return p


def _load_json_file(p: Path) -> dict:
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _default_secrets_locations() -> list[Path]:
    # Google client secrets are user/runtime data, not source-controlled assets.
    return [(_app_folder() / "gdrive_client_secrets.json")]


def _publisher_oauth_config_locations() -> list[Path]:
    roots: list[Path] = []
    try:
        roots.append(Path(__file__).resolve().parents[2])  # repo root
    except Exception:
        pass
    out: list[Path] = []
    # Optional files that can be bundled with the app build (do not commit secrets to source control).
    for r in roots:
        out.append(r / "assets" / "oauth" / "oauth_apps.json")
        out.append(r / "assets" / "oauth" / "onedrive_client_id.txt")
    return out


def load_app_credentials() -> CloudAppCredentials:
    """
    Resolve publisher-owned OAuth app credentials.

    Priority:
      1) Env vars (preferred for packaging):
         - FYLORRA_ONEDRIVE_CLIENT_ID
         - FYLORRA_ONEDRIVE_TENANT
         - FYLORRA_GDRIVE_CLIENT_SECRETS_PATH
      2) ~/.fylorra/oauth_apps.json:
         { "onedrive_client_id": "...", "onedrive_tenant": "common", "gdrive_client_secrets_path": "..." }
      3) User-owned default secrets file location (Google only):
         ~/.fylorra/gdrive_client_secrets.json
    """

    onedrive_client_id = str(os.getenv("FYLORRA_ONEDRIVE_CLIENT_ID", "") or "").strip()
    onedrive_tenant = str(os.getenv("FYLORRA_ONEDRIVE_TENANT", "") or "").strip() or "common"
    gdrive_path = str(os.getenv("FYLORRA_GDRIVE_CLIENT_SECRETS_PATH", "") or "").strip()

    # Publisher-bundled config (optional)
    pub_cfg: dict = {}
    for p in _publisher_oauth_config_locations():
        if p.name.lower().endswith(".json") and p.exists():
            pub_cfg = _load_json_file(p) or {}
            break
    if not onedrive_client_id:
        onedrive_client_id = str(pub_cfg.get("onedrive_client_id", "") or "").strip()
    if onedrive_tenant == "common":
        t = str(pub_cfg.get("onedrive_tenant", "") or "").strip()
        if t:
            onedrive_tenant = t
    if not gdrive_path:
        gdrive_path = str(pub_cfg.get("gdrive_client_secrets_path", "") or "").strip()

    # Publisher-bundled OneDrive client id (txt shortcut)
    if not onedrive_client_id:
        for p in _publisher_oauth_config_locations():
            if p.name.lower() == "onedrive_client_id.txt" and p.exists():
                try:
                    onedrive_client_id = p.read_text(encoding="utf-8").strip()
                except Exception:
                    pass
                break

    # User config file
    cfg = _load_json_file(_app_folder() / "oauth_apps.json")
    if not onedrive_client_id:
        onedrive_client_id = str(cfg.get("onedrive_client_id", "") or "").strip()
    if onedrive_tenant == "common":
        t = str(cfg.get("onedrive_tenant", "") or "").strip()
        if t:
            onedrive_tenant = t
    if not gdrive_path:
        gdrive_path = str(cfg.get("gdrive_client_secrets_path", "") or "").strip()

    # Default Google secrets locations
    if not gdrive_path:
        for p in _default_secrets_locations():
            if p.exists():
                gdrive_path = str(p)
                break

    return CloudAppCredentials(
        onedrive_client_id=onedrive_client_id,
        onedrive_tenant=onedrive_tenant,
        gdrive_client_secrets_path=gdrive_path,
    )


def get_onedrive_client_id(settings_manager=None) -> str:
    try:
        if settings_manager is not None:
            v = str(settings_manager.get_setting("onedrive_client_id", "") or "").strip()
            if v:
                return v
    except Exception:
        pass
    return load_app_credentials().onedrive_client_id


def get_onedrive_tenant(settings_manager=None) -> str:
    try:
        if settings_manager is not None:
            v = str(settings_manager.get_setting("onedrive_tenant", "common") or "common").strip()
            if v:
                return v
    except Exception:
        pass
    return load_app_credentials().onedrive_tenant or "common"


def get_gdrive_client_secrets_path(settings_manager=None) -> str:
    try:
        if settings_manager is not None:
            v = str(settings_manager.get_setting("gdrive_client_secrets_path", "") or "").strip()
            if v:
                return v
    except Exception:
        pass
    return load_app_credentials().gdrive_client_secrets_path
