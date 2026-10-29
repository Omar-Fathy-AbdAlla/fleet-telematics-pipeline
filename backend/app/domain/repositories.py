"""Contracts the services depend on. Services never import Snowflake: infrastructure/repositories/ implements
these (Snowflake today), and api/dependencies.py chooses the implementation."""
from typing import Protocol


class SystemRepository(Protocol):
    def current_session(self) -> dict:
        """One row: LOGIN_USER, ROLE, WAREHOUSE, DATABASE, SCHEMA of the current session."""
        ...

    def list_tables(self) -> list[dict]:
        """One row per table or view: TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ROW_COUNT."""
        ...


class KpiRepository(Protocol):
    def fetch_rows(self, query: str, params: dict) -> list[dict]:
        """Rows of the query named `query` (e.g. "kpis/margin_proxy", "series/lane_otd") run with `params`
        (the period dates). Column names in lower case, numbers as int or float."""
        ...
