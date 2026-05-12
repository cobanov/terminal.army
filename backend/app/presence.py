"""In-memory online-presence tracking.

Every authenticated request stamps `last_seen[user_id] = now`. We avoid
DB writes on the hot path; the count is read by /stats and the web
dashboard. State is lost on restart but repopulates as users hit any
authenticated endpoint, which happens every few seconds.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# user_id -> last seen UTC datetime
_last_seen: dict[int, datetime] = {}

# Users who hit any authed endpoint within this window are "online".
ONLINE_WINDOW = timedelta(minutes=5)


def touch(user_id: int) -> None:
    _last_seen[user_id] = datetime.now(UTC)


def online_count(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - ONLINE_WINDOW
    # Opportunistic GC: prune entries older than the window. Cheap because
    # we only walk the dict here, never on the hot path.
    stale = [uid for uid, seen in _last_seen.items() if seen < cutoff]
    for uid in stale:
        del _last_seen[uid]
    return len(_last_seen)
