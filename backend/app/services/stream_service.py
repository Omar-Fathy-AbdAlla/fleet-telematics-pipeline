"""Runs the live stream for the whole app: one background reader fills FleetState from the source, and a loop
sends the changes every TICK_SECONDS to every connected viewer. Each viewer has its own queue, so a slow browser
never blocks the reader or the other viewers. Started and stopped in main.py."""
import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from ..domain.stream_source import StreamSource
from .fleet_state import Event, FleetState
from .stream_kpis import kept

logger = logging.getLogger(__name__)

TICK_SECONDS = 1  # how often changes are checked; nothing is sent when nothing changed
RETRY_SECONDS = 10  # wait after the source fails (e.g. Kafka down) before reading again


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StreamService:
    def __init__(self, source: StreamSource, history: timedelta):
        self._source = source
        self._history = history
        self._state = FleetState(history)
        self._viewers: set[asyncio.Queue[list[Event]]] = set()
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._send_changes())]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def events(self) -> AsyncIterator[Event]:
        """One viewer: the snapshot first (so the page is never empty), then every tick's changes until it leaves."""
        queue: asyncio.Queue[list[Event]] = asyncio.Queue()
        self._viewers.add(queue)  # before the snapshot, so no change is missed in between
        try:
            for event in self._state.snapshot(_now()):
                yield event
            while True:
                for event in await queue.get():
                    yield event
        finally:
            self._viewers.discard(queue)

    async def _read(self) -> None:
        """Reads the source forever, starting kept(STREAM_HISTORY_MINUTES) back (the stream KPI window, the previous
        one and a margin). After any failure it waits and reads the same again: FleetState drops the rows it has."""
        while True:
            try:
                async for message in self._source.messages(since=_now() - kept(self._history)):
                    try:
                        self._state.apply(message, _now())
                    except (KeyError, TypeError, ValueError):  # counted as rejected (KPI 58), row not kept
                        logger.warning("Rejected a %s message (not JSON, or no valid vehicle_id / event_ts): partition %s "
                                       "offset %s: %s", message.kind, message.partition, message.offset, message.row)
            except Exception:
                logger.exception("Stream source failed, reading again in %s s", RETRY_SECONDS)
            await asyncio.sleep(RETRY_SECONDS)

    async def _send_changes(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            events = self._state.take_changes(_now())
            if events:
                for queue in self._viewers:
                    queue.put_nowait(events)
