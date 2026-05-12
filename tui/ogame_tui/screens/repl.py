"""Sakusen dashboard screen (slash-command REPL)."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.suggester import Suggester
from textual.widgets import Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from ogame_tui.client import APIError

# ---------- Catalog -------------------------------------------------------
_RESOURCE_KEYS = [
    "metal_mine",
    "crystal_mine",
    "deuterium_synthesizer",
    "solar_plant",
    "fusion_reactor",
    "solar_satellite",
    "crawler",
    "metal_storage",
    "crystal_storage",
    "deuterium_tank",
]
_FACILITY_KEYS = [
    "robotics_factory",
    "shipyard",
    "research_lab",
    "alliance_depot",
    "missile_silo",
    "nanite_factory",
    "terraformer",
]
_BUILDING_KEYS = _RESOURCE_KEYS + _FACILITY_KEYS
_TECH_KEYS = [
    "energy",
    "laser",
    "ion",
    "hyperspace",
    "plasma",
    "computer",
    "astrophysics",
    "espionage",
    "combustion_drive",
    "impulse_drive",
    "hyperspace_drive",
    "weapons",
    "shielding",
    "armour",
]

# Tech tree: (parent -> children). Each node placed under its deepest
# tech parent. Drives + shielding parent to energy; hyperspace_drive
# under hyperspace; weapons, armour, computer are roots.
_TECH_CHILDREN: dict[str, list[str]] = {
    "energy": [
        "laser",
        "hyperspace",
        "combustion_drive",
        "impulse_drive",
        "shielding",
    ],
    "laser": ["ion"],
    "ion": ["plasma"],
    "hyperspace": ["hyperspace_drive"],
    "espionage": ["astrophysics"],
}
_TECH_REQS: dict[str, dict[str, int]] = {
    "energy": {"lab": 1},
    "laser": {"lab": 1, "energy": 2},
    "ion": {"lab": 4, "energy": 4, "laser": 5},
    "hyperspace": {"lab": 7, "energy": 5},
    "plasma": {"lab": 4, "energy": 8, "laser": 10, "ion": 5},
    "computer": {"lab": 1},
    "espionage": {"lab": 3},
    "astrophysics": {"lab": 3, "espionage": 4},
    "combustion_drive": {"lab": 1, "energy": 1},
    "impulse_drive": {"lab": 2, "energy": 1},
    "hyperspace_drive": {"lab": 7, "hyperspace": 3},
    "weapons": {"lab": 4},
    "shielding": {"lab": 6, "energy": 3},
    "armour": {"lab": 2},
}


@dataclass(frozen=True)
class CommandSpec:
    completion: str
    label: str
    desc: str


COMMANDS: list[CommandSpec] = [
    CommandSpec("/help", "/help", "show all commands"),
    CommandSpec("/planets", "/planets", "list my planets"),
    CommandSpec("/planet", "/planet", "current planet detail"),
    CommandSpec("/switch ", "/switch <#|CODE|name>", "change active planet"),
    CommandSpec("/buildings", "/buildings", "all buildings (resources + facilities)"),
    CommandSpec("/resources", "/resources", "mines, energy, storage, crawlers"),
    CommandSpec("/facilities", "/facilities", "industry, research, depots"),
    CommandSpec("/upgrade ", "/upgrade <type>", "upgrade a building (+1)"),
    CommandSpec("/research", "/research [type]", "list tech or upgrade one"),
    CommandSpec("/tree", "/tree", "tech tree with prereqs"),
    CommandSpec("/galaxy ", "/galaxy <g>:<s>", "galaxy system view"),
    CommandSpec("/queue", "/queue", "active build/research queue"),
    CommandSpec("/cancel ", "/cancel <id>", "cancel a queue item"),
    CommandSpec("/msg ", "/msg <user> <text>", "send a message"),
    CommandSpec("/inbox", "/inbox [user]", "conversations (or chat with user)"),
    CommandSpec("/logs", "/logs [N]", "recent activity on this planet"),
    CommandSpec("/ships", "/ships", "ships in shipyard + buildable"),
    CommandSpec("/build ", "/build <type> <n>", "build N ships in shipyard"),
    CommandSpec("/defense", "/defense", "planetary defenses + buildable"),
    CommandSpec("/defend ", "/defend <type> <n>", "build N defenses on planet"),
    CommandSpec("/fleets", "/fleets", "active fleet movements"),
    CommandSpec("/send", "/send", "fleet send wizard (see /help)"),
    CommandSpec("/espionage ", "/espionage <g>:<s>:<p>", "send probes to target"),
    CommandSpec("/attack ", "/attack <g>:<s>:<p>", "attack a target (see /help)"),
    CommandSpec("/transport ", "/transport <g>:<s>:<p>", "transport resources"),
    CommandSpec("/reports", "/reports [id]", "list reports or open one"),
    CommandSpec("/leaderboard", "/leaderboard", "server rankings"),
    CommandSpec("/alliances", "/alliances", "list alliances"),
    CommandSpec(
        "/alliance",
        "/alliance [tag|--flag]",
        "show alliance; flags: --requests --approve <u> --reject <u> --withdraw",
    ),
    CommandSpec("/found ", "/found <tag> <name>", "found a new alliance"),
    CommandSpec("/join ", "/join <tag> [msg]", "apply to join an alliance"),
    CommandSpec("/leave", "/leave", "leave your alliance"),
    CommandSpec("/me", "/me", "show my account"),
    CommandSpec("/refresh", "/refresh", "force refresh"),
    CommandSpec("/clear", "/clear", "clear log"),
    CommandSpec("/logout", "/logout", "delete key and exit"),
    CommandSpec("/quit", "/quit", "exit"),
]


HELP_TEXT = """[bold yellow]sakusen · commands[/bold yellow]

[bold]gameplay[/bold]
  /planets                list my planets
  /planet                 current planet detail
  /switch <#|CODE|name>   change active planet by number / code / name
  /buildings              all buildings (resources + facilities)
  /resources              mines, energy, storage, crawlers
  /facilities             industry, research, depots
  /upgrade <type>         upgrade a building (+1 level)
  /research               list all technologies
  /research <type>        research a technology
  /tree                   tech tree with prerequisites
  /galaxy <g>:<s>         galaxy system view (e.g. /galaxy 4:28)
  /queue                  active build/research queue
  /cancel <queue_id>      cancel a queue item (refund)

[bold]social[/bold]
  /msg                    show conversation list (alias of /inbox)
  /msg <user>             open chat history with that user
  /msg <user> <text>      send a private message
  /inbox                  list active conversations (most recent first)
  /inbox <user>           chat history with that user (WhatsApp style)
  /logs                   recent activity on current planet
  /logs <N>               last N events (default 20)

[bold]fleet & combat[/bold]
  /ships                  list ships in shipyard + buildable types
  /build <ship> <count>   construct ships at current planet's shipyard
/defense                planetary defenses + buildable structures
/defend <type> <n>      build N defenses (e.g. /defend rocket_launcher 20)
  /fleets                 active fleet movements
  /espionage <g>:<s>:<p>  send espionage probe to target
  /attack <g>:<s>:<p> <ship>:<n> ...   attack a target
  /transport <g>:<s>:<p> small_cargo:<n> m=<M> c=<C> d=<D>
  /send <mission> <g>:<s>:<p> <ship>:<n> ...   generic fleet send
  /reports                list espionage + combat reports
  /reports <id>           open one report in detail

[bold]standings[/bold]
  /leaderboard            server rankings (or /rank, /lb)
  /alliances              list all alliances
  /alliance               your alliance detail
  /alliance <tag>         alliance detail by tag
  /found <tag> <name>     found a new alliance (tag 2-6 chars)
  /join <tag> [message]   apply to join — the founder must approve
  /leave                  leave your alliance (founder must dissolve)
  /alliance --requests    founder: list pending applicants; else: your own
  /alliance --approve <u> founder: approve a join request
  /alliance --reject <u>  founder: reject a join request
  /alliance --withdraw    withdraw your own pending join request

[bold]system[/bold]
  /me                     my account info
  /refresh                force refresh all panels
  /clear                  clear the log
  /logout                 delete saved key and exit
  /quit | /q              exit

[bold]autocomplete[/bold]
  /                       open suggestion popup
  Tab                     accept highlighted suggestion
  Up / Down               navigate popup
  Esc                     close popup
  Ctrl+L                  clear log
  Ctrl+C                  quit"""


# ---------- Suggestion helpers --------------------------------------------
_LABEL_WIDTH = 22


def _make_label(name: str, desc: str) -> Text:
    txt = Text()
    txt.append(name.ljust(_LABEL_WIDTH), style="cyan")
    txt.append("  ")
    txt.append(desc, style="dim")
    return txt


def suggestions_for(
    input_text: str,
    players: list[str] | None = None,
    planets: list[dict] | None = None,
) -> list[tuple[str, Text]]:
    text = input_text.lstrip()
    if not text:
        return []

    # Slash-less input still triggers autocomplete: "queue" -> "/queue".
    # The runtime command dispatcher already strips the leading slash, so
    # both forms are equivalent at execution time.
    if not text.startswith("/"):
        text = "/" + text

    if " " in text:
        cmd, _, arg = text.partition(" ")
        cmd_l = cmd.lower()
        arg_l = arg.lower()
        if cmd_l in ("/upgrade", "/u"):
            return [
                (f"/upgrade {k}", _make_label(f"/upgrade {k}", "upgrade building"))
                for k in _BUILDING_KEYS
                if k.startswith(arg_l)
            ]
        if cmd_l in ("/research", "/r", "/res"):
            return [
                (f"/research {k}", _make_label(f"/research {k}", "research tech"))
                for k in _TECH_KEYS
                if k.startswith(arg_l)
            ]
        if cmd_l in ("/inbox", "/ib", "/in") and players:
            # Suggest only first token (username); ignore second token cases
            if " " in arg:
                return []
            return [
                (f"/inbox {u}", _make_label(f"/inbox {u}", "open conversation"))
                for u in players
                if u.lower().startswith(arg_l)
            ]
        if cmd_l in ("/msg", "/m") and players:
            if " " in arg:
                return []
            return [
                (f"/msg {u} ", _make_label(f"/msg {u} <text>", "send message"))
                for u in players
                if u.lower().startswith(arg_l)
            ]
        if cmd_l in ("/switch", "/sw") and planets:
            if " " in arg:
                return []
            out: list[tuple[str, Text]] = []
            for i, p in enumerate(planets, start=1):
                code = (p.get("code") or "").upper()
                name = p.get("name", "")
                # Code prefix
                if arg_l and code.lower().startswith(arg_l):
                    out.append(
                        (
                            f"/switch {code}",
                            _make_label(f"/switch {code}", f"{code}#{name}"),
                        )
                    )
                # Name prefix (case-insensitive)
                elif arg_l and name.lower().startswith(arg_l):
                    out.append(
                        (
                            f"/switch {name}",
                            _make_label(f"/switch {name}", f"{code}#{name}"),
                        )
                    )
                # Pure-digit arg: only suggest the matching index, if any
                elif arg.isdigit() and str(i).startswith(arg):
                    out.append(
                        (
                            f"/switch {i}",
                            _make_label(f"/switch {i}", f"{code}#{name}"),
                        )
                    )
                elif not arg_l:
                    out.append(
                        (
                            f"/switch {code}",
                            _make_label(f"/switch {code}", f"{code}#{name}"),
                        )
                    )
            return out
        return []

    if not text.startswith("/"):
        return []

    out: list[tuple[str, Text]] = []
    text_l = text.lower()
    for spec in COMMANDS:
        if spec.label.lower().startswith(text_l) or spec.completion.lower().startswith(text_l):
            out.append((spec.completion, _make_label(spec.label, spec.desc)))
    return out


# ---------- Formatters ----------------------------------------------------
def _fmt_seconds(s: int) -> str:
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"


def _fmt_int(v: float | int) -> str:
    n = int(v)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _parse_utc(iso_str: str) -> datetime:
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _local_hhmmss(iso_str: str) -> str:
    try:
        return _parse_utc(iso_str).astimezone().strftime("%H:%M:%S")
    except Exception:
        return "??:??:??"


def _remaining_str(iso_str: str) -> str:
    try:
        delta = (_parse_utc(iso_str) - datetime.now(UTC)).total_seconds()
    except Exception:
        return "?"
    if delta < 0:
        return "done"
    s = int(delta)
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m{sec:02d}s"
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m"


def _now_local_hhmmss() -> str:
    return datetime.now().strftime("%H:%M:%S")


class HistorySuggester(Suggester):
    """fish/zsh-style inline autosuggest from command history (prefix match).

    Returns the most recent history entry whose slash-normalized form begins
    with the user's input. The Input widget renders it as dim ghost text;
    Right-arrow / End / Tab accepts the rest into the buffer.
    """

    def __init__(self, history_ref) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._history_ref = history_ref

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        user_norm = value.lstrip("/").lower()
        if not user_norm:
            return None
        for h in reversed(self._history_ref()):
            h_norm = h.lstrip("/").lower()
            if h_norm == user_norm or not h_norm.startswith(user_norm):
                continue
            # Preserve user's leading-slash preference
            base = h.lstrip("/")
            return ("/" if value.startswith("/") else "") + base
        return None


def _short_dt(iso_str: str) -> str:
    """Short date for inbox: HH:MM or 'yesterday' / dd MMM."""
    try:
        dt = _parse_utc(iso_str).astimezone()
    except Exception:
        return iso_str[:16]
    now = datetime.now(dt.tzinfo)
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if (now - dt).days < 7:
        return dt.strftime("%a %H:%M")
    return dt.strftime("%d %b %H:%M")


def _nav_text() -> Text:
    """Categorized nav: PLANET / RESEARCH / FLEET / GALAXY / SOCIAL / HELP."""
    sections: list[tuple[str, list[str]]] = [
        ("PLANET", ["/planet", "/resources", "/facilities", "/upgrade", "/queue", "/cancel"]),
        ("RESEARCH", ["/research", "/tree"]),
        (
            "FLEET",
            [
                "/ships",
                "/build",
                "/defense",
                "/defend",
                "/fleets",
                "/espionage",
                "/attack",
                "/transport",
                "/reports",
            ],
        ),
        ("GALAXY", ["/galaxy", "/planets", "/switch", "/logs"]),
        ("SOCIAL", ["/msg", "/inbox"]),
        ("STANDINGS", ["/leaderboard", "/alliances", "/alliance"]),
        ("HELP", ["/help"]),
    ]
    t = Text()
    for i, (title, cmds) in enumerate(sections):
        if i > 0:
            t.append("\n")
        t.append(f"{title}\n", style="bold yellow")
        for cmd in cmds:
            # Look up the CommandSpec whose completion is exactly `cmd`
            # (no args) or `cmd ` (takes args). A naive prefix match used
            # to alias /alliance to /alliances since they share a prefix.
            spec = next(
                (s for s in COMMANDS if s.completion in (cmd, f"{cmd} ")),
                None,
            )
            label = spec.label if spec else cmd
            t.append(f"  {label}\n", style="cyan")
    t.append("\n")
    t.append("HOTKEYS\n", style="bold yellow")
    t.append("  Tab    complete\n", style="dim")
    t.append("  ↑ ↓    history\n", style="dim")
    t.append("  Esc    hide popup\n", style="dim")
    t.append("  Ctrl+L clear log\n", style="dim")
    t.append("  Ctrl+C quit\n", style="dim")
    return t


# ---------- Screen --------------------------------------------------------
class ReplScreen(Screen):
    BINDINGS = [
        Binding("ctrl+c", "app.quit", "Quit", priority=True),
        Binding("ctrl+l", "clear_log", "Clear log", show=False),
        Binding("escape", "hide_suggestions", "Hide", show=False),
        Binding("tab", "complete", "Complete", show=False, priority=True),
        Binding("up", "suggest_prev", "Prev", show=False, priority=True),
        Binding("down", "suggest_next", "Next", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    ReplScreen {
        background: #000000;
    }
    #topbar {
        height: 3;
        background: #0a0a0a;
        border-bottom: solid #262626;
    }
    #top-left {
        width: 1fr;
        height: 2;
        background: #0a0a0a;
        color: #d4d4d4;
        padding: 0 1;
    }
    #top-right {
        width: auto;
        height: 2;
        background: #0a0a0a;
        color: #d4d4d4;
        padding: 0 1;
        text-align: right;
    }
    #cols {
        height: 1fr;
        background: #000000;
    }
    #left-panel {
        width: 24;
        background: #0a0a0a;
        border-right: solid #262626;
        padding: 0 1;
    }
    #center-panel {
        width: 1fr;
        background: #000000;
    }
    #right-panel {
        width: 34;
        background: #0a0a0a;
        border-left: solid #262626;
        padding: 0 1;
    }
    #planet-card {
        height: 11;
        background: #000000;
        border-bottom: solid #262626;
        padding: 0 1;
    }
    #log {
        height: 1fr;
        background: #000000;
        padding: 0 1;
    }
    #suggestions {
        height: auto;
        max-height: 10;
        background: #0a0a0a;
        border: none;
        border-top: solid #fbbf24;
        color: #d4d4d4;
        padding: 0;
        scrollbar-size: 1 1;
    }
    #suggestions.-hidden {
        display: none;
    }
    #suggestions > .option-list--option {
        padding: 0 1;
    }
    #suggestions > .option-list--option-highlighted {
        background: #262626;
        color: #fbbf24;
    }
    #suggestions:focus > .option-list--option-highlighted {
        background: #262626;
        color: #fbbf24;
    }
    #prompt {
        background: #0a0a0a;
        color: #e5e5e5;
        border: none;
        height: 3;
    }
    Input > .input--placeholder { color: #525252; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._planets_cache: list[dict[str, Any]] = []
        self._current_suggestions: list[tuple[str, Text]] = []
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_taken_at: float = 0.0
        self._queue_cache: list[dict[str, Any]] = []
        self._unread_count: int = 0
        self._buildings_cache: dict[str, int] = {}
        self._tech_levels_cache: dict[str, int] = {}
        self._max_lab_level: int = 0
        self._players_cache: list[str] = []  # usernames for autocomplete
        self._cached_user_id: int | None = None
        # Command history (arrow-up/down + autosuggest source)
        self._history: list[str] = []
        self._history_pos: int = 0  # cursor; len == "no current entry"
        self._history_stash: str = ""  # what user was typing when nav began

    # ------- Compose ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("[dim]loading...[/dim]", id="top-left")
            yield Static("", id="top-right")
        with Horizontal(id="cols"):
            with Vertical(id="left-panel"):
                yield Static(_nav_text(), id="nav-content")
            with Vertical(id="center-panel"):
                yield Static("[dim]loading planet...[/dim]", id="planet-card")
                yield RichLog(id="log", markup=True, wrap=True, auto_scroll=True)
                yield OptionList(id="suggestions", classes="-hidden")
                yield Input(
                    placeholder="type / for commands, Tab to autocomplete, ↑ for history, /help, /q to quit",
                    id="prompt",
                    suggester=HistorySuggester(lambda: self._history),
                )
            with Vertical(id="right-panel"):
                yield Static("[dim]loading...[/dim]", id="right-content")

    def on_click(self, event: object) -> None:
        """Click anywhere on the screen refocuses the prompt.

        Nothing else on screen is meaningfully clickable (the log is
        read-only, the panels are static text). The widget that received
        the click already processed its own click logic (OptionList
        selection, etc.) before this bubbles up to the screen.
        """
        try:
            self._input.focus()
        except Exception:
            pass

    async def on_mount(self) -> None:
        self._top_left = self.query_one("#top-left", Static)
        self._top_right = self.query_one("#top-right", Static)
        self._planet_card = self.query_one("#planet-card", Static)
        self._right = self.query_one("#right-content", Static)
        self._log = self.query_one("#log", RichLog)
        self._input = self.query_one("#prompt", Input)
        self._suggestions = self.query_one("#suggestions", OptionList)

        self._log.write("[bold yellow]sakusen[/bold yellow]")
        self._log.write("[dim]Type / to see commands, Tab to autocomplete, Enter to run.[/dim]")
        self._log.write("")

        await self._refresh_planets()
        await self._refresh_dashboard()
        self._input.focus()

        self.set_interval(3.0, self._refresh_dashboard, name="refresh")
        self.set_interval(1.0, self._tick, name="tick")

    def _tick(self) -> None:
        self._render_top_bar()
        self._render_planet_card()
        self._render_right_panel()

    # ------- Auto-refresh ----------------------------------------------------
    async def _refresh_dashboard(self) -> None:
        pid = self.app.current_planet_id
        if pid is None:
            return
        try:
            self._snapshot = await self.app.client.get_planet(pid)
            self._snapshot_taken_at = monotonic()
        except APIError:
            return
        try:
            self._queue_cache = await self.app.client.get_queue(pid)
        except APIError:
            self._queue_cache = []
        try:
            blds = await self.app.client.list_buildings(pid)
            self._buildings_cache = {b["building_type"]: b["level"] for b in blds["buildings"]}
        except APIError:
            self._buildings_cache = {}
        try:
            techs = await self.app.client.list_researches()
            self._tech_levels_cache = {r["tech_type"]: r["level"] for r in techs["researches"]}
        except APIError:
            self._tech_levels_cache = {}
        self._max_lab_level = self._buildings_cache.get("research_lab", 0)
        try:
            self._unread_count = await self.app.client.unread_count()
        except APIError:
            self._unread_count = 0
        try:
            players = await self.app.client.list_players()
            me_username = self._username()
            self._players_cache = [p["username"] for p in players if p["username"] != me_username]
        except APIError:
            pass
        self._render_top_bar()
        self._render_planet_card()
        self._render_right_panel()

    def _projected(self) -> dict[str, float] | None:
        snap = self._snapshot
        if snap is None:
            return None
        elapsed_h = (monotonic() - self._snapshot_taken_at) / 3600.0
        prod = snap["production"]
        return {
            "metal": snap["resources_metal"] + prod["metal_per_hour"] * elapsed_h,
            "crystal": snap["resources_crystal"] + prod["crystal_per_hour"] * elapsed_h,
            "deuterium": snap["resources_deuterium"] + prod["deuterium_per_hour"] * elapsed_h,
        }

    def _render_top_bar(self) -> None:
        snap = self._snapshot
        if snap is None:
            self._top_left.update("[dim]loading...[/dim]")
            self._top_right.update("")
            return
        proj = self._projected() or {
            "metal": snap["resources_metal"],
            "crystal": snap["resources_crystal"],
            "deuterium": snap["resources_deuterium"],
        }
        prod = snap["production"]
        en = snap["energy"]
        bal_style = "green" if en["balance"] >= 0 else "red"

        # --- LEFT: player/universe/planet on line 1, resources on line 2
        sep = Text(" · ", style="dim")
        line1 = Text()
        line1.append(self._username(), style="bold yellow")
        line1.append_text(sep)
        line1.append(f"U#{snap['universe_id']}", style="cyan")
        line1.append_text(sep)
        line1.append(
            f"{snap['name']} {snap['galaxy']}:{snap['system']}:{snap['position']}",
            style="bold yellow",
        )
        line1.append_text(sep)
        line1.append(
            f"fields {snap['fields_used']}/{snap['fields_total']}",
            style="dim",
        )
        line1.append_text(sep)
        line1.append(f"temp {snap['temp_min']}/{snap['temp_max']}°C", style="dim")

        line2 = Text()
        line2.append("M ", style="bold yellow")
        line2.append(_fmt_int(proj["metal"]), style="yellow")
        line2.append("  C ", style="bold cyan")
        line2.append(_fmt_int(proj["crystal"]), style="cyan")
        line2.append("  D ", style="bold magenta")
        line2.append(_fmt_int(proj["deuterium"]), style="magenta")
        line2.append(
            f"  +{prod['metal_per_hour']:.0f}/{prod['crystal_per_hour']:.0f}/"
            f"{prod['deuterium_per_hour']:.0f}/h",
            style="dim",
        )
        line2.append("  E ", style="bold")
        line2.append(f"{en['balance']:+d}", style=bal_style)
        line2.append(f" ({en['production_factor']:.2f}x)", style="dim")

        left = Text()
        left.append_text(line1)
        left.append("\n")
        left.append_text(line2)
        self._top_left.update(left)

        # --- RIGHT: clock on line 1, unread on line 2 (right-aligned by CSS)
        right = Text()
        right.append(_now_local_hhmmss(), style="bold green")
        right.append("\n")
        if self._unread_count > 0:
            right.append(f"✉ {self._unread_count} unread", style="bold magenta")
        else:
            right.append("✉ inbox", style="dim")
        self._top_right.update(right)

    def _render_planet_card(self) -> None:
        snap = self._snapshot
        if snap is None:
            self._planet_card.update("[dim]loading...[/dim]")
            return
        proj = self._projected() or {
            "metal": snap["resources_metal"],
            "crystal": snap["resources_crystal"],
            "deuterium": snap["resources_deuterium"],
        }
        prod = snap["production"]
        en = snap["energy"]
        bal_style = "green" if en["balance"] >= 0 else "red"

        body = Text()
        body.append(f"{snap['name'].upper()} ", style="bold yellow")
        body.append(f"{snap['galaxy']}:{snap['system']}:{snap['position']}\n", style="yellow")
        body.append(
            f"fields {snap['fields_used']}/{snap['fields_total']}   "
            f"temp {snap['temp_min']}/{snap['temp_max']}°C\n\n",
            style="dim",
        )
        body.append("  metal    ", style="bold")
        body.append(f"{_fmt_int(proj['metal']):>10}", style="yellow")
        body.append(f"   +{prod['metal_per_hour']:.0f}/h\n", style="dim")
        body.append("  crystal  ", style="bold")
        body.append(f"{_fmt_int(proj['crystal']):>10}", style="cyan")
        body.append(f"   +{prod['crystal_per_hour']:.0f}/h\n", style="dim")
        body.append("  deut     ", style="bold")
        body.append(f"{_fmt_int(proj['deuterium']):>10}", style="magenta")
        body.append(f"    +{prod['deuterium_per_hour']:.0f}/h\n", style="dim")
        body.append("\n  energy   ", style="bold")
        body.append(f"prod {en['produced']} / used {en['consumed']}   ")
        body.append(f"bal {en['balance']:+d}", style=bal_style)
        body.append(f"  ({en['production_factor']:.2f}x)", style="dim")
        if en["production_factor"] < 1.0:
            body.append("\n  ", style="")
            body.append("⚠ ", style="bold red")
            body.append("energy deficit", style="bold red")
            body.append(" — mines throttled to ", style="red")
            body.append(f"{en['production_factor'] * 100:.0f}%", style="bold red")
            body.append("; build a solar plant", style="red")
        self._planet_card.update(body)

    def _render_right_panel(self) -> None:
        if self.app.current_planet_id is None:
            self._right.update("[dim]no planet[/dim]")
            return
        body = Text()

        # PLANETS — primary section now
        body.append("PLANETS\n", style="bold yellow")
        cur_id = self.app.current_planet_id
        for i, p in enumerate(self._planets_cache, start=1):
            marker = "▸ " if p["id"] == cur_id else "  "
            style = "bold yellow" if p["id"] == cur_id else "cyan"
            body.append(marker, style=style)
            body.append(f"{i}. ", style="dim")
            body.append(p.get("code", "—"), style="magenta")
            body.append("#", style="dim")
            body.append(f"{p['name']}\n", style=style)
            body.append(
                f"     {p['galaxy']}:{p['system']}:{p['position']}  "
                f"M {_fmt_int(p['resources_metal'])}\n",
                style="dim",
            )
        body.append("\nswitch: ", style="dim")
        body.append("/switch <#|CODE|name>\n", style="yellow")

        # QUEUE — compact
        queue = self._queue_cache
        body.append(f"\nQUEUE ({len(queue)}/5)\n", style="bold yellow")
        if not queue:
            body.append("  empty\n", style="dim")
        else:
            for q in queue[:3]:  # show first 3
                remaining = _remaining_str(q["finished_at"])
                body.append(f"  #{q['id']} ", style="cyan")
                body.append(f"{q['item_key']}\n", style="dim")
                rem_style = "green" if remaining != "done" else "dim"
                body.append(f"    {remaining}\n", style=rem_style)
            if len(queue) > 3:
                body.append(f"  +{len(queue) - 3} more\n", style="dim")

        # Compact one-liner for messages
        body.append("\nMESSAGES  ", style="bold yellow")
        if self._unread_count == 0:
            body.append("(none)\n", style="dim")
        else:
            body.append(f"{self._unread_count} new", style="bold magenta")
            body.append(" /inbox\n", style="dim")
        self._right.update(body)

    def _username(self) -> str:
        try:
            me = getattr(self.app, "me_info", None)
            if me:
                return str(me.get("username", "?"))
        except Exception:
            pass
        return "?"

    # ------- Suggestions / autocomplete --------------------------------------
    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "prompt":
            return
        self._update_suggestions(event.value)

    def _update_suggestions(self, text: str) -> None:
        items = suggestions_for(text, players=self._players_cache, planets=self._planets_cache)
        self._current_suggestions = items
        self._suggestions.clear_options()
        if not items:
            self._suggestions.add_class("-hidden")
            return
        self._suggestions.add_options(
            [Option(label, id=str(i)) for i, (_, label) in enumerate(items)]
        )
        self._suggestions.remove_class("-hidden")
        try:
            self._suggestions.highlighted = 0
            self._scroll_highlighted_into_view()
        except Exception:
            pass

    def _suggestions_visible(self) -> bool:
        return "-hidden" not in self._suggestions.classes

    def _scroll_highlighted_into_view(self) -> None:
        try:
            self._suggestions.scroll_to_highlight()
        except Exception:
            pass

    async def action_complete(self) -> None:
        if not self._suggestions_visible() or not self._current_suggestions:
            return
        idx = self._suggestions.highlighted or 0
        if idx < 0 or idx >= len(self._current_suggestions):
            return
        completion = self._current_suggestions[idx][0]
        self._input.value = completion
        self._input.cursor_position = len(completion)
        self._update_suggestions(completion)

    async def action_suggest_next(self) -> None:
        # Popup visible -> navigate suggestions
        if self._suggestions_visible():
            n = len(self._current_suggestions)
            if n == 0:
                return
            cur = self._suggestions.highlighted
            cur = 0 if cur is None else cur
            self._suggestions.highlighted = (cur + 1) % n
            self._scroll_highlighted_into_view()
            return
        # Popup hidden -> history forward
        self._history_forward()

    async def action_suggest_prev(self) -> None:
        # Popup visible -> navigate suggestions
        if self._suggestions_visible():
            n = len(self._current_suggestions)
            if n == 0:
                return
            cur = self._suggestions.highlighted
            cur = 0 if cur is None else cur
            self._suggestions.highlighted = (cur - 1) % n
            self._scroll_highlighted_into_view()
            return
        # Popup hidden -> history back
        self._history_back()

    # ------- Command history -------------------------------------------------
    def _history_back(self) -> None:
        """↑ when popup hidden: cycle backward through history."""
        if not self._history:
            return
        if self._history_pos >= len(self._history):
            # First time pressing up: stash current input so ↓↓ can return
            self._history_stash = self._input.value
            self._history_pos = len(self._history) - 1
        elif self._history_pos > 0:
            self._history_pos -= 1
        self._input.value = self._history[self._history_pos]
        self._input.cursor_position = len(self._input.value)

    def _history_forward(self) -> None:
        """↓ when popup hidden: cycle forward in history (or back to stash)."""
        if not self._history:
            return
        if self._history_pos >= len(self._history):
            return  # already past end
        self._history_pos += 1
        if self._history_pos >= len(self._history):
            self._input.value = self._history_stash
        else:
            self._input.value = self._history[self._history_pos]
        self._input.cursor_position = len(self._input.value)

    def _push_history(self, cmd: str) -> None:
        # Dedupe consecutive duplicates
        if not cmd:
            return
        if self._history and self._history[-1] == cmd:
            self._history_pos = len(self._history)
            self._history_stash = ""
            return
        self._history.append(cmd)
        # Bound history size
        if len(self._history) > 500:
            self._history = self._history[-500:]
        self._history_pos = len(self._history)
        self._history_stash = ""

    def action_hide_suggestions(self) -> None:
        self._suggestions.add_class("-hidden")

    async def action_clear_log(self) -> None:
        self._log.clear()

    # ------- Input submit ----------------------------------------------------
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        self._suggestions.add_class("-hidden")
        self._current_suggestions = []
        if not raw:
            return
        self._push_history(raw)
        self._log.write(f"[bold yellow]>[/bold yellow] {raw}")
        try:
            await self._handle(raw)
        except APIError as exc:
            self._log.write(f"[red]error {exc.status_code}:[/red] {exc.detail}")
        except Exception as exc:
            self._log.write(f"[red]exception:[/red] {exc!r}")
        await self._refresh_dashboard()

    async def _handle(self, raw: str) -> None:
        if raw.startswith("/"):
            raw = raw[1:]
        try:
            parts = shlex.split(raw)
        except ValueError:
            parts = raw.split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        aliases = {
            "q": "quit",
            "exit": "quit",
            "h": "help",
            "?": "help",
            "p": "planet",
            "ps": "planets",
            "b": "buildings",
            "bld": "buildings",
            "rs": "resources",
            "fc": "facilities",
            "fac": "facilities",
            "u": "upgrade",
            "r": "research",
            "res": "research",
            "g": "galaxy",
            "qu": "queue",
            "m": "msg",
            "in": "inbox",
            "ib": "inbox",
            "t": "tree",
            "l": "logs",
            "log": "logs",
            "activity": "logs",
            "sh": "ships",
            "shp": "ships",
            "bs": "build",
            "def": "defense",
            "defs": "defense",
            "dfd": "defend",
            "f": "fleets",
            "fl": "fleets",
            "esp": "espionage",
            "spy": "espionage",
            "atk": "attack",
            "trans": "transport",
            "tx": "transport",
            "rep": "reports",
            "lb": "leaderboard",
            "rank": "leaderboard",
            "ranking": "leaderboard",
            "ally": "alliance",
            "all": "alliances",
        }
        cmd = aliases.get(cmd, cmd)

        handler = getattr(self, f"_cmd_{cmd}", None)
        if handler is None:
            self._log.write(f"[red]unknown command:[/red] {cmd}  [dim](type /help)[/dim]")
            return
        await handler(args)

    # ------- Commands --------------------------------------------------------
    async def _cmd_help(self, args: list[str]) -> None:
        self._log.write(HELP_TEXT)

    async def _cmd_quit(self, args: list[str]) -> None:
        self.app.exit()

    async def _cmd_clear(self, args: list[str]) -> None:
        self._log.clear()

    async def _cmd_me(self, args: list[str]) -> None:
        me = await self.app.client.me()
        self._cached_user_id = int(me["id"])
        self._log.write(
            f"[bold]{me['username']}[/bold] [dim]<{me['email']}>[/dim] "
            f"universe={me.get('current_universe_id')}"
        )

    async def _me_user_id(self) -> int:
        if self._cached_user_id is None:
            me = await self.app.client.me()
            self._cached_user_id = int(me["id"])
        return self._cached_user_id

    async def _cmd_logout(self, args: list[str]) -> None:
        from ogame_tui import credentials as creds

        creds.remove_token(self.app.client.base_url)
        self._log.write("[green]key deleted, exiting.[/green]")
        self.app.exit()

    async def _cmd_planets(self, args: list[str]) -> None:
        await self._refresh_planets()
        if not self._planets_cache:
            self._log.write("[dim]no planets[/dim]")
            return
        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("#", style="cyan", justify="right")
        t.add_column("code", style="magenta")
        t.add_column("name")
        t.add_column("coord")
        t.add_column("metal", justify="right")
        t.add_column("crystal", justify="right")
        t.add_column("deut", justify="right")
        cur = self.app.current_planet_id
        for i, p in enumerate(self._planets_cache, start=1):
            marker = "[green]*[/green]" if p["id"] == cur else " "
            t.add_row(
                f"{marker}{i}",
                p.get("code", "—"),
                p["name"],
                f"{p['galaxy']}:{p['system']}:{p['position']}",
                _fmt_int(p["resources_metal"]),
                _fmt_int(p["resources_crystal"]),
                _fmt_int(p["resources_deuterium"]),
            )
        self._log.write(t)
        self._log.write("[dim]switch by[/dim] [yellow]/switch <#|CODE|name>[/yellow]")

    def _resolve_planet(self, arg: str) -> dict | None:
        """Match a planet by per-user number, code, or name (prefix/exact).

        Returns the planet dict from `_planets_cache`, or None.
        """
        if not self._planets_cache:
            return None
        # 1) per-user number (1-based)
        if arg.isdigit():
            idx = int(arg)
            if 1 <= idx <= len(self._planets_cache):
                return self._planets_cache[idx - 1]
            return None
        upper = arg.upper()
        # 2) exact code match
        for p in self._planets_cache:
            if (p.get("code") or "").upper() == upper:
                return p
        # 3) name: exact (case-insensitive) wins, otherwise unique prefix.
        lower = arg.lower()
        exact = [p for p in self._planets_cache if p["name"].lower() == lower]
        if len(exact) == 1:
            return exact[0]
        prefix = [p for p in self._planets_cache if p["name"].lower().startswith(lower)]
        if len(prefix) == 1:
            return prefix[0]
        return None

    async def _cmd_switch(self, args: list[str]) -> None:
        if not args:
            self._log.write("[red]usage:[/red] /switch <number | CODE | name>")
            return
        await self._refresh_planets()
        target = self._resolve_planet(args[0])
        if target is None:
            candidates = (
                ", ".join(f"{p.get('code', '?')}#{p['name']}" for p in self._planets_cache)
                or "(no planets)"
            )
            self._log.write(
                f"[red]no match for[/red] [yellow]{args[0]}[/yellow]  "
                f"[dim]try one of:[/dim] {candidates}"
            )
            return
        self.app.current_planet_id = target["id"]
        self._log.write(
            f"[green]active planet:[/green] "
            f"[magenta]{target.get('code', '—')}[/magenta]"
            f"[dim]#[/dim]{target['name']} "
            f"[dim]({target['galaxy']}:{target['system']}:{target['position']})[/dim]"
        )

    async def _cmd_planet(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        p = await self.app.client.get_planet(pid)
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style="cyan", justify="right")
        t.add_column()
        t.add_row("name", p["name"])
        t.add_row("coord", f"{p['galaxy']}:{p['system']}:{p['position']}")
        t.add_row("temp", f"{p['temp_min']} / {p['temp_max']} °C")
        t.add_row("fields", f"{p['fields_used']} / {p['fields_total']}")
        t.add_row(
            "resources",
            f"M [yellow]{_fmt_int(p['resources_metal'])}[/yellow] "
            f"C [cyan]{_fmt_int(p['resources_crystal'])}[/cyan] "
            f"D [magenta]{_fmt_int(p['resources_deuterium'])}[/magenta]",
        )
        prod = p["production"]
        t.add_row(
            "rate/h",
            f"M {prod['metal_per_hour']:.1f}  "
            f"C {prod['crystal_per_hour']:.1f}  "
            f"D {prod['deuterium_per_hour']:.1f}",
        )
        en = p["energy"]
        bal_color = "green" if en["balance"] >= 0 else "red"
        t.add_row(
            "energy",
            f"prod {en['produced']}  used {en['consumed']}  "
            f"bal [{bal_color}]{en['balance']:+d}[/{bal_color}]  "
            f"factor {en['production_factor']:.2f}",
        )
        self._log.write(t)

    async def _render_buildings(self, title: str, keys: list[str] | None = None) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        data = await self.app.client.list_buildings(pid)
        snap = self._snapshot or {}
        cur_m = snap.get("resources_metal", 0)
        cur_c = snap.get("resources_crystal", 0)
        cur_d = snap.get("resources_deuterium", 0)

        self._log.write(f"[bold yellow]{title}[/bold yellow]")
        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("building")
        t.add_column("lvl", justify="right")
        t.add_column("metal", justify="right")
        t.add_column("crystal", justify="right")
        t.add_column("deut", justify="right")
        t.add_column("time")
        # If a key list is supplied, render in that exact order; otherwise
        # render server order so legacy /buildings keeps its layout.
        if keys is not None:
            by_key = {b["building_type"]: b for b in data["buildings"]}
            rows = [by_key[k] for k in keys if k in by_key]
        else:
            rows = data["buildings"]
        for b in rows:
            cm, cc, cd = b["next_cost_metal"], b["next_cost_crystal"], b["next_cost_deuterium"]
            affordable = cur_m >= cm and cur_c >= cc and cur_d >= cd
            style = "" if affordable else "dim"
            name_style = "bold" if affordable else "dim"
            t.add_row(
                Text(b["building_type"], style=name_style),
                Text(str(b["level"]), style=style or "cyan"),
                Text(_fmt_int(cm), style=style or ("yellow" if cur_m >= cm else "red")),
                Text(_fmt_int(cc), style=style or ("cyan" if cur_c >= cc else "red")),
                Text(_fmt_int(cd), style=style or ("magenta" if cur_d >= cd else "red")),
                Text(_fmt_seconds(b["next_build_seconds"]), style=style or ""),
            )
        self._log.write(t)

    async def _cmd_buildings(self, args: list[str]) -> None:
        await self._render_buildings("all buildings")

    async def _cmd_resources(self, args: list[str]) -> None:
        await self._render_buildings("resources", _RESOURCE_KEYS)

    async def _cmd_facilities(self, args: list[str]) -> None:
        await self._render_buildings("facilities", _FACILITY_KEYS)

    async def _cmd_upgrade(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        if not args:
            self._log.write(
                "[red]usage:[/red] /upgrade <building_type>  (e.g. /upgrade metal_mine)"
            )
            return
        bt = args[0].lower()
        if bt not in _BUILDING_KEYS:
            self._log.write(f"[red]unknown building:[/red] {bt}  [dim]/buildings to list[/dim]")
            return
        r = await self.app.client.upgrade_building(pid, bt)
        self._log.write(
            f"[green]queued[/green] {r['item_key']} -> L{r['target_level']}  "
            f"cost {r['cost_metal']}/{r['cost_crystal']}/{r['cost_deuterium']}  "
            f"done at [cyan]{_local_hhmmss(r['finished_at'])}[/cyan] "
            f"([dim]{_remaining_str(r['finished_at'])}[/dim])"
        )

    async def _cmd_research(self, args: list[str]) -> None:
        if args:
            await self._upgrade_research(args[0].lower())
            return
        data = await self.app.client.list_researches()
        snap = self._snapshot or {}
        cur_m = snap.get("resources_metal", 0)
        cur_c = snap.get("resources_crystal", 0)
        cur_d = snap.get("resources_deuterium", 0)

        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("tech")
        t.add_column("lvl", justify="right")
        t.add_column("metal", justify="right")
        t.add_column("crystal", justify="right")
        t.add_column("deut", justify="right")
        t.add_column("status")
        for r in data["researches"]:
            cm, cc, cd = r["next_cost_metal"], r["next_cost_crystal"], r["next_cost_deuterium"]
            ok_prereq = r["prereq_met"]
            ok_cost = cur_m >= cm and cur_c >= cc and cur_d >= cd
            available = ok_prereq and ok_cost
            base_style = "" if available else "dim"
            if not ok_prereq:
                status = Text("locked: " + ", ".join(r["prereq_missing"])[:40], style="red")
            elif not ok_cost:
                status = Text("need resources", style="yellow")
            else:
                status = Text("ready", style="green")
            t.add_row(
                Text(r["tech_type"], style="bold" if available else "dim"),
                Text(str(r["level"]), style=base_style or "cyan"),
                Text(_fmt_int(cm), style=base_style or "yellow"),
                Text(_fmt_int(cc), style=base_style or "cyan"),
                Text(_fmt_int(cd), style=base_style or "magenta"),
                status,
            )
        self._log.write(t)

    async def _upgrade_research(self, tech: str) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        if tech not in _TECH_KEYS:
            self._log.write(f"[red]unknown tech:[/red] {tech}  [dim]/research to list[/dim]")
            return
        r = await self.app.client.upgrade_research(tech, pid)
        self._log.write(
            f"[green]researching[/green] {r['item_key']} -> L{r['target_level']}  "
            f"cost {r['cost_metal']}/{r['cost_crystal']}/{r['cost_deuterium']}  "
            f"done at [cyan]{_local_hhmmss(r['finished_at'])}[/cyan] "
            f"([dim]{_remaining_str(r['finished_at'])}[/dim])"
        )

    async def _cmd_tree(self, args: list[str]) -> None:
        """Render tech tree with prerequisites; lock unmet ones (dim)."""
        levels = self._tech_levels_cache
        max_lab = self._max_lab_level

        def _node_available(t: str) -> tuple[bool, list[str]]:
            reqs = _TECH_REQS.get(t, {})
            missing: list[str] = []
            for k, v in reqs.items():
                if k == "lab":
                    if max_lab < v:
                        missing.append(f"Lab L{v}")
                else:
                    if levels.get(k, 0) < v:
                        missing.append(f"{k} L{v}")
            return len(missing) == 0, missing

        out = Text()
        out.append("TECH TREE", style="bold yellow")
        out.append(f"   (Research Lab max: L{max_lab})\n\n", style="dim")

        def render(node: str, depth: int, is_last: bool = False) -> None:
            indent = ""
            if depth > 0:
                indent = "  " * (depth - 1) + ("└─ " if is_last else "├─ ")
            lvl = levels.get(node, 0)
            available, missing = _node_available(node)

            # Status marker + name
            if lvl > 0:
                marker, name_style, lvl_style = "✓", "bold green", "cyan"
            elif available:
                marker, name_style, lvl_style = "○", "yellow", "yellow"
            else:
                marker, name_style, lvl_style = " ", "dim", "dim"

            out.append(indent)
            out.append(f"{marker} ", style=name_style)
            out.append(node, style=name_style)
            out.append(f" L{lvl}", style=lvl_style)

            # Show requirements only when not yet researched AND locked
            if lvl == 0 and not available and missing:
                out.append("   needs ", style="dim")
                out.append(", ".join(missing), style="dim yellow")
            out.append("\n")

            children = _TECH_CHILDREN.get(node, [])
            for i, child in enumerate(children):
                render(child, depth + 1, is_last=(i == len(children) - 1))

        roots = [
            tt for tt in _TECH_KEYS if not any(k != "lab" for k in _TECH_REQS.get(tt, {}).keys())
        ]
        for i, tt in enumerate(roots):
            render(tt, 0, is_last=(i == len(roots) - 1))

        self._log.write(out)
        # Legend as a separate markup-parsed line
        self._log.write(
            "[dim]Legend:[/dim] [bold green]✓ done[/bold green]   "
            "[yellow]○ available[/yellow]   [dim]locked[/dim]   "
            "[dim yellow]needs ...[/dim yellow] missing prereq"
        )

    async def _cmd_galaxy(self, args: list[str]) -> None:
        if not args:
            self._log.write("[red]usage:[/red] /galaxy <galaxy>:<system>  (e.g. /galaxy 4:28)")
            return
        try:
            galaxy_str, system_str = args[0].split(":")
            g = int(galaxy_str)
            s = int(system_str)
        except ValueError:
            self._log.write("[red]format error:[/red] /galaxy 4:28")
            return
        uid = self.app.current_universe_id
        data = await self.app.client.view_galaxy(uid, g, s)
        t = Table(show_header=True, header_style="bold yellow", box=None, title=f"galaxy {g}:{s}")
        t.add_column("pos", justify="right", style="cyan")
        t.add_column("planet")
        t.add_column("owner")
        for slot in data["slots"]:
            name = slot["planet_name"] or "[dim]-[/dim]"
            owner = slot["owner_username"] or "[dim]-[/dim]"
            t.add_row(str(slot["position"]), name, owner)
        self._log.write(t)

    async def _cmd_queue(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        items = await self.app.client.get_queue(pid)
        if not items:
            self._log.write("[dim]queue empty[/dim]")
            return
        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("id", style="bold yellow")
        t.add_column("type")
        t.add_column("item")
        t.add_column("->lvl", justify="right")
        t.add_column("done at (local)")
        t.add_column("remaining")
        for q in items:
            t.add_row(
                str(q["id"]),
                q["queue_type"],
                q["item_key"],
                str(q["target_level"]),
                _local_hhmmss(q["finished_at"]),
                _remaining_str(q["finished_at"]),
            )
        self._log.write(t)
        self._log.write(
            "[dim]cancel one with[/dim] [yellow]/cancel <id>[/yellow] "
            "[dim](refunds full cost)[/dim]"
        )

    async def _cmd_cancel(self, args: list[str]) -> None:
        if not args:
            self._log.write("[red]usage:[/red] /cancel <queue_id>")
            return
        try:
            qid = int(args[0])
        except ValueError:
            self._log.write("[red]id must be integer[/red]")
            return
        r = await self.app.client.cancel_queue(qid)
        self._log.write(
            f"[green]cancelled[/green] {r['item_key']}  "
            f"refund {r['cost_metal']}/{r['cost_crystal']}/{r['cost_deuterium']}"
        )

    # ------- Leaderboard / Alliance --------------------------------------
    async def _cmd_leaderboard(self, args: list[str]) -> None:
        data = await self.app.client.leaderboard(limit=100)
        my_username = self._username()
        my_rank = data.get("my_rank")
        my_total = data.get("my_total") or 0
        rows = data["rows"]
        in_top = any(r["username"] == my_username for r in rows)

        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("#", justify="right", style="dim")
        t.add_column("player", style="bold")
        t.add_column("ally", style="cyan")
        t.add_column("buildings", justify="right", style="dim")
        t.add_column("research", justify="right", style="dim")
        t.add_column("fleet", justify="right", style="dim")
        t.add_column("total", justify="right", style="bold yellow")
        for r in rows:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["rank"], str(r["rank"]))
            name = r["username"]
            if name == my_username:
                name = f"[bold green]{name}[/bold green]"
            ally = f"[{r['alliance_tag']}]" if r.get("alliance_tag") else "-"
            t.add_row(
                medal,
                name,
                ally,
                _fmt_int(r["building_points"]),
                _fmt_int(r["research_points"]),
                _fmt_int(r["fleet_points"]),
                _fmt_int(r["total_points"]),
            )
        # If I'm not in the top 100, append a divider + my row at the bottom.
        if not in_top and my_rank is not None:
            t.add_row("[dim]⋮[/dim]", "", "", "", "", "", "")
            t.add_row(
                str(my_rank),
                f"[bold green]{my_username}[/bold green]",
                "-",
                "",
                "",
                "",
                _fmt_int(my_total),
            )
        self._log.write(t)
        if my_rank is not None:
            self._log.write(
                f"[dim]your rank:[/dim] [bold yellow]#{my_rank}[/bold yellow] "
                f"of {data['total_players']}  "
                f"[dim]({_fmt_int(my_total)} pts)[/dim]"
            )

    async def _cmd_alliances(self, args: list[str]) -> None:
        rows = await self.app.client.list_alliances()
        my = await self.app.client.my_alliance()
        my_tag = my["tag"] if my else None
        if not rows:
            self._log.write(
                "[dim]no alliances yet — found one with[/dim] [yellow]/found <tag> <name>[/yellow]"
            )
            return
        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("tag", style="bold yellow")
        t.add_column("name")
        t.add_column("members", justify="right")
        t.add_column("founder", style="dim")
        for r in rows:
            tag = f"[{r['tag']}]"
            if r["tag"] == my_tag:
                tag = f"[bold green]{tag}[/bold green]"
            t.add_row(tag, r["name"], str(r["member_count"]), r["founder_username"])
        self._log.write(t)
        if my_tag:
            self._log.write(f"[dim]you are in[/dim] [bold yellow][{my_tag}][/bold yellow]")
        else:
            self._log.write(
                "[dim]join one with[/dim] [yellow]/join <tag>[/yellow] "
                "[dim]or found yours with[/dim] [yellow]/found <tag> <name>[/yellow]"
            )

    async def _cmd_alliance(self, args: list[str]) -> None:
        """Umbrella for everything that operates on YOUR alliance.

        Forms:
          /alliance                          show your alliance
          /alliance <TAG>                    show another alliance
          /alliance --requests               founder: list pending; or your own
          /alliance --approve <user>         founder: approve a request
          /alliance --reject <user>          founder: reject a request
          /alliance --withdraw               cancel your own pending request
        """
        # Flag mode: anything starting with "--" routes to a subcommand
        # acting on the user's own alliance.
        flag = next((a for a in args if a.startswith("--")), None)
        if flag is not None:
            tail = [a for a in args if not a.startswith("--")]
            return await self._alliance_flag(flag, tail)

        if not args:
            my = await self.app.client.my_alliance()
            if my is None:
                self._log.write(
                    "[dim]you are not in any alliance.[/dim] "
                    "[yellow]/alliances[/yellow] [dim]to browse[/dim]"
                )
                return
            await self._render_alliance(my)
            return
        tag = args[0].upper()
        try:
            data = await self.app.client.get_alliance(tag)
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return
        await self._render_alliance(data)

    async def _alliance_flag(self, flag: str, tail: list[str]) -> None:
        flag = flag.lower()
        if flag in ("--requests", "--reqs", "--r"):
            return await self._alliance_requests()
        if flag in ("--approve", "--app", "--a"):
            return await self._alliance_decide(tail, approve=True)
        if flag in ("--reject", "--rej"):
            return await self._alliance_decide(tail, approve=False)
        if flag in ("--withdraw", "--w"):
            return await self._alliance_withdraw()
        self._log.write(
            f"[red]unknown flag:[/red] {flag}  "
            "[dim]known:[/dim] [yellow]--requests --approve <user> "
            "--reject <user> --withdraw[/yellow]"
        )

    async def _alliance_requests(self) -> None:
        my = await self.app.client.my_alliance()
        if my is not None and my["founder_id"] == await self._me_user_id():
            try:
                items = await self.app.client.list_alliance_requests(my["tag"])
            except APIError as exc:
                self._log.write(f"[red]{exc.detail}[/red]")
                return
            if not items:
                self._log.write("[dim]no pending applications[/dim]")
                return
            t = Table(show_header=True, header_style="bold yellow", box=None)
            t.add_column("applicant", style="bold")
            t.add_column("message")
            t.add_column("applied")
            for r in items:
                t.add_row(
                    r["username"],
                    r.get("message") or "—",
                    _local_hhmmss(r["created_at"]),
                )
            self._log.write(t)
            self._log.write(
                "[dim]approve:[/dim] [yellow]/alliance --approve <user>[/yellow]  "
                "[dim]reject:[/dim] [yellow]/alliance --reject <user>[/yellow]"
            )
            return

        mine = await self.app.client.my_alliance_request()
        if mine is None:
            self._log.write("[dim]no pending request[/dim]")
            return
        self._log.write(
            f"[yellow]pending[/yellow] [{mine['alliance_tag']}] {mine['alliance_name']} "
            f"[dim](applied {_local_hhmmss(mine['created_at'])})[/dim]  "
            f"[dim]withdraw:[/dim] [yellow]/alliance --withdraw[/yellow]"
        )

    async def _alliance_decide(self, tail: list[str], *, approve: bool) -> None:
        verb = "approve" if approve else "reject"
        if not tail:
            self._log.write(f"[red]usage:[/red] /alliance --{verb} <username>")
            return
        my = await self.app.client.my_alliance()
        if my is None or my["founder_id"] != await self._me_user_id():
            self._log.write(f"[red]only the founder can {verb} requests[/red]")
            return
        username = tail[0]
        try:
            if approve:
                await self.app.client.approve_alliance_request(my["tag"], username)
            else:
                await self.app.client.reject_alliance_request(my["tag"], username)
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return
        if approve:
            self._log.write(f"[green]approved[/green] {username} into [{my['tag']}]")
        else:
            self._log.write(f"[yellow]rejected[/yellow] {username}")

    async def _alliance_withdraw(self) -> None:
        try:
            await self.app.client.withdraw_alliance_request()
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return
        self._log.write("[green]request withdrawn[/green]")

    async def _render_alliance(self, data: dict) -> None:
        header = Text()
        header.append("━━━ ", style="bold yellow")
        header.append(f"[{data['tag']}] {data['name']}", style="bold yellow")
        header.append(f" · {data['member_count']} members ━━━", style="dim")
        self._log.write(header)
        if data.get("description"):
            self._log.write(f"[dim]{data['description']}[/dim]")
        self._log.write(f"[dim]founder:[/dim] [bold]{data['founder_username']}[/bold]")

        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("player", style="bold")
        t.add_column("role", style="dim")
        t.add_column("joined", style="dim")
        for m in data.get("members", []):
            role_style = "yellow" if m["role"] == "founder" else "dim"
            t.add_row(
                m["username"],
                Text(m["role"], style=role_style),
                str(m["joined_at"])[:10],
            )
        self._log.write(t)

    async def _cmd_found(self, args: list[str]) -> None:
        if len(args) < 2:
            self._log.write(
                "[red]usage:[/red] /found <TAG> <name...> [dim](TAG = 2-6 alphanumeric chars)[/dim]"
            )
            return
        tag = args[0]
        name = " ".join(args[1:])
        try:
            data = await self.app.client.create_alliance(tag, name)
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return
        self._log.write(
            f"[green]founded[/green] [bold yellow][{data['tag']}][/bold yellow] {data['name']}"
        )

    async def _cmd_join(self, args: list[str]) -> None:
        if not args:
            self._log.write("[red]usage:[/red] /join <tag> [message]")
            return
        tag = args[0]
        message = " ".join(args[1:]) if len(args) > 1 else ""
        try:
            data = await self.app.client.join_alliance(tag, message=message)
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return
        self._log.write(
            f"[green]request sent[/green] to [bold yellow][{data['alliance_tag']}][/bold yellow] "
            f"{data['alliance_name']} — wait for the founder to approve"
        )

    async def _cmd_leave(self, args: list[str]) -> None:
        my = await self.app.client.my_alliance()
        if my is None:
            self._log.write("[dim]you are not in any alliance[/dim]")
            return
        try:
            await self.app.client.leave_alliance(my["tag"])
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return
        self._log.write(f"[green]left[/green] [bold yellow][{my['tag']}][/bold yellow]")

    async def _cmd_refresh(self, args: list[str]) -> None:
        await self._refresh_planets()
        await self._refresh_dashboard()
        self._log.write(
            f"[green]refreshed[/green] [dim]({_now_local_hhmmss()})[/dim] "
            f"top bar, planet card, queue, inbox, all panels"
        )

    async def _cmd_msg(self, args: list[str]) -> None:
        # No args -> show conversation list (same as /inbox)
        if not args:
            await self._cmd_inbox([])
            self._log.write(
                "[dim]continue a thread:[/dim] [yellow]/msg <username>[/yellow]  "
                "[dim]send:[/dim] [yellow]/msg <username> <text>[/yellow]"
            )
            return
        # Single arg -> show conversation with that user
        if len(args) == 1:
            await self._show_conversation(args[0])
            return
        # /msg <user> <text...> -> send a message
        recipient = args[0]
        body = " ".join(args[1:])
        r = await self.app.client.send_message(recipient, body)
        self._log.write(
            f"[green]sent[/green] -> [bold]{r['recipient_username']}[/bold]: {body}  "
            f"[dim]({_short_dt(r['created_at'])})[/dim]"
        )

    async def _cmd_inbox(self, args: list[str]) -> None:
        # /inbox <user> -> conversation; /inbox -> thread list
        if args:
            await self._show_conversation(args[0])
            return

        threads = await self.app.client.threads()
        if not threads:
            self._log.write(
                "[dim]no conversations yet. send a message with[/dim] "
                "[cyan]/msg <user> <text>[/cyan]"
            )
            return

        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("", width=2)
        t.add_column("with", style="bold")
        t.add_column("last", justify="right")
        t.add_column("preview")
        for th in threads:
            unread_marker = "•" if th["unread_count"] > 0 else " "
            unread_style = "bold magenta" if th["unread_count"] > 0 else ""
            preview = th["last_preview"]
            if th["last_from_me"]:
                preview = f"you: {preview}"
            t.add_row(
                Text(unread_marker, style=unread_style),
                Text(
                    th["other_username"]
                    + (f" ({th['unread_count']})" if th["unread_count"] else "")
                ),
                _short_dt(th["last_at"]),
                preview,
            )
        self._log.write(t)
        self._log.write(
            "[dim]use[/dim] [cyan]/inbox <username>[/cyan] [dim]to open a conversation[/dim]"
        )

    async def _show_conversation(self, username: str) -> None:
        try:
            messages = await self.app.client.conversation(username, limit=200)
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return

        if not messages:
            self._log.write(
                f"[dim]no messages with[/dim] [bold]{username}[/bold]. "
                f"[dim]start one:[/dim] [cyan]/msg {username} <text>[/cyan]"
            )
            return

        me_username = self._username()
        header = Text()
        header.append("━━━ conversation with ", style="bold yellow")
        header.append(username, style="bold yellow")
        header.append(f"  ({len(messages)} messages) ", style="dim")
        header.append("━" * 10, style="cyan")
        self._log.write(header)

        # Sequential render, sender-colored, with timestamps
        for m in messages:
            from_me = m["sender_username"] == me_username
            time_str = _local_hhmmss(m["created_at"])
            line = Text()
            if from_me:
                line.append(f"[{time_str}] ", style="dim")
                line.append("me", style="bold green")
                line.append(":  ", style="dim")
                line.append(m["body"], style="white")
            else:
                line.append(f"[{time_str}] ", style="dim")
                line.append(m["sender_username"], style="bold yellow")
                line.append(":  ", style="dim")
                line.append(m["body"], style="white")
            self._log.write(line)

        footer = Text()
        footer.append("─" * 40 + "\n", style="dim")
        footer.append("reply with: ", style="dim")
        footer.append(f"/msg {username} <text>", style="cyan")
        self._log.write(footer)

    # ------- Fleet / Shipyard / Espionage / Reports --------------------------
    async def _cmd_ships(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        data = await self.app.client.list_ships(pid)
        snap = self._snapshot or {}
        cur_m = snap.get("resources_metal", 0)
        cur_c = snap.get("resources_crystal", 0)
        cur_d = snap.get("resources_deuterium", 0)

        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("ship", style="bold")
        t.add_column("have", justify="right")
        t.add_column("metal", justify="right")
        t.add_column("crystal", justify="right")
        t.add_column("deut", justify="right")
        t.add_column("per-ship time")
        t.add_column("status")
        for s in data["ships"]:
            avail = s["prereq_met"]
            base = "" if avail else "dim"
            if not avail:
                status = Text("locked: " + ", ".join(s["prereq_missing"])[:40], style="red")
            elif (
                cur_m < s["cost_metal"] or cur_c < s["cost_crystal"] or cur_d < s["cost_deuterium"]
            ):
                status = Text("need resources", style="yellow")
            else:
                status = Text("ready", style="green")
            t.add_row(
                Text(s["ship_type"], style="bold" if avail else "dim"),
                Text(str(s["count"]), style=base or "yellow"),
                Text(_fmt_int(s["cost_metal"]), style=base or "yellow"),
                Text(_fmt_int(s["cost_crystal"]), style=base or "cyan"),
                Text(_fmt_int(s["cost_deuterium"]), style=base or "magenta"),
                Text(_fmt_seconds(s["build_seconds"]), style=base or ""),
                status,
            )
        self._log.write(Text(f"Shipyard L{data['shipyard_level']}", style="bold yellow"))
        self._log.write(t)
        self._log.write("[dim]build:[/dim] [yellow]/build <ship_type> <count>[/yellow]")

    async def _cmd_build(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        if len(args) < 2:
            self._log.write(
                "[red]usage:[/red] /build <ship_type> <count>  (e.g. /build small_cargo 5)"
            )
            return
        ship = args[0].lower()
        try:
            count = int(args[1])
        except ValueError:
            self._log.write("[red]count must be integer[/red]")
            return
        r = await self.app.client.build_ship(pid, ship, count)
        self._log.write(
            f"[green]queued[/green] {count}x {ship}  "
            f"cost {r['cost_metal']}/{r['cost_crystal']}/{r['cost_deuterium']}  "
            f"done at [yellow]{_local_hhmmss(r['finished_at'])}[/yellow] "
            f"([dim]{_remaining_str(r['finished_at'])}[/dim])"
        )

    async def _cmd_defense(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        data = await self.app.client.list_defenses(pid)
        snap = self._snapshot or {}
        cur_m = snap.get("resources_metal", 0)
        cur_c = snap.get("resources_crystal", 0)
        cur_d = snap.get("resources_deuterium", 0)

        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("structure", style="bold")
        t.add_column("have", justify="right")
        t.add_column("metal", justify="right")
        t.add_column("crystal", justify="right")
        t.add_column("deut", justify="right")
        t.add_column("hull", justify="right")
        t.add_column("shld", justify="right")
        t.add_column("atk", justify="right")
        t.add_column("status")
        for s in data["defenses"]:
            avail = s["prereq_met"]
            base = "" if avail else "dim"
            if not avail:
                stat = Text("locked: " + ", ".join(s["prereq_missing"])[:40], style="red")
            elif s["unique"] and s["count"] >= 1:
                stat = Text("built (max 1)", style="dim")
            elif (
                cur_m < s["cost_metal"] or cur_c < s["cost_crystal"] or cur_d < s["cost_deuterium"]
            ):
                stat = Text("need resources", style="yellow")
            else:
                stat = Text("ready", style="green")
            label = s["defense_type"] + (" *" if s["unique"] else "")
            t.add_row(
                Text(label, style="bold" if avail else "dim"),
                Text(str(s["count"]), style=base or "yellow"),
                Text(_fmt_int(s["cost_metal"]), style=base or "yellow"),
                Text(_fmt_int(s["cost_crystal"]), style=base or "cyan"),
                Text(_fmt_int(s["cost_deuterium"]), style=base or "magenta"),
                Text(_fmt_int(s["structural_integrity"]), style=base or "dim"),
                Text(_fmt_int(s["shield_power"]), style=base or "dim"),
                Text(_fmt_int(s["weapon_power"]), style=base or "dim"),
                stat,
            )
        self._log.write(
            Text(f"Shipyard L{data['shipyard_level']}  [* = unique, max 1]", style="bold yellow")
        )
        self._log.write(t)
        self._log.write("[dim]build:[/dim] [yellow]/defend <defense_type> <count>[/yellow]")

    async def _cmd_defend(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        if len(args) < 2:
            self._log.write(
                "[red]usage:[/red] /defend <defense_type> <count>  (e.g. /defend rocket_launcher 20)"
            )
            return
        dtype = args[0].lower()
        try:
            count = int(args[1])
        except ValueError:
            self._log.write("[red]count must be integer[/red]")
            return
        r = await self.app.client.build_defense(pid, dtype, count)
        self._log.write(
            f"[green]queued[/green] {count}x {dtype}  "
            f"cost {r['cost_metal']}/{r['cost_crystal']}/{r['cost_deuterium']}  "
            f"done at [yellow]{_local_hhmmss(r['finished_at'])}[/yellow] "
            f"([dim]{_remaining_str(r['finished_at'])}[/dim])"
        )

    async def _cmd_fleets(self, args: list[str]) -> None:
        fleets = await self.app.client.list_fleets()
        if not fleets:
            self._log.write("[dim]no active fleets[/dim]")
            return
        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("id", style="yellow")
        t.add_column("mission", style="bold")
        t.add_column("status")
        t.add_column("target")
        t.add_column("ships")
        t.add_column("arrival/return")
        t.add_column("cargo")
        for f in fleets:
            ship_summary = ", ".join(
                f"{s['ship_type']}x{s['count']}" for s in f["ships"] if s["count"] > 0
            )
            target = f"{f['target_galaxy']}:{f['target_system']}:{f['target_position']}"
            cargo = f"{f['cargo_metal']}/{f['cargo_crystal']}/{f['cargo_deuterium']}"
            if f["status"] == "outbound":
                eta = f"{_local_hhmmss(f['arrival_at'])} ({_remaining_str(f['arrival_at'])})"
                stat = Text("→ outbound", style="cyan")
            elif f["status"] == "returning" and f["return_at"]:
                eta = f"{_local_hhmmss(f['return_at'])} ({_remaining_str(f['return_at'])})"
                stat = Text("← returning", style="green")
            else:
                eta = "?"
                stat = Text(f["status"], style="dim")
            t.add_row(
                str(f["id"]),
                f["mission"],
                stat,
                target,
                ship_summary[:30],
                eta,
                cargo,
            )
        self._log.write(t)

    async def _send_fleet_generic(
        self, args: list[str], mission: str, default_ships: dict[str, int] | None = None
    ) -> None:
        """Generic: /<cmd> <g>:<s>:<p> [<ship>:<n>...] [cargo M/C/D]

        For /espionage: probes auto-added. For /attack: requires explicit ships.
        For /transport: ships + cargo flags.
        """
        pid = self._require_planet()
        if pid is None:
            return
        if not args:
            self._log.write(
                f"[red]usage:[/red] /{mission} <g>:<s>:<p> [<ship>:<n>...]  "
                "[example: /attack 1:42:8 light_fighter:50 cruiser:5]"
            )
            return
        try:
            parts = args[0].split(":")
            g, s, p = int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            self._log.write("[red]format error:[/red] use <galaxy>:<system>:<position>")
            return

        ships: dict[str, int] = dict(default_ships or {})
        cargo_m = cargo_c = cargo_d = 0
        for token in args[1:]:
            if token.startswith("m="):
                cargo_m = int(token[2:])
            elif token.startswith("c="):
                cargo_c = int(token[2:])
            elif token.startswith("d="):
                cargo_d = int(token[2:])
            elif ":" in token:
                stype, cnt = token.split(":", 1)
                ships[stype.lower()] = int(cnt)

        if mission == "espionage" and "espionage_probe" not in ships:
            ships["espionage_probe"] = 1

        try:
            r = await self.app.client.send_fleet(
                origin_planet_id=pid,
                mission=mission,
                target_galaxy=g,
                target_system=s,
                target_position=p,
                ships=ships,
                cargo_metal=cargo_m,
                cargo_crystal=cargo_c,
                cargo_deuterium=cargo_d,
            )
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return

        fuel = r.get("fuel_cost", 0)
        self._log.write(
            f"[green]fleet #{r['id']} sent[/green]  "
            f"{mission} -> {g}:{s}:{p}  "
            f"arrival [yellow]{_local_hhmmss(r['arrival_at'])}[/yellow] "
            f"([dim]{_remaining_str(r['arrival_at'])}[/dim])  fuel {fuel} deut"
        )

    async def _cmd_espionage(self, args: list[str]) -> None:
        if not args:
            self._log.write(
                "[red]usage:[/red] /espionage <g>:<s>:<p> [espionage_probe:<n>]  (default 1 probe)"
            )
            return
        await self._send_fleet_generic(args, "espionage", default_ships={"espionage_probe": 1})

    async def _cmd_attack(self, args: list[str]) -> None:
        if len(args) < 2:
            self._log.write("[red]usage:[/red] /attack <g>:<s>:<p> <ship>:<n> [<ship>:<n> ...]")
            return
        await self._send_fleet_generic(args, "attack")

    async def _cmd_transport(self, args: list[str]) -> None:
        if len(args) < 2:
            self._log.write(
                "[red]usage:[/red] /transport <g>:<s>:<p> small_cargo:<n> "
                "[m=<metal> c=<crystal> d=<deuterium>]"
            )
            return
        await self._send_fleet_generic(args, "transport")

    async def _cmd_send(self, args: list[str]) -> None:
        """Generic send: /send <mission> <coord> <ships...> [cargo]"""
        if len(args) < 2:
            self._log.write(
                "[red]usage:[/red] /send <mission> <g>:<s>:<p> <ship>:<n> ...  "
                "[missions: attack transport espionage deploy]"
            )
            return
        mission = args[0].lower()
        rest = args[1:]
        await self._send_fleet_generic(rest, mission)

    async def _cmd_reports(self, args: list[str]) -> None:
        if args:
            try:
                rid = int(args[0])
            except ValueError:
                self._log.write("[red]report id must be integer[/red]")
                return
            await self._show_report(rid)
            return

        reports = await self.app.client.list_reports(limit=20)
        if not reports:
            self._log.write("[dim]no reports yet[/dim]")
            return
        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("id", style="yellow")
        t.add_column("type")
        t.add_column("when", style="dim")
        t.add_column("title")
        for r in reports:
            t.add_row(
                str(r["id"]),
                Text(r["report_type"], style="cyan" if r["report_type"] == "espionage" else "red"),
                _short_dt(r["created_at"]),
                r["title"],
            )
        self._log.write(t)
        self._log.write("[dim]open one with[/dim] [yellow]/reports <id>[/yellow]")

    async def _show_report(self, report_id: int) -> None:
        import json as _json

        try:
            r = await self.app.client.get_report(report_id)
        except APIError as exc:
            self._log.write(f"[red]{exc.detail}[/red]")
            return
        try:
            body = _json.loads(r["body"])
        except Exception:
            self._log.write(r["body"])
            return

        header = Text()
        header.append("━━━ ", style="bold yellow")
        header.append(r["title"], style="bold yellow")
        header.append(f"  ({_short_dt(r['created_at'])}) ━━━", style="dim")
        self._log.write(header)

        if r["report_type"] == "espionage":
            self._render_espionage_report(body)
        elif r["report_type"] == "combat":
            self._render_combat_report(body)

    def _render_espionage_report(self, body: dict) -> None:
        if "spy_username" in body:
            # Counter-espionage notification (target's view)
            self._log.write(
                f"[red]You were spied on by[/red] [bold]{body['spy_username']}[/bold]\n"
                f"  probes sent: {body['probes_sent']}, destroyed by you: {body['probes_destroyed']}, "
                f"counter chance: {body['counter_chance'] * 100:.0f}%"
            )
            return
        info = body.get("info_level", 1)
        self._log.write(
            f"Target: [bold yellow]{body['target_name']}[/bold yellow] "
            f"[{body['target_coord']}] owner [cyan]{body['target_owner']}[/cyan]  "
            f"info level [yellow]{info}/5[/yellow]"
        )
        r = body["resources"]
        self._log.write(
            f"  resources: M [yellow]{_fmt_int(r['metal'])}[/yellow] "
            f"C [cyan]{_fmt_int(r['crystal'])}[/cyan] "
            f"D [magenta]{_fmt_int(r['deuterium'])}[/magenta]"
        )
        if body.get("fleet"):
            ships = ", ".join(f"{k}: {v}" for k, v in body["fleet"].items())
            self._log.write(f"  fleet: {ships}")
        if body.get("defenses"):
            defs = ", ".join(f"{k}: {v}" for k, v in body["defenses"].items())
            self._log.write(f"  defenses: {defs}")
        if body.get("buildings"):
            blds = ", ".join(f"{k}: L{v}" for k, v in body["buildings"].items() if v > 0)
            if blds:
                self._log.write(f"  buildings: {blds}")
        if body.get("research"):
            res = ", ".join(f"{k}: L{v}" for k, v in body["research"].items() if v > 0)
            if res:
                self._log.write(f"  research: {res}")
        if body.get("probes_destroyed"):
            self._log.write(
                f"  [red]counter-espionage:[/red] {body['probes_destroyed']}/{body['probes_sent']} probes destroyed"
            )

    def _render_combat_report(self, body: dict) -> None:
        winner = body.get("winner", "draw")
        winner_style = (
            "green" if winner == "attacker" else ("red" if winner == "defender" else "yellow")
        )
        self._log.write(
            f"[{winner_style}]{winner.upper()} WINS[/{winner_style}]  at {body['target_coord']}\n"
            f"  attacker [bold]{body['attacker']}[/bold] vs defender [bold]{body['defender']}[/bold]"
        )
        self._log.write(
            f"  total attack:  attacker {body['attacker_attack']}  defender {body['defender_attack']}"
        )
        if body.get("attacker_destroyed"):
            losses = ", ".join(f"{k}: -{v}" for k, v in body["attacker_destroyed"].items())
            self._log.write(f"  [red]attacker losses:[/red] {losses}")
        if body.get("defender_ships_destroyed"):
            losses = ", ".join(f"{k}: -{v}" for k, v in body["defender_ships_destroyed"].items())
            self._log.write(f"  [red]defender ship losses:[/red] {losses}")
        if body.get("defender_defenses_destroyed"):
            losses = ", ".join(f"{k}: -{v}" for k, v in body["defender_defenses_destroyed"].items())
            self._log.write(f"  [red]defender defense losses:[/red] {losses}")
        pl = body.get("plunder", {})
        if any(pl.values()):
            self._log.write(
                f"  [yellow]plunder:[/yellow] M {_fmt_int(pl['metal'])} "
                f"C {_fmt_int(pl['crystal'])} D {_fmt_int(pl['deuterium'])}"
            )
        deb = body.get("debris", {})
        if any(deb.values()):
            self._log.write(
                f"  [dim]debris field:[/dim] M {_fmt_int(deb['metal'])} "
                f"C {_fmt_int(deb['crystal'])}"
            )

    async def _cmd_logs(self, args: list[str]) -> None:
        pid = self._require_planet()
        if pid is None:
            return
        limit = 20
        if args:
            try:
                limit = max(1, min(100, int(args[0])))
            except ValueError:
                self._log.write("[red]usage:[/red] /logs [N]  (N=1..100)")
                return

        events = await self.app.client.planet_logs(pid, limit=limit)
        snap = self._snapshot
        pname = (
            f"{snap['name']} {snap['galaxy']}:{snap['system']}:{snap['position']}"
            if snap
            else f"planet {pid}"
        )

        header = Text()
        header.append("━━━ recent activity on ", style="bold yellow")
        header.append(pname, style="bold yellow")
        header.append(f"  (last {len(events)}) ", style="dim")
        header.append("━" * 10, style="cyan")
        self._log.write(header)

        if not events:
            self._log.write("[dim]no completed events yet[/dim]")
            return

        t = Table(show_header=True, header_style="bold yellow", box=None)
        t.add_column("when", style="dim")
        t.add_column("type")
        t.add_column("item")
        t.add_column("level", justify="right")
        for ev in events:
            type_style = "green" if ev["queue_type"] == "building" else "magenta"
            t.add_row(
                _short_dt(ev["completed_at"]),
                Text(f"✓ {ev['queue_type']}", style=type_style),
                Text(ev["item_key"], style="bold"),
                Text(f"L{ev['target_level']}", style="cyan"),
            )
        self._log.write(t)

    # ------- Helpers ---------------------------------------------------------
    def _require_planet(self) -> int | None:
        pid = self.app.current_planet_id
        if pid is None:
            self._log.write(
                "[red]no active planet[/red]  [dim]/planets to list, /switch <id>[/dim]"
            )
            return None
        return pid

    async def _refresh_planets(self) -> None:
        try:
            self._planets_cache = await self.app.client.list_planets()
        except APIError:
            self._planets_cache = []
            return
        if self.app.current_planet_id is None and self._planets_cache:
            self.app.current_planet_id = self._planets_cache[0]["id"]
        self.app.planets = self._planets_cache
