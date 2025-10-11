import uuid
from typing import Any

import pytest
from inline_snapshot import snapshot
from time_machine import travel

from hishel._utils import print_sqlite_state
from hishel.beta import Request
from hishel.beta._core._async._storages._sqlite import AsyncSqliteStorage


@pytest.mark.anyio
@travel("2024-01-01 00:00:00")
async def test_create_pair(use_temp_dir: Any) -> None:
    storage = AsyncSqliteStorage()

    await storage.create_pair(
        id=uuid.UUID(int=0),
        request=Request(
            method="GET",
            url="https://example.com",
        ),
    )

    assert print_sqlite_state(storage._sync_sqlite_storage.connection) == snapshot("""\
================================================================================
DATABASE SNAPSHOT
================================================================================

TABLE: entries
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    id              = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    cache_key       = NULL
    data            = (bytes) 0x84a26964c41000000000000000000000000000000000a772657175657374... (130 bytes)
    created_at      = 2024-01-01
    deleted_at      = NULL

TABLE: streams
--------------------------------------------------------------------------------
Rows: 0

  (empty)

================================================================================\
""")
