"""SystemRepository on Snowflake: session info and the table list, from Snowflake's own metadata."""
from .. import snowflake_client

CURRENT_SESSION_SQL = (
    "SELECT CURRENT_USER() AS login_user, CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS warehouse, "
    "CURRENT_DATABASE() AS database, CURRENT_SCHEMA() AS schema"
)

LIST_TABLES_SQL = (
    "SELECT table_schema, table_name, table_type, row_count "
    "FROM information_schema.tables "
    "WHERE table_schema <> 'INFORMATION_SCHEMA' "
    "ORDER BY table_schema, table_name"
)


class SnowflakeSystemRepository:
    def current_session(self) -> dict:
        return snowflake_client.fetch_all(CURRENT_SESSION_SQL)[0]

    def list_tables(self) -> list[dict]:
        return snowflake_client.fetch_all(LIST_TABLES_SQL)
