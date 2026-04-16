from collections import defaultdict
from collections.abc import Callable, Mapping, MutableMapping
from contextlib import nullcontext
from threading import RLock
from typing import Any, ContextManager
from uuid import UUID, uuid4

from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core.models import Entry, EntryMeta, Request, Response


class SyncDictStorage(SyncBaseStorage):
    __dict: Mapping[str, MutableMapping[UUID, Entry]]
    __lock: ContextManager[Any]

    def __init__(self, *, threadsafe: bool = True) -> None:
        self.__dict = defaultdict(dict)
        self.__lock = RLock() if threadsafe else nullcontext()

    def create_entry(self, request: Request, response: Response, key: str, id_: UUID | None = None) -> Entry:
        entry_id = id_ or uuid4()
        entry = Entry(
            id=entry_id,
            request=request,
            meta=EntryMeta(),
            response=response,
            cache_key=key.encode(),
        )

        with self.__lock:
            self.__dict[key][entry_id] = entry

        return entry

    def get_entries(self, key: str) -> list[Entry]:
        with self.__lock:
            return list(self.__dict.get(key, {}).values())

    def update_entry(self, id: UUID, new_entry: Entry | Callable[[Entry], Entry]) -> Entry | None:
        with self.__lock:
            existing = self.__pop_entry(id)
            if existing is None:
                return None

            entry = new_entry(existing) if callable(new_entry) else new_entry
            key = entry.cache_key.decode()
            self.__dict[key][id] = entry

        return entry

    def remove_entry(self, id: UUID) -> None:
        with self.__lock:
            self.__pop_entry(id)

    def __pop_entry(self, entry_id: UUID) -> Entry | None:
        for subdict in self.__dict.values():
            entry = subdict.pop(entry_id, None)
            if entry is not None:
                return entry

        return None
