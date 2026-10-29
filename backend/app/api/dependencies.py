"""Wiring: the only place that chooses which repository or source each service gets (Snowflake and Kafka today).
Routes receive services through Depends(), so they never build them or know about Snowflake or Kafka."""
from datetime import timedelta

from ..core.config import settings
from ..infrastructure.kafka_stream_source import KafkaStreamSource
from ..infrastructure.repositories.snowflake_kpi_repository import SnowflakeKpiRepository
from ..infrastructure.repositories.snowflake_system_repository import SnowflakeSystemRepository
from ..services.kpi_service import KpiService
from ..services.stream_service import StreamService
from ..services.system_service import SystemService

# One stream for the whole app (started and stopped in main.py): every viewer reads the same fleet state
stream_service = StreamService(KafkaStreamSource(), timedelta(minutes=settings.stream_history_minutes))


def get_system_service() -> SystemService:
    return SystemService(SnowflakeSystemRepository())


def get_kpi_service() -> KpiService:
    return KpiService(SnowflakeKpiRepository())


def get_stream_service() -> StreamService:
    return stream_service
