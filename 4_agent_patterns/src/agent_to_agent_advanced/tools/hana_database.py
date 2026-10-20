"""Bounded read-only SAP HANA query Tool for the Codex SQL Generator Agent."""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

try:
    from hdbcli import dbapi
except ImportError:  # pragma: no cover - configuration error is reported at runtime
    dbapi = None

_READ_ONLY = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(ALTER|CALL|COMMIT|CREATE|DELETE|DROP|GRANT|INSERT|MERGE|REPLACE|REVOKE|ROLLBACK|TRUNCATE|UPDATE|UPSERT)\b",
    re.IGNORECASE,
)
_ENV_KEYS = (
    "HANA_HOST", "HANA_PORT", "HANA_USER", "HANA_PASSWORD",
    "HANA_SCHEMA", "HANA_ENCRYPT", "HANA_SSL_VALIDATE_CERTIFICATE",
)
_MAX_SCHEMA_TABLES = 50
_MAX_SCHEMA_COLUMNS = 500


class HanaQueryError(RuntimeError):
    """Raised without exposing credentials or driver internals."""


def _load_env_file() -> None:
    """Load only missing HANA settings from an explicitly configured env file."""
    configured = os.getenv("HANA_ENV_FILE", "").strip()
    path = Path(configured).expanduser() if configured else Path.cwd() / ".env"
    if not path.is_file():
        local_example = Path.home() / "Desktop/sap-app-in-app/.env"
        path = local_example if local_example.is_file() else None
    if path is None or not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key in _ENV_KEYS and not os.getenv(key):
            os.environ[key] = value.strip().strip("'\"")


def _bool(name: str, default: bool = True) -> bool:
    return os.getenv(name, str(default)).strip().lower() not in {"0", "false", "no"}


@contextmanager
def _connection() -> Iterator[Any]:
    _load_env_file()
    if dbapi is None:
        raise HanaQueryError("hdbcli가 설치되지 않았습니다.")
    host, user, password = (os.getenv(key, "").strip() for key in ("HANA_HOST", "HANA_USER", "HANA_PASSWORD"))
    if not all((host, user, password)):
        raise HanaQueryError("HANA 연결 정보가 없습니다. HANA_* 환경변수 또는 HANA_ENV_FILE을 설정하세요.")
    try:
        connection = dbapi.connect(
            address=host, port=int(os.getenv("HANA_PORT", "443")), user=user, password=password,
            encrypt=_bool("HANA_ENCRYPT"), sslValidateCertificate=_bool("HANA_SSL_VALIDATE_CERTIFICATE"),
        )
    except Exception as error:  # noqa: BLE001 - never surface a driver string containing connection details
        raise HanaQueryError("SAP HANA 읽기 전용 연결에 실패했습니다.") from error
    try:
        yield connection
    finally:
        connection.close()


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _bounded_limit(value: int, maximum: int, name: str) -> int:
    try:
        return max(1, min(maximum, int(value)))
    except (TypeError, ValueError) as error:
        raise HanaQueryError(f"{name}는 1부터 {maximum} 사이의 정수여야 합니다.") from error


def _current_schema(connection: Any) -> str:
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT CURRENT_SCHEMA FROM DUMMY")
        row = cursor.fetchone()
    except Exception as error:  # noqa: BLE001 - never expose driver internals
        raise HanaQueryError("SAP HANA 기본 스키마를 확인하지 못했습니다.") from error
    schema = str(row[0]).strip() if row and row[0] else ""
    if not schema:
        raise HanaQueryError("SAP HANA 기본 스키마가 설정되지 않았습니다.")
    return schema


def discover_hana_schema(
    *, max_tables: int = _MAX_SCHEMA_TABLES, max_columns: int = _MAX_SCHEMA_COLUMNS
) -> dict[str, Any]:
    """Return bounded table and column metadata from only the configured schema.

    This tool never accepts a user-provided SQL identifier. Metadata values are
    bound as database parameters and are returned only as SQL-generation context.
    """
    table_limit = _bounded_limit(max_tables, _MAX_SCHEMA_TABLES, "max_tables")
    column_limit = _bounded_limit(max_columns, _MAX_SCHEMA_COLUMNS, "max_columns")
    _load_env_file()
    with _connection() as connection:
        schema_name = os.getenv("HANA_SCHEMA", "").strip() or _current_schema(connection)
        try:
            table_cursor = connection.cursor()
            table_cursor.execute(
                """
                SELECT TABLE_NAME
                FROM SYS.TABLES
                WHERE SCHEMA_NAME = ?
                  AND IS_USER_DEFINED_TYPE = 'FALSE'
                ORDER BY TABLE_NAME
                LIMIT ?
                """,
                (schema_name, table_limit),
            )
            table_names = [str(row[0]) for row in table_cursor.fetchall() if row and row[0]]
            if not table_names:
                return {
                    "source": "sap_hana_schema_metadata",
                    "schema_name": schema_name,
                    "tables": [],
                    "table_count": 0,
                    "column_count": 0,
                    "limits": {"max_tables": table_limit, "max_columns": column_limit},
                }
            placeholders = ", ".join("?" for _ in table_names)
            column_cursor = connection.cursor()
            column_cursor.execute(
                f"""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE_NAME, POSITION
                FROM SYS.TABLE_COLUMNS
                WHERE SCHEMA_NAME = ?
                  AND TABLE_NAME IN ({placeholders})
                ORDER BY TABLE_NAME, POSITION
                LIMIT ?
                """,
                (schema_name, *table_names, column_limit),
            )
            columns_by_table: dict[str, list[dict[str, Any]]] = {name: [] for name in table_names}
            for table_name, column_name, data_type, position in column_cursor.fetchall():
                if table_name in columns_by_table:
                    columns_by_table[table_name].append(
                        {
                            "name": str(column_name),
                            "data_type": str(data_type),
                            "position": int(position),
                        }
                    )
        except Exception as error:  # noqa: BLE001 - never expose driver internals
            raise HanaQueryError("SAP HANA 스키마 메타데이터를 조회하지 못했습니다.") from error
    tables = [
        {"table_name": name, "columns": columns_by_table[name]}
        for name in table_names
    ]
    return {
        "source": "sap_hana_schema_metadata",
        "schema_name": schema_name,
        "tables": tables,
        "table_count": len(tables),
        "column_count": sum(len(table["columns"]) for table in tables),
        "limits": {"max_tables": table_limit, "max_columns": column_limit},
    }


def execute_hana_readonly_query(sql: str, *, max_rows: int = 100) -> dict[str, Any]:
    """Execute one bounded SELECT/CTE query and return tabular evidence only."""
    statement = str(sql or "").strip().rstrip(";")
    if not statement or not _READ_ONLY.match(statement) or _FORBIDDEN.search(statement) or ";" in statement:
        raise HanaQueryError("HANA Tool은 단일 읽기 전용 SELECT 또는 WITH 쿼리만 실행할 수 있습니다.")
    limit = _bounded_limit(max_rows, 1000, "max_rows")
    started = time.perf_counter()
    with _connection() as connection:
        try:
            cursor = connection.cursor()
            cursor.execute(statement)
            columns = [item[0] for item in cursor.description or []]
            rows = [
                dict(zip(columns, map(_value, row), strict=True))
                for row in cursor.fetchmany(limit)
            ]
        except Exception as error:  # noqa: BLE001 - never expose driver internals
            raise HanaQueryError("SAP HANA 읽기 전용 조회를 실행하지 못했습니다.") from error
    return {
        "source": "sap_hana_readonly", "columns": columns, "rows": rows,
        "row_count": len(rows), "max_rows": limit,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
