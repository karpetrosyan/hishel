from collections.abc import Callable
from uuid import UUID

from hishel._core._storages._async_base import AsyncBaseStorage
from hishel._core._storages._sync_dict import SyncDictStorage
from hishel._core.models import Entry, Request, Response

try:
    from anyio import Semaphore
except ImportError:
    from asyncio import Semaphore  # type: ignore[assignment]


class AsyncDictStorage(AsyncBaseStorage):
    __semaphore: Semaphore
    __sync: SyncDictStorage

    def __init__(self) -> None:
        self.__semaphore = Semaphore(1)
        self.__sync = SyncDictStorage(threadsafe=False)

    async def create_entry(self, request: Request, response: Response, key: str, id_: UUID | None = None) -> Entry:
        async with self.__semaphore:
            return self.__sync.create_entry(request, response, key, id_)

    async def get_entries(self, key: str) -> list[Entry]:
        async with self.__semaphore:
            return self.__sync.get_entries(key)

    async def update_entry(self, id: UUID, new_entry: Entry | Callable[[Entry], Entry]) -> Entry | None:
        async with self.__semaphore:
            return self.__sync.update_entry(id, new_entry)

    async def remove_entry(self, id: UUID) -> None:
        async with self.__semaphore:
            return self.__sync.remove_entry(id)
