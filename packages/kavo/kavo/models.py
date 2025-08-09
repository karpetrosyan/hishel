import uuid
from typing import Any, Mapping, TypeAlias, TypedDict

from kavo.utils import UnixTimestamp

Response: TypeAlias = Mapping[str, Any]
Request: TypeAlias = Mapping[str, Any]


class CacheEntry(TypedDict):
    key: str
    responses: list[uuid.UUID]


class GetCacheEntryOptions(TypedDict, total=False):
    allow_incomplete: bool


class PutResponseOptions(TypedDict, total=False):
    # time in seconds after which the response should be considered stale (if not used)
    stale_after: int

    # if True, accessing a stale response won't refresh its staleness timer
    no_refresh_on_access: bool


class StampedeInfo(TypedDict):
    # we need this to find hanging responses
    # unix timestamp in seconds
    acquiredAt: UnixTimestamp

    # we need this lock id to not wait for other requests if the first was failed
    lock_id: uuid.UUID


class ResponseLastUsageInfo(TypedDict):
    response_id: uuid.UUID


def compare_stampede_info(info1: StampedeInfo | None, info2: StampedeInfo | None) -> bool:
    if info1 is None or info2 is None:
        return False
    return info1["lock_id"] == info2["lock_id"]
