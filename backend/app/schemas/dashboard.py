"""Response shape of GET /api/kpis/{dashboard_id}, as in dashboard/src/data/contract.js (DashboardResponse, KpiValue).
Units of value/previous are the KPI's unit in dashboard/src/kpis/definitions.js (metric: km, L, USD)."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class KpiValue(BaseModel):
    kpi_id: int
    value: float | None  # current period; null when the KPI is not in the warehouse
    previous: float | None  # previous period, for the trend arrow


class DashboardResponse(BaseModel):
    dashboard: str
    period: str
    as_of: datetime  # when the backend calculated the values (UTC)
    kpis: list[KpiValue]
    series: dict[str, list[dict[str, Any]] | None]  # chart rows per series name; null when not in the warehouse
