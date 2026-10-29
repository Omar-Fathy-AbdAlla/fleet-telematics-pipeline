"""The only module that talks to Snowflake. Repositories call fetch_all() and never touch the connection."""
from contextlib import suppress

import snowflake.connector
from snowflake.connector import DictCursor, SnowflakeConnection
from snowflake.connector.errors import Error, ReauthenticationRequest

from ..core.config import settings

_connection: SnowflakeConnection | None = None

# Snowflake error codes that mean "log in again": session no longer exists, session expired, login token expired
LOGIN_REQUIRED_ERRNOS = {390111, 390112, 390114}


def get_connection() -> SnowflakeConnection:
    """Shared connection: opened on first use, reopened if Snowflake closed it (session timeout)."""
    global _connection
    if _connection is None or _connection.is_closed():
        _connection = snowflake.connector.connect(
            account=settings.snowflake_api_account,
            user=settings.snowflake_api_user,
            password=settings.snowflake_api_password,
            database=settings.snowflake_api_database,
            role=settings.snowflake_api_role,
            warehouse=settings.snowflake_api_warehouse,
            schema=settings.snowflake_api_schema,
            client_session_keep_alive=True,
            enable_server_session_keep_alive_auto_detection=False,  # no async queries: plain logout on close
        )
    return _connection


def fetch_all(sql: str, params: dict | tuple | None = None) -> list[dict]:
    """Runs one query and returns the rows as dicts keyed by column name (upper case, as Snowflake returns them).
    If the login has expired (the connection is still open but Snowflake no longer accepts it, e.g. after a few
    hours), opens a new connection and runs the query once more. Any other error is raised as is."""
    try:
        return _execute(sql, params)
    except Error as error:
        if not _login_expired(error):
            raise
        close_connection()
        return _execute(sql, params)


def _login_expired(error: Error) -> bool:
    return isinstance(error, ReauthenticationRequest) or error.errno in LOGIN_REQUIRED_ERRNOS


def _execute(sql: str, params: dict | tuple | None) -> list[dict]:
    with get_connection().cursor(DictCursor) as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def close_connection() -> None:
    """Closes the shared connection. Errors are ignored: an expired session cannot log out cleanly, and the
    connection is dropped either way."""
    global _connection
    if _connection is not None:
        with suppress(Error):
            _connection.close()
        _connection = None
