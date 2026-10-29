"""Shapes of the SSE events the backend builds itself (GET /api/stream). telemetry and reefer rows are sent exactly
as Kafka has them (all their columns, see dashboard/src/data/contract.js), so they have no model here."""
from typing import Any, Literal

from pydantic import BaseModel

from .dashboard import KpiValue

EventName = Literal["telemetry", "reefer", "alert", "kpis", "stream_kpis"]  # SSE event names (?events= filter)

AnomalyType = Literal[
    "SPEEDING", "ENGINE_OVERHEATING", "LOW_FUEL", "EXCESSIVE_IDLING", "COLD_CHAIN_BREACH", "REEFER_UNIT_FAILURE"
]


class AlertRow(BaseModel):
    anomaly_id: str  # vehicle_id-anomaly_type-start_ts: the same alert keeps the same id after a backend restart
    anomaly_type: AnomalyType
    vehicle_id: str
    trip_id: str | None  # not in the stream: always null for live alerts
    start_ts: str
    end_ts: str | None  # null while the alert is active


class LiveKpis(BaseModel):
    """Calculated from the latest row of each truck kept in the last STREAM_HISTORY_MINUTES."""

    as_of: str  # backend time (UTC) when these values were calculated
    trucks_reporting: int  # trucks with a telemetry row (count)
    motion_status: dict[str, int]  # trucks per motion_status: DRIVING / PARKED / IDLING (count)
    is_speeding: int  # trucks whose latest row has the flag (count)
    is_engine_overheating: int
    is_low_fuel: int
    reefers_reporting: int  # trucks with a reefer row (count)
    is_reefer_unit_failure: int
    cold_chain_compliance_pct: float | None  # valid readings (cargo_temp_f not null) without is_temp_breach (%)
    cold_chain_compliance_pct_by_commodity: dict[str, float]  # same, per commodity_type (%)
    newest_event_ts: str | None  # newest reading kept
    data_age_min: float | None  # as_of - newest_event_ts (min)
    last_received_at: str | None  # backend time (UTC) when the last new row arrived


class StreamKpis(BaseModel):
    """Catalog KPIs and charts calculated from every Kafka row of the window (services/stream_kpis.py), same shapes
    as KpiValue and the series of GET /api/kpis/{dashboard_id}, where these are null (not in the warehouse)."""

    period: str  # e.g. "60 min to 14:50 vs previous 60 min" (event_ts, the newest row ends the window)
    kpis: list[KpiValue]  # STREAM_KPI_IDS; value/previous null when the window has no row to count
    series: dict[str, Any]  # trip_temperature (object or null), excursions_by_trailer, excursion_rate_by_ambient,
    # high_risk_trips, time_in_state (lists of rows)
