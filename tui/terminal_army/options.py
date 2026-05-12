"""User options (theme, etc.) persisted to ~/.config/tarmy/options.json.

Separate from credentials.json so it can be checked into version control
(without secrets) or shared across hosts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path.home() / ".config" / "tarmy" / "options.json"

DEFAULT_THEME = "tarmy-dark"

# Friendly aliases that map to Textual's built-in theme names. Anything the
# user types that doesn't appear here is passed through verbatim so any new
# upstream theme works without a code change.
THEME_ALIASES = {
    "darcula": "dracula",  # JetBrains Darcula → close match
    "default": "tarmy-dark",
    "tarmy": "tarmy-dark",
    "dark": "textual-dark",
    "light": "textual-light",
}


def load(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict[str, Any], path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_theme(path: Path = DEFAULT_PATH) -> str:
    return load(path).get("theme", DEFAULT_THEME)


def set_theme(name: str, path: Path = DEFAULT_PATH) -> str:
    """Persist the theme name. Returns the resolved name (after aliasing)."""
    resolved = THEME_ALIASES.get(name.lower(), name)
    data = load(path)
    data["theme"] = resolved
    save(data, path)
    return resolved
