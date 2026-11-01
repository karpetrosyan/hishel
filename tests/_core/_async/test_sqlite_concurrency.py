import sqlite3
import time

import anyio
import pytest

from hishel._core._storages._async_sqlite import STORAGE_CHUNK_SIZE, AsyncSqliteStorage

from .test_sqlite_storage import new_storage, read, rows, store


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_concurrent_tasks_on_one_storage():
    storage = await new_storage()
    body = b"x" * (STORAGE_CHUNK_SIZE + 10)

    async def worker(i):
        await store(storage, key=f"k{i % 5}", body=body)
        for entry in await storage.get_entries(f"k{i % 5}"):
            assert await read(entry) == body

    async with anyio.create_task_group() as tg:
        for i in range(100):
            tg.start_soon(worker, i)
    assert await rows(storage) == 100


@pytest.mark.anyio
async def test_two_storages_sharing_a_file(tmp_path):
    path = tmp_path / "shared.db"
    first = AsyncSqliteStorage(database_path=path)
    second = AsyncSqliteStorage(database_path=path)
    await first._ensure_connection()
    await second._ensure_connection()
    body = b"x" * (STORAGE_CHUNK_SIZE + 10)

    async def worker(storage, i):
        await store(storage, key=f"k{i}", body=body)

    async with anyio.create_task_group() as tg:
        for i in range(100):
            tg.start_soon(worker, first if i % 2 else second, i)

    for i in range(100):
        storage = second if i % 2 else first
        [entry] = await storage.get_entries(f"k{i}")
        assert await read(entry) == body
    await first.close()
    await second.close()


@pytest.mark.anyio
async def test_failed_write_leaves_no_open_transaction(tmp_path):
    path = tmp_path / "shared.db"
    storage = AsyncSqliteStorage(database_path=path)
    other_process = AsyncSqliteStorage(database_path=path)
    await store(storage, key="first")
    [entry] = await storage.get_entries("first")
    connection = await storage._ensure_connection()
    await connection.execute("PRAGMA busy_timeout=50")

    blocker = sqlite3.connect(path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    await storage.remove_entry(entry.id)
    blocker.execute("COMMIT")
    blocker.close()

    # The removal failed, and this lookup must not pin what it sees.
    assert len(await storage.get_entries("first")) == 1
    await store(other_process, key="other")

    assert len(await storage.get_entries("other")) == 1
    await store(storage, key="second")
    assert len(await storage.get_entries("second")) == 1
    await storage.close()
    await other_process.close()


@pytest.mark.anyio
async def test_cancelled_write_does_not_keep_the_write_lock(tmp_path):
    path = tmp_path / "c.db"
    storage = AsyncSqliteStorage(database_path=path)
    await store(storage)
    connection = await storage._ensure_connection()

    def slow():
        time.sleep(0.2)
        return 1

    connection._real_connection.create_function("slow", 0, slow)

    async with anyio.create_task_group() as tg:
        tg.start_soon(storage._try_write, "UPDATE entries SET last_accessed_at = slow()", ())
        await anyio.sleep(0.05)
        tg.cancel_scope.cancel()

    other_process = sqlite3.connect(path, timeout=0.1)
    other_process.execute("UPDATE entries SET last_accessed_at = 2")
    other_process.commit()
    other_process.close()
    await storage.close()
