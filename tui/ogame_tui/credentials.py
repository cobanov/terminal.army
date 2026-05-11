"""~/.config/sakusen/credentials.json yonetimi.

Eski ~/.config/ogame/credentials.json varsa otomatik migrate edilir.

Format:
    {
      "servers": {
        "http://host:9931": "eyJhbGci...",
        "http://other:8000": "eyJhbGci..."
      }
    }
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "sakusen" / "credentials.json"
LEGACY_PATH = Path.home() / ".config" / "ogame" / "credentials.json"


def _migrate_legacy(path: Path = DEFAULT_PATH) -> None:
    """One-time migration: if legacy path has data and the new path is empty,
    copy the legacy file forward so users don't have to re-authenticate."""
    if path.exists() or not LEGACY_PATH.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(LEGACY_PATH, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        pass


def _normalize(url: str) -> str:
    return url.rstrip("/")


def load_all(path: Path = DEFAULT_PATH) -> dict[str, dict[str, str]]:
    _migrate_legacy(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def get_token(backend_url: str, path: Path = DEFAULT_PATH) -> str | None:
    data = load_all(path)
    return data.get("servers", {}).get(_normalize(backend_url))


def save_token(backend_url: str, token: str, path: Path = DEFAULT_PATH) -> None:
    data = load_all(path)
    servers = data.setdefault("servers", {})
    servers[_normalize(backend_url)] = token
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def remove_token(backend_url: str, path: Path = DEFAULT_PATH) -> None:
    data = load_all(path)
    servers = data.setdefault("servers", {})
    servers.pop(_normalize(backend_url), None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
