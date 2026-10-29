"""Reads SQL files from infrastructure/queries/. Each file is read once, then served from memory."""
from functools import cache
from pathlib import Path

QUERIES_DIR = Path(__file__).resolve().parent / "queries"


@cache
def load_sql(path: str) -> str:
    """load_sql("kpis/margin_proxy") returns the text of queries/kpis/margin_proxy.sql.
    `path` comes from code constants only, never from a request."""
    return (QUERIES_DIR / f"{path}.sql").read_text(encoding="utf-8")
