from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class EventRecord:
    time: str
    kind: str
    summary: str
    ok: bool = True


@dataclass
class BotStats:
    received: int = 0
    validated: int = 0
    replied: int = 0
    ignored: int = 0
    errors: int = 0
    started_at: str = field(default_factory=utc_now)


class MemoryStore:
    def __init__(self, event_limit: int = 80, dedup_ttl: float = 600) -> None:
        self._lock = Lock()
        self._stats = BotStats()
        self._events: deque[EventRecord] = deque(maxlen=event_limit)
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._dedup_ttl = dedup_ttl
        self._start = monotonic()

    @property
    def uptime_seconds(self) -> int:
        return int(monotonic() - self._start)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "stats": asdict(self._stats),
                "events": [asdict(item) for item in list(self._events)],
                "uptime_seconds": self.uptime_seconds,
            }

    def bump(self, field_name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self._stats, field_name, getattr(self._stats, field_name) + n)

    def remember(self, kind: str, summary: str, ok: bool = True) -> None:
        with self._lock:
            self._events.appendleft(EventRecord(time=utc_now(), kind=kind, summary=summary, ok=ok))

    def seen_before(self, event_id: str) -> bool:
        if not event_id:
            return False
        now = monotonic()
        with self._lock:
            expired = [key for key, ts in self._seen.items() if now - ts > self._dedup_ttl]
            for key in expired:
                self._seen.pop(key, None)
            if event_id in self._seen:
                return True
            self._seen[event_id] = now
            return False


store = MemoryStore()
