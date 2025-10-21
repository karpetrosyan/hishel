import json
import os
import sqlite3
from datetime import date
from typing import Any

import anysqlite
import pytest


def format_value(value: Any, col_name: str, col_type: str) -> str:
    """Format a value for display based on its type and column name."""

    if value is None:
        return "NULL"

    # Handle BLOB columns
    if col_type.upper() == "BLOB":
        if isinstance(value, bytes):
            # Try to decode as UTF-8 string first
            try:
                decoded = value.decode("utf-8")
                # Check if it looks like JSON
                if decoded.strip().startswith("{") or decoded.strip().startswith("["):
                    try:
                        parsed = json.loads(decoded)
                        return f"(JSON) {json.dumps(parsed, indent=2)}"
                    except json.JSONDecodeError:
                        pass
                # Show string if it's printable
                if all(32 <= ord(c) <= 126 or c in "\n\r\t" for c in decoded):
                    return f"(str) '{decoded}'"
            except UnicodeDecodeError:
                pass

            # Show hex representation for binary data
            hex_str = value.hex()
            if len(hex_str) > 64:
                return f"(bytes) 0x{hex_str[:60]}... ({len(value)} bytes)"
            return f"(bytes) 0x{hex_str} ({len(value)} bytes)"
        return repr(value)

    # Handle timestamps - ONLY show date, not the raw timestamp
    if col_name.endswith("_at") and isinstance(value, (int, float)):
        try:
            dt = date.fromtimestamp(value)
            return dt.isoformat()  # Changed: removed the timestamp prefix
        except (ValueError, OSError):
            return str(value)

    # Handle TEXT columns
    if col_type.upper() == "TEXT":
        return f"'{value}'"

    # Handle other types
    return str(value)


def print_sqlite_state(conn: sqlite3.Connection) -> str:
    """
    Print all tables and their rows in a pretty format suitable for inline snapshots.

    Args:
        conn: SQLite database connection

    Returns:
        Formatted string representation of the database state
    """
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    output_lines = []
    output_lines.append("=" * 80)
    output_lines.append("DATABASE SNAPSHOT")
    output_lines.append("=" * 80)

    for table_name in tables:
        # Get column information
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        column_types = {col[1]: col[2] for col in columns}

        # Get all rows
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        output_lines.append("")
        output_lines.append(f"TABLE: {table_name}")
        output_lines.append("-" * 80)
        output_lines.append(f"Rows: {len(rows)}")
        output_lines.append("")

        if not rows:
            output_lines.append("  (empty)")
            continue

        # Format each row
        for idx, row in enumerate(rows, 1):
            output_lines.append(f"  Row {idx}:")

            for col_name, value in zip(column_names, row):
                col_type = column_types[col_name]
                formatted_value = format_value(value, col_name, col_type)
                output_lines.append(f"    {col_name:15} = {formatted_value}")

            if idx < len(rows):
                output_lines.append("")

    output_lines.append("")
    output_lines.append("=" * 80)

    result = "\n".join(output_lines)
    return result


async def aprint_sqlite_state(conn: anysqlite.Connection) -> str:
    """
    Print all tables and their rows in a pretty format suitable for inline snapshots.

    Args:
        conn: SQLite database connection

    Returns:
        Formatted string representation of the database state
    """
    cursor = await conn.cursor()

    # Get all table names
    await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in await cursor.fetchall()]

    output_lines = []
    output_lines.append("=" * 80)
    output_lines.append("DATABASE SNAPSHOT")
    output_lines.append("=" * 80)

    for table_name in tables:
        # Get column information
        await cursor.execute(f"PRAGMA table_info({table_name})")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        column_types = {col[1]: col[2] for col in columns}

        # Get all rows
        await cursor.execute(f"SELECT * FROM {table_name}")
        rows = await cursor.fetchall()

        output_lines.append("")
        output_lines.append(f"TABLE: {table_name}")
        output_lines.append("-" * 80)
        output_lines.append(f"Rows: {len(rows)}")
        output_lines.append("")

        if not rows:
            output_lines.append("  (empty)")
            continue

        # Format each row
        for idx, row in enumerate(rows, 1):
            output_lines.append(f"  Row {idx}:")

            for col_name, value in zip(column_names, row):
                col_type = column_types[col_name]
                formatted_value = format_value(value, col_name, col_type)
                output_lines.append(f"    {col_name:15} = {formatted_value}")

            if idx < len(rows):
                output_lines.append("")

    output_lines.append("")
    output_lines.append("=" * 80)

    result = "\n".join(output_lines)
    return result


@pytest.fixture()
def use_temp_dir(tmpdir):
    cur_dir = os.getcwd()
    os.chdir(tmpdir)
    yield
    os.chdir(cur_dir)
