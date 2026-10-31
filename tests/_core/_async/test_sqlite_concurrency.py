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
