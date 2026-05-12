"""Sakusen CLI: solo + remote + server modes, signup URL + key prompt."""

from __future__ import annotations

import argparse
import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ogame_tui import credentials as creds

DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "sakusen"
LEGACY_DATA_DIR = Path.home() / ".local" / "share" / "ogame"

# Default public deployment. End users don't have to configure anything —
# `sakusen` with no args connects here. Override with SAKUSEN_BACKEND or
# --remote for self-hosted shards.
DEFAULT_BACKEND = "https://sakusen.space"


def _backend_env() -> str | None:
    """Read backend URL from SAKUSEN_BACKEND, falling back to legacy OGAME_BACKEND."""
    return os.environ.get("SAKUSEN_BACKEND") or os.environ.get("OGAME_BACKEND")

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"


def _color(s: str, code: str) -> str:
    if not sys.stderr.isatty():
        return s
    return f"{code}{s}{ANSI_RESET}"


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_health(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=0.5)
            if r.status_code == 200:
                return True
        except Exception as exc:
            last_err = exc
        time.sleep(0.25)
    if last_err is not None:
        print(f"backend not ready: {last_err}", file=sys.stderr)
    return False


def _spawn_local_backend(port: int, data_dir: Path) -> tuple[subprocess.Popen, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "ogame.db"
    log_path = data_dir / "server.log"

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    env.setdefault("JWT_SECRET", "solo-mode-local-secret-do-not-share")
    env.setdefault("DEFAULT_UNIVERSE_NAME", "SoloUniverse")

    log_fp = open(log_path, "a", encoding="utf-8")
    log_fp.write(f"\n--- backend start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_fp.flush()

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ],
        env=env,
        stdout=log_fp,
        stderr=log_fp,
    )
    return proc, log_path


def _shutdown(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _validate_token(backend_url: str, token: str) -> bool:
    try:
        r = httpx.get(
            f"{backend_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3.0,
        )
        return r.status_code == 200
    except Exception:
        return False


def _device_auth_flow(backend_url: str) -> str | None:
    """Device authorization flow: show URL, poll until browser auth completes."""
    try:
        r = httpx.post(f"{backend_url}/auth/start", timeout=10.0)
        r.raise_for_status()
    except Exception as exc:
        print(_color(f"failed to start auth: {exc}", ANSI_RED), file=sys.stderr)
        return None

    data = r.json()
    code = data["auth_code"]
    expires_in = int(data.get("expires_in", 600))
    interval = float(data.get("polling_interval", 2))
    url = f"{backend_url}/login?code={code}"

    print(file=sys.stderr)
    print(_color("┌─ sakusen · sign in ", ANSI_BOLD) + _color("─" * 39, ANSI_DIM), file=sys.stderr)
    print(_color("│", ANSI_DIM), file=sys.stderr)
    print(_color("│ ", ANSI_DIM) + "Open this URL in your browser:", file=sys.stderr)
    print(_color("│   ", ANSI_DIM) + _color(url, ANSI_CYAN), file=sys.stderr)
    print(_color("│", ANSI_DIM), file=sys.stderr)
    print(_color("│ ", ANSI_DIM) + "Sign in (or create an account).", file=sys.stderr)
    print(
        _color("│ ", ANSI_DIM)
        + _color(f"Timeout: {expires_in // 60}m. Press Ctrl+C to abort.", ANSI_DIM),
        file=sys.stderr,
    )
    print(_color("│", ANSI_DIM), file=sys.stderr)
    print(_color("└" + "─" * 64, ANSI_DIM), file=sys.stderr)
    print(file=sys.stderr)

    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    deadline = time.time() + expires_in
    tick = 0
    is_tty = sys.stderr.isatty()

    try:
        while time.time() < deadline:
            try:
                pr = httpx.post(
                    f"{backend_url}/auth/poll",
                    json={"auth_code": code},
                    timeout=5.0,
                )
            except Exception:
                time.sleep(interval)
                continue

            if pr.status_code == 200:
                token = pr.json().get("token")
                if not token:
                    print(_color("server returned empty token", ANSI_RED), file=sys.stderr)
                    return None
                if is_tty:
                    print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
                print(_color("✓ authentication complete", ANSI_GREEN), file=sys.stderr)
                return token
            if pr.status_code == 410:
                print(_color("auth code expired, try again", ANSI_RED), file=sys.stderr)
                return None
            # 202 pending or other: keep polling
            if is_tty:
                ch = spinner[tick % len(spinner)]
                remaining = int(deadline - time.time())
                print(
                    f"\r{_color(ch, ANSI_CYAN)} waiting for browser auth "
                    f"{_color(f'(~{remaining}s left)', ANSI_DIM)}",
                    end="",
                    file=sys.stderr,
                )
            tick += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        if is_tty:
            print(file=sys.stderr)
        print(_color("auth aborted", ANSI_YELLOW), file=sys.stderr)
        return None

    if is_tty:
        print(file=sys.stderr)
    print(_color("auth timed out", ANSI_RED), file=sys.stderr)
    return None


def _get_or_acquire_credentials(backend_url: str) -> str:
    token = creds.get_token(backend_url)
    if token and _validate_token(backend_url, token):
        return token
    new_token = _device_auth_flow(backend_url)
    if not new_token:
        sys.exit(1)
    if not _validate_token(backend_url, new_token):
        print(_color("received token failed validation", ANSI_RED), file=sys.stderr)
        sys.exit(1)
    creds.save_token(backend_url, new_token)
    print(_color(f"key saved to: {creds.DEFAULT_PATH}", ANSI_GREEN), file=sys.stderr)
    return new_token


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sakusen",
        description="sakusen — terminal-native multiplayer space strategy",
        epilog=(
            "Default: connects to $SAKUSEN_BACKEND (or legacy $OGAME_BACKEND), "
            "otherwise starts solo mode. "
            'For multiplayer: export SAKUSEN_BACKEND="http://operator-host:9931"'
        ),
    )
    parser.add_argument(
        "--remote", "-r",
        default=None,
        help="Backend URL (multiplayer). Overrides $SAKUSEN_BACKEND.",
    )
    parser.add_argument(
        "--solo",
        action="store_true",
        help="Force solo mode (local SQLite). Ignores $SAKUSEN_BACKEND.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Solo mode data directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--logout",
        action="store_true",
        help="Delete saved key for this backend and exit.",
    )
    args = parser.parse_args()

    # Resolution order: --remote, then SAKUSEN_BACKEND env, then the public
    # default. --solo overrides everything to spin up a local sqlite backend.
    remote = args.remote or (None if args.solo else (_backend_env() or DEFAULT_BACKEND))

    if args.solo:
        data_dir = Path(args.data_dir).expanduser()
        port = _find_free_port()
        print(
            _color(f"solo mode: starting local backend on 127.0.0.1:{port}", ANSI_DIM),
            file=sys.stderr,
        )
        print(_color(f"data: {data_dir}", ANSI_DIM), file=sys.stderr)

        proc, log_path = _spawn_local_backend(port, data_dir)
        atexit.register(_shutdown, proc)

        backend_url = f"http://127.0.0.1:{port}"
        if not _wait_for_health(backend_url):
            print(f"backend failed to start, see {log_path}", file=sys.stderr)
            _shutdown(proc)
            sys.exit(1)
    else:
        backend_url = remote.rstrip("/")
        if args.logout:
            creds.remove_token(backend_url)
            print(_color(f"key removed for: {backend_url}", ANSI_GREEN), file=sys.stderr)
            return
        if not _wait_for_health(backend_url, timeout=5.0):
            print(
                _color(
                    f"warning: {backend_url}/health unreachable; trying anyway",
                    ANSI_YELLOW,
                ),
                file=sys.stderr,
            )

    token = _get_or_acquire_credentials(backend_url)

    from ogame_tui.app import OGameApp
    app = OGameApp(base_url=backend_url, token=token)
    try:
        app.run()
    except KeyboardInterrupt:
        pass


def server_main() -> None:
    """sakusen-server console script: backend only (multiplayer host)."""
    parser = argparse.ArgumentParser(
        prog="sakusen-server",
        description="sakusen backend (multiplayer host)",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="SQLite data directory (only used if DATABASE_URL not set)",
    )
    parser.add_argument("--reload", action="store_true", help="dev reload")
    args = parser.parse_args()

    if "DATABASE_URL" not in os.environ:
        data_dir = Path(args.data_dir).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{data_dir / 'ogame.db'}"

    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
