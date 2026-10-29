"""Response shapes of GET /health and GET /api/tables. Upper-case names are Snowflake's column names."""
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    login_user: str
    role: str | None
    warehouse: str | None
    database: str | None
    # "schema" is a BaseModel attribute, so the field is schema_; the JSON key is still "schema" (alias)
    schema_: str | None = Field(alias="schema")


class TableRow(BaseModel):
    TABLE_SCHEMA: str
    TABLE_NAME: str
    TABLE_TYPE: str
    ROW_COUNT: int | None  # null for views
