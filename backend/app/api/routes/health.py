from typing import Annotated

from fastapi import APIRouter, Depends

from ...schemas.system import HealthResponse
from ...services.system_service import SystemService
from ..dependencies import get_system_service

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(service: Annotated[SystemService, Depends(get_system_service)]) -> dict:
    """Proves the login works and shows which user, role, warehouse, database and schema the API is using."""
    return service.health()
