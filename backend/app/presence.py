"""In-memory online-presence tracking.

Every authenticated request stamps `last_seen[user_id] = now`. We avoid
DB writes on the hot path; the count is read by /stats and the web
dashboard. State is lost on restart but repopulates as users hit any
authenticated endpoint, which happens every few seconds.

Entries are retained for ACTIVE_WINDOW (24h) so /stats can report
active_24h. `online_count` is a tighter 5-minute view of the same map.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# user_id -> last seen UTC datetime
_last_seen: dict[int, datetime] = {}

# Users who hit any authed endpoint within this window are "online".
ONLINE_WINDOW = timedelta(minutes=5)

# Longest window we report on; entries older than this are pruned.
ACTIVE_WINDOW = timedelta(hours=24)


def touch(user_id: int) -> None:
    _last_seen[user_id] = datetime.now(UTC)


def _gc(now: datetime) -> None:
    """Drop entries older than the longest window we care about."""
    cutoff = now - ACTIVE_WINDOW
    stale = [uid for uid, seen in _last_seen.items() if seen < cutoff]
    for uid in stale:
        del _last_seen[uid]


def online_count(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    _gc(now)
    cutoff = now - ONLINE_WINDOW
    return sum(1 for seen in _last_seen.values() if seen >= cutoff)


def active_count(
    window: timedelta = ACTIVE_WINDOW, now: datetime | None = None
) -> int:
    """Count users seen within the given window. Default: 24h."""
    now = now or datetime.now(UTC)
    _gc(now)
    cutoff = now - window
    return sum(1 for seen in _last_seen.values() if seen >= cutoff)
