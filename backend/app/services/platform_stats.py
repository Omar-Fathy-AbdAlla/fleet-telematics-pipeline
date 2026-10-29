"""Platform KPIs 54, 57, 58, 60 from the Kafka messages themselves (their Kafka time and position), as plain logic
(no Kafka, no asyncio). Window = the last `window` of Kafka time, ending at the newest message; previous = the `window`
before it. Kafka time is used (not event_ts) because a rejected message may have no event_ts."""
from datetime import datetime, timedelta

from ..domain.stream_source import StreamMessage
from .stream_kpis import pct

PLATFORM_KPI_IDS = (54, 57, 58, 60)
RECEIVED, DUPLICATES, REJECTED = range(3)  # positions in a minute's counts


class PlatformStats:
    def __init__(self, window: timedelta):
        self._window = window
        self._minutes: dict[datetime, list[int]] = {}  # Kafka time (to the minute) -> [received, duplicates, rejected]
        self._read: dict[tuple[str, int], tuple[int, datetime]] = {}  # (kind, partition) -> newest (offset, Kafka time)

    def is_new(self, message: StreamMessage) -> bool:
        """False for a message read again (the reader goes back after a Kafka failure): its offset and Kafka time are
        not past the newest ones read on its partition. A newer Kafka time with a lower offset (topic re-created) is new."""
        key = (message.kind, message.partition)
        read = self._read.get(key)
        if read and message.offset <= read[0] and message.timestamp <= read[1]:
            return False
        self._read[key] = (message.offset, message.timestamp)
        return True

    def count(self, message: StreamMessage, duplicate: bool = False, rejected: bool = False) -> None:
        minute = message.timestamp.replace(second=0, microsecond=0)
        counts = self._minutes.setdefault(minute, [0, 0, 0])
        counts[RECEIVED] += 1
        counts[DUPLICATES] += duplicate
        counts[REJECTED] += rejected

    def kpis(self, now: datetime) -> list[dict]:
        """KpiValue rows for PLATFORM_KPI_IDS (empty before the first message). Drops minutes older than 2 windows.
        54 = received / seconds (events/s), 57 / 58 = duplicates / rejected of received (%), 60 = now - newest Kafka
        time (min, a point in time: no previous)."""
        if not self._minutes:
            return []
        end = max(self._minutes)
        for minute in [minute for minute in self._minutes if minute <= end - 2 * self._window]:
            del self._minutes[minute]
        current = self._sum(end - self._window, end)
        previous = self._sum(end - 2 * self._window, end - self._window)
        newest = max(read[1] for read in self._read.values())
        seconds = self._window.total_seconds()
        return [
            {"kpi_id": 54, "value": round(current[RECEIVED] / seconds, 2), "previous": round(previous[RECEIVED] / seconds, 2) if previous[RECEIVED] else None},
            {"kpi_id": 57, "value": pct(current[DUPLICATES], current[RECEIVED], 2), "previous": pct(previous[DUPLICATES], previous[RECEIVED], 2)},
            {"kpi_id": 58, "value": pct(current[REJECTED], current[RECEIVED], 2), "previous": pct(previous[REJECTED], previous[RECEIVED], 2)},
            {"kpi_id": 60, "value": round((now - newest).total_seconds() / 60, 1), "previous": None},
        ]

    def _sum(self, start: datetime, end: datetime) -> list[int]:
        """Counts of the minutes with start < minute <= end."""
        total = [0, 0, 0]
        for minute, counts in self._minutes.items():
            if start < minute <= end:
                total = [a + b for a, b in zip(total, counts)]
        return total
