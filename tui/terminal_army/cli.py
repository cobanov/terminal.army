"""terminal.army CLI: solo + remote + server modes, signup URL + key prompt."""

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

from terminal_army import credentials as creds

DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "tarmy"

# Default public deployment. End users don't have to configure anything;
# `tarmy` with no args connects here. Override with TA_BACKEND or --remote
# for self-hosted shards.
DEFAULT_BACKEND = "https://terminal.army"


def _backend_env() -> str | None:
    """Read backend URL from TA_BACKEND."""
    return os.environ.get("TA_BACKEND")


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
    db_path = data_dir / "tarmy.db"
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
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
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
    print(
        _color("┌─ terminal.army · sign in ", ANSI_BOLD) + _color("─" * 33, ANSI_DIM),
        file=sys.stderr,
    )
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


_GIT_INSTALL_URL = "git+https://github.com/cobanov/space-galactic-tui.git"
_PACKAGE_NAME = "terminal-army"


def _self_uninstall() -> int:
    """Fully remove the CLI: binaries, saved keys, and any solo-mode data.

    Steps:
      1. Show what will be deleted and prompt for confirmation.
      2. Delete the credential dir (~/.config/tarmy).
      3. Delete the solo data dir (~/.local/share/tarmy).
      4. Run `uv tool uninstall terminal-army` to remove the binaries.

    Each step is best-effort. If `uv` isn't on PATH we still wipe the user
    data so people can rm-rf their way out without uv installed.
    """
    import shutil
    import subprocess

    # Everything tarmy may have created on disk.
    data_paths = [
        Path.home() / ".config" / "tarmy",
        Path.home() / ".local" / "share" / "tarmy",
    ]
    existing = [p for p in data_paths if p.exists()]

    print(
        _color("This will permanently remove tarmy from your machine:", ANSI_BOLD), file=sys.stderr
    )
    print(file=sys.stderr)
    print(_color("  - the tarmy and tarmy-server commands", ANSI_DIM), file=sys.stderr)
    if existing:
        print(_color("  - saved login keys and solo-mode data:", ANSI_DIM), file=sys.stderr)
        for p in existing:
            print(_color(f"      {p}", ANSI_DIM), file=sys.stderr)
    else:
        print(_color("  - (no saved keys or solo data found)", ANSI_DIM), file=sys.stderr)
    print(file=sys.stderr)

    try:
        answer = input("Type 'yes' to confirm: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        print(_color("aborted", ANSI_YELLOW), file=sys.stderr)
        return 1
    if answer != "yes":
        print(_color("aborted", ANSI_YELLOW), file=sys.stderr)
        return 1

    # 1. Wipe user data first so even a failing uv step leaves a clean home.
    for p in existing:
        try:
            shutil.rmtree(p)
            print(_color(f"  removed {p}", ANSI_DIM), file=sys.stderr)
        except OSError as exc:
            print(_color(f"  could not remove {p}: {exc}", ANSI_YELLOW), file=sys.stderr)

    # 2. Remove the package via uv.
    uv = shutil.which("uv")
    if uv is None:
        print(
            _color(
                "uv is not on PATH; user data was wiped but the tarmy and\n"
                "tarmy-server binaries are still where you left them.\n"
                "Remove them manually, or install uv and re-run `tarmy --uninstall`.",
                ANSI_YELLOW,
            ),
            file=sys.stderr,
        )
        return 1

    cmd = [uv, "tool", "uninstall", _PACKAGE_NAME]
    print(_color(f"removing {_PACKAGE_NAME} via uv tool uninstall", ANSI_CYAN), file=sys.stderr)
    try:
        rc = subprocess.call(cmd)
    except OSError as exc:
        print(_color(f"uv failed: {exc}", ANSI_RED), file=sys.stderr)
        return 1
    if rc != 0:
        print(_color(f"uninstall failed (uv exited {rc})", ANSI_RED), file=sys.stderr)
        return rc

    print(_color("✓ tarmy fully removed. Thanks for playing.", ANSI_GREEN), file=sys.stderr)
    return 0


def _self_update() -> int:
    """Re-install the CLI from the public git URL via `uv tool install`.

    Works whether the user installed under the new (tarmy / terminal-army)
    name or the legacy aliases — `uv tool install --reinstall` rebuilds
    the active install in-place.
    """
    import shutil
    import subprocess

    uv = shutil.which("uv")
    if uv is None:
        print(
            _color(
                "uv is not on PATH — install it first:\n"
                "  curl -LsSf https://astral.sh/uv/install.sh | sh",
                ANSI_RED,
            ),
            file=sys.stderr,
        )
        return 1
    cmd = [
        uv,
        "tool",
        "install",
        "--reinstall",
        "--python",
        "3.12",
        _GIT_INSTALL_URL,
    ]
    print(_color(f"updating from {_GIT_INSTALL_URL}", ANSI_CYAN), file=sys.stderr)
    try:
        rc = subprocess.call(cmd)
    except OSError as exc:
        print(_color(f"uv failed: {exc}", ANSI_RED), file=sys.stderr)
        return 1
    if rc != 0:
        print(_color(f"update failed (uv exited {rc})", ANSI_RED), file=sys.stderr)
        return rc
    print(
        _color("✓ updated. Re-run tarmy to start the new build.", ANSI_GREEN),
        file=sys.stderr,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tarmy",
        description="terminal.army — multiplayer space strategy from your terminal",
        epilog=(
            "Default: connects to $TA_BACKEND, falling back to "
            "https://terminal.army. Solo offline: tarmy --solo."
        ),
    )
    parser.add_argument(
        "--remote",
        "-r",
        default=None,
        help="Backend URL (multiplayer). Overrides $TA_BACKEND.",
    )
    parser.add_argument(
        "--solo",
        action="store_true",
        help="Force solo mode (local SQLite). Ignores $TA_BACKEND.",
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
    parser.add_argument(
        "--update",
        action="store_true",
        help="Re-install the CLI from the public github URL and exit.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the CLI via `uv tool uninstall` and exit.",
    )
    args = parser.parse_args()

    if args.update:
        sys.exit(_self_update())
    if args.uninstall:
        sys.exit(_self_uninstall())

    # Resolution order: --remote, then $TA_BACKEND, then the public default.
    # --solo overrides everything to spin up a local sqlite backend.
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

    from terminal_army.app import TerminalArmyApp

    app = TerminalArmyApp(base_url=backend_url, token=token)
    try:
        app.run()
    except KeyboardInterrupt:
        pass


def server_main() -> None:
    """tarmy-server console script: backend only (multiplayer host)."""
    parser = argparse.ArgumentParser(
        prog="tarmy-server",
        description="terminal.army backend (multiplayer host)",
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
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{data_dir / 'tarmy.db'}"

    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
