"""Health and table listing: which Snowflake session the API uses, and what it can see."""
from ..domain.repositories import SystemRepository


class SystemService:
    def __init__(self, repository: SystemRepository):
        self._repository = repository

    def health(self) -> dict:
        """Proves the login works: status "ok" plus the session's user, role, warehouse, database, schema."""
        row = self._repository.current_session()
        return {"status": "ok", **{column.lower(): value for column, value in row.items()}}

    def tables(self) -> list[dict]:
        """Every table and view the API user can see in the configured database, with its row count."""
        return self._repository.list_tables()
