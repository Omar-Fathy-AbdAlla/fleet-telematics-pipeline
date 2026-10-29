"""Every telemetry and reefer row of the last `keep` (by event_ts, counted back from the newest row kept), with only
the columns services/stream_kpis.py reads: full rows of 120 min take ~223 MB (measured 2026-10-29).
Plain logic (no Kafka, no asyncio), filled by FleetState.apply()."""
from datetime import datetime, timedelta
from typing import Literal

from ..domain.stream_source import StreamKind

COLUMNS: dict[StreamKind, tuple[str, ...]] = {
    "telemetry": ("vehicle_id", "event_ts", "motion_status", "is_speeding", "is_idling", "fuel_gph", "odometer_mi"),
    "reefer": ("vehicle_id", "trailer_id", "event_ts", "commodity_type", "cargo_temp_f", "setpoint_f",
               "allowed_temp_min_f", "allowed_temp_max_f", "ambient_temp_f", "door_open", "is_temp_breach",
               "is_reefer_unit_failure"),
}


class StreamHistory:
    def __init__(self, keep: timedelta):
        self._keep = keep
        self._rows: dict[StreamKind, dict[tuple[str, str], dict]] = {"telemetry": {}, "reefer": {}}  # (vehicle_id, event_ts) -> row
        self._newest: datetime | None = None

    def add(self, kind: StreamKind, row: dict) -> Literal["added", "duplicate", "old"]:
        """Keeps the row's COLUMNS ("added"), unless it is a duplicate (same vehicle_id + event_ts already kept, ~0.4%)
        or older than `keep` before the newest row. KeyError / TypeError / ValueError when vehicle_id or event_ts is bad."""
        event_ts = datetime.fromisoformat(row["event_ts"])
        key = (row["vehicle_id"], row["event_ts"])
        if key in self._rows[kind]:
            return "duplicate"
        if self._newest and event_ts < self._newest - self._keep:
            return "old"
        self._rows[kind][key] = {column: row.get(column) for column in COLUMNS[kind]}
        self._newest = max(self._newest or event_ts, event_ts)
        return "added"

    def rows(self, kind: StreamKind) -> list[dict]:
        """The rows kept of `kind`, in no order, after dropping the ones older than `keep` before the newest row."""
        if self._newest:
            oldest = self._newest - self._keep
            rows = self._rows[kind]
            for key in [key for key in rows if datetime.fromisoformat(key[1]) < oldest]:
                del rows[key]
        return list(self._rows[kind].values())
