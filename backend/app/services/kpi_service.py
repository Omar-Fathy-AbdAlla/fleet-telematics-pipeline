"""Warehouse KPIs and chart series of one dashboard: last 30 days vs the previous 30 days.
The window ends yesterday (DATA_LAG_DAYS = 1): today is still loading. A trip lands in FCT_TRIPS only when completed,
so trips count on the day they finished (ARRIVAL_TS), which keeps every past day complete.
KPIs and charts that are not in the warehouse (live stream, platform) are returned as null. The stream ones are
calculated from Kafka instead and sent in the stream_kpis event of GET /api/stream (services/stream_kpis.py).
The SQL is in infrastructure/queries/kpis/<query>.sql and infrastructure/queries/series/<name>.sql."""
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from ..domain.repositories import KpiRepository

PERIOD_DAYS = 30
DATA_LAG_DAYS = 1

# kpi_id -> query in queries/kpis/. Any other kpi_id is not in the warehouse and gets value/previous null.
KPI_QUERIES = {
    1: "on_time_delivery_rate",
    2: "on_time_pickup_rate",
    3: "average_delivery_delay",
    5: "severe_delay_rate",
    6: "destination_queue_time",
    7: "dock_time",
    8: "trip_duration_variance",
    19: "total_fuel_spend",
    20: "fuel_cost_per_km",
    21: "fuel_efficiency",
    22: "fuel_price_variance",
    24: "idle_time_share",
    26: "revenue_per_km",
    27: "fuel_cost_pct_of_revenue",
    28: "margin_proxy",
    30: "km_per_truck_per_day",
    36: "incident_rate",
    38: "claim_cost",
    41: "total_maintenance_cost",
    42: "maintenance_downtime",
    43: "orders_per_truck",
    44: "maintenance_cost_per_km",
    46: "truck_availability",
    65: "warehouse_data_freshness",
}

# dashboard id (dashboard/src/dashboards.js) -> its chart series. Each name is a file in queries/series/,
# except the names in SERIES_NOT_IN_WAREHOUSE, which are returned as null.
DASHBOARD_SERIES = {
    "executive": ("service_trend", "unit_economics_trend"),
    "delivery": ("lane_otd", "worst_customers", "delay_by_hour", "facility_queue"),
    "cold_chain": ("trip_temperature", "excursions_by_trailer", "excursion_rate_by_ambient", "high_risk_trips"),
    "fuel": ("fuel_spend_trend", "fuel_efficiency_by_route", "fuel_efficiency_by_truck", "price_by_state", "purchase_outliers"),
    "safety": ("driver_scorecard", "time_in_state", "incidents_by_type"),
    "maintenance": ("cost_trend", "maintenance_mix", "repeat_trucks", "cost_by_model_year"),
    "platform": (),
}
SERIES_NOT_IN_WAREHOUSE = {
    # reefer stream
    "trip_temperature", "excursions_by_trailer", "excursion_rate_by_ambient", "high_risk_trips",
    # telemetry stream
    "time_in_state",
}


@dataclass(frozen=True)
class Period:
    """Inclusive dates. Field names are the SQL parameters: %(previous_start)s, %(current_start)s, %(current_end)s."""
    previous_start: date
    current_start: date
    current_end: date


def period_ending(current_end: date) -> Period:
    current_start = current_end - timedelta(days=PERIOD_DAYS - 1)
    return Period(previous_start=current_start - timedelta(days=PERIOD_DAYS), current_start=current_start, current_end=current_end)


class KpiService:
    def __init__(self, repository: KpiRepository):
        self._repository = repository

    def dashboard(self, dashboard_id: str, kpi_ids: list[int]) -> dict:
        """DashboardResponse (dashboard/src/data/contract.js). dashboard_id must be a key of DASHBOARD_SERIES."""
        as_of = datetime.now(UTC)
        period = period_ending(as_of.date() - timedelta(days=DATA_LAG_DAYS))
        params = asdict(period)
        return {
            "dashboard": dashboard_id,
            "period": f"{PERIOD_DAYS} days to {period.current_end} vs previous {PERIOD_DAYS} days",
            "as_of": as_of,
            "kpis": [self._kpi(kpi_id, params) for kpi_id in kpi_ids],
            "series": {name: self._series(name, params) for name in DASHBOARD_SERIES[dashboard_id]},
        }

    def _kpi(self, kpi_id: int, params: dict) -> dict:
        """The KPI query returns one row per period: period ('value' or 'previous') and kpi_value."""
        query = KPI_QUERIES.get(kpi_id)
        rows = self._repository.fetch_rows(f"kpis/{query}", params) if query else []
        by_period = {row["period"]: row["kpi_value"] for row in rows}
        return {"kpi_id": kpi_id, "value": by_period.get("value"), "previous": by_period.get("previous")}

    def _series(self, name: str, params: dict) -> list[dict] | None:
        return None if name in SERIES_NOT_IN_WAREHOUSE else self._repository.fetch_rows(f"series/{name}", params)
