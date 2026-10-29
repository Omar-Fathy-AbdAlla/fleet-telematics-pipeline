from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ...schemas.stream import EventName
from ...services.stream_service import StreamService
from ..dependencies import get_stream_service

router = APIRouter(tags=["stream"])


@router.get("/stream", response_class=EventSourceResponse)
async def stream(
    service: Annotated[StreamService, Depends(get_stream_service)],
    events: Annotated[list[EventName], Query()] = [],
) -> AsyncIterable[ServerSentEvent]:
    """Live fleet over Server-Sent Events: events telemetry (list of rows), reefer (list of rows), alert (one AlertRow),
    kpis (LiveKpis) and stream_kpis (StreamKpis). A new viewer first gets a snapshot of everything, then only changes.
    ?events=stream_kpis&events=alert sends only those events (all when empty), e.g. pages without the map.
    See app/services/stream_service.py and dashboard/src/data/contract.js."""
    async for event, data in service.events():
        if not events or event in events:
            yield ServerSentEvent(event=event, data=data)
