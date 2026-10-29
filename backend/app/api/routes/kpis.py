from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ...schemas.dashboard import DashboardResponse
from ...services.kpi_service import DASHBOARD_SERIES, KpiService
from ..dependencies import get_kpi_service

router = APIRouter(prefix="/kpis", tags=["kpis"])


@router.get("/{dashboard_id}", response_model=DashboardResponse)
def dashboard_kpis(
    dashboard_id: str,
    service: Annotated[KpiService, Depends(get_kpi_service)],
    kpi_ids: Annotated[list[int], Query()] = [],
) -> dict:
    """KPI cards (?kpi_ids=1&kpi_ids=2...) and chart series of one dashboard, last 30 days vs previous 30 days.
    See app/services/kpi_service.py."""
    # dashboard_id becomes part of SQL file names, so only known ids are accepted
    if dashboard_id not in DASHBOARD_SERIES:
        raise HTTPException(status_code=404, detail=f"Unknown dashboard '{dashboard_id}'. Known: {', '.join(DASHBOARD_SERIES)}")
    return service.dashboard(dashboard_id, kpi_ids)
