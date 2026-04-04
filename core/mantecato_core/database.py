import os
import re
from decimal import Decimal
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Set it to your PostgreSQL connection string."
        )
    return url


async def create_pool(dsn: str | None = None, **kwargs) -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        await _pool.close()
    url = dsn or _get_database_url()
    _pool = await asyncpg.create_pool(
        url,
        min_size=kwargs.get("min_size", 2),
        max_size=kwargs.get("max_size", 20),
    )
    return _pool


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        await create_pool()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


_PARAM_RE = re.compile(
    r"\{\{\s*(\w+)(?:::([\w\[\]]+))?\s*\}\}|\{\s*(\w+)(?:::([\w\[\]]+))?\s*\}"
)


def _substitute_params(sql: str, params: dict[str, Any]) -> tuple[str, list[Any]]:
    args: list[Any] = []

    def _replacer(m: re.Match) -> str:
        name = m.group(1) or m.group(3)
        type_cast = (
            f"::{m.group(2) or m.group(4)}" if (m.group(2) or m.group(4)) else ""
        )
        args.append(params.get(name))
        return f"${len(args)}{type_cast}"

    query = _PARAM_RE.sub(_replacer, sql)
    return query, args


def _convert_row(row: asyncpg.Record) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            d[key] = float(value)
        else:
            d[key] = value
    return d


async def raw_query(
    sql: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    if params is None:
        params = {}
    pool = await get_pool()
    query, args = _substitute_params(sql, params)
    rows = await pool.fetch(query, *args)
    return [_convert_row(r) for r in rows]


async def raw_query_one(
    sql: str, params: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    results = await raw_query(sql, params)
    return results[0] if results else None


async def paged_raw_query(
    sql: str,
    params: dict[str, Any],
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    count_sql = f"SELECT COUNT(*) AS count FROM ({sql}) AS t"
    count_row = await raw_query_one(count_sql, params)
    count = int(count_row["count"]) if count_row else 0

    paged_sql = f"{sql} LIMIT {page_size} OFFSET {(page - 1) * page_size}"
    data = await raw_query(paged_sql, params)

    return {"data": data, "count": count, "page": page, "pageSize": page_size}


def get_date_trunc(granularity: str) -> str:
    valid = ["minute", "hour", "day", "week", "month", "year"]
    if granularity not in valid:
        return "date_trunc('day', we.created_at)"
    return f"date_trunc('{granularity}', we.created_at)"
