"""Contract for the live stream. Services never import Kafka: infrastructure/kafka_stream_source.py implements this,
and api/dependencies.py chooses the implementation."""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

StreamKind = Literal["telemetry", "reefer"]


@dataclass(frozen=True)
class StreamMessage:
    kind: StreamKind
    row: dict | None  # the message JSON as a dict (catalog 3.14 / 3.15 columns + the silver flags); None = not JSON
    partition: int  # Kafka partition and offset: the same message read again has the same partition + offset
    offset: int
    timestamp: datetime  # Kafka message time (UTC): when upstream wrote it


class StreamSource(Protocol):
    def messages(self, since: datetime) -> AsyncIterator[StreamMessage]:
        """Every message produced at or after `since`, then new ones as they arrive (never ends)."""
        ...
