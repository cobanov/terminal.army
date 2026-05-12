"""~/.config/tarmy/credentials.json yonetimi.

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
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "tarmy" / "credentials.json"


def _normalize(url: str) -> str:
    return url.rstrip("/")


def load_all(path: Path = DEFAULT_PATH) -> dict[str, dict[str, str]]:
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
