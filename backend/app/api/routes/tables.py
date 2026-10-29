from typing import Annotated

from fastapi import APIRouter, Depends

from ...schemas.system import TableRow
from ...services.system_service import SystemService
from ..dependencies import get_system_service

router = APIRouter(tags=["system"])


@router.get("/tables", response_model=list[TableRow])
def tables(service: Annotated[SystemService, Depends(get_system_service)]) -> list[dict]:
    """Every table and view the API user can see in the configured database, with its row count."""
    return service.tables()
