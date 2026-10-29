"""Turns Snowflake failures into clean HTTP errors. Registered in main.py."""
from fastapi import Request
from fastapi.responses import JSONResponse
from snowflake.connector.errors import Error as SnowflakeError


async def snowflake_error_handler(_: Request, exc: SnowflakeError) -> JSONResponse:
    """Any Snowflake failure (login, SQL, timeout) becomes a 503 with the Snowflake message, not a stack trace."""
    return JSONResponse(status_code=503, content={"detail": f"Snowflake error: {exc.msg}"})
