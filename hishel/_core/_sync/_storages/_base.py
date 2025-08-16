import abc
import typing as tp
import uuid
from abc import ABC

from ...models import Request, RequestPair, Response

RemoveTypes: tp.TypeAlias = tp.Union[str, Response]


class SyncBaseStorage(ABC):
    @abc.abstractmethod
    def store_request(
        self,
        key: str,
        request: Request,
        /,
        ttl: tp.Optional[float] = None,
        refresh_ttl_on_access: tp.Optional[bool] = None,
    ) -> tuple[uuid.UUID, Request]:
        raise NotImplementedError()

    @abc.abstractmethod
    def store_response(self, pair_id: uuid.UUID, response: Response) -> Response:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_responses(self, key: str, /, complete_only: tp.Optional[bool] = None) -> tp.List[RequestPair]:
        raise NotImplementedError()

    @abc.abstractmethod
    def update_entry_extra(
        self,
        key: str,
        extra: tp.Union[tp.Mapping[str, tp.Any], tp.MutableMapping[str, tp.Any]],
    ) -> None:
        raise NotImplementedError()
