"""KpiRepository on Snowflake: runs a query from queries/ and returns its rows ready for JSON."""
from decimal import Decimal

from .. import snowflake_client
from ..sql_loader import load_sql


class SnowflakeKpiRepository:
    def fetch_rows(self, query: str, params: dict) -> list[dict]:
        rows = snowflake_client.fetch_all(load_sql(query), params)
        return [{column.lower(): _to_json(value) for column, value in row.items()} for row in rows]


def _to_json(value):
    """Snowflake returns NUMBER with decimals as Decimal, which JSON cannot hold: send it as float."""
    return float(value) if isinstance(value, Decimal) else value
