import abc
import typing as tp
import uuid
from abc import ABC

from hishel._core.models import CompletePair, IncompletePair, Request, Response


class SyncBaseStorage(ABC):
    @abc.abstractmethod
    def create_pair(
        self,
        key: str,
        request: Request,
        /,
        ttl: tp.Optional[float] = None,
        refresh_ttl_on_access: tp.Optional[bool] = None,
    ) -> IncompletePair:
        """
        Store a request in the backend under the given key.

        Args:
            key: Unique identifier for grouping or looking up stored requests.
            request: The request object to store.
            ttl: Optional time-to-live (in seconds). If set, the entry expires after
                the given duration.
            refresh_ttl_on_access: If True, accessing this entry refreshes its TTL.
                If False, the TTL is fixed. If None, uses the backend's default behavior.

        Returns:
            The created IncompletePair object representing the stored request.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_response(self, pair_id: uuid.UUID, response: Response) -> CompletePair:
        """
        Add a response to an existing request pair.

        Args:
            pair_id: The unique identifier of the request pair.
            response: The response object to add.

        Returns:
            The updated response object.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_pairs(self, key: str) -> tp.List[CompletePair]:
        """
        Retrieve all responses associated with a given key.

        Args:
            key: The unique identifier for the request pairs.
            complete_only: If True, only return pairs with responses. If False,
                only return pairs without responses. If None, return all pairs.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def update_pair(
        self,
        id: uuid.UUID,
        new_pair: tp.Union[CompletePair, tp.Callable[[CompletePair], CompletePair]],
    ) -> tp.Optional[CompletePair]:
        """
        Update an existing request pair.

        Args:
            id: The unique identifier of the request pair to update.
            new_pair: The new pair data or a callable that takes the current pair
                and returns the updated pair.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def remove(self, id: uuid.UUID) -> None:
        """
        Remove a request pair from the storage.

        Args:
            id: The unique identifier of the request pair to remove.
        """
        raise NotImplementedError()


class AsyncBaseStorage(ABC):
    @abc.abstractmethod
    async def create_pair(
        self,
        key: str,
        request: Request,
        /,
        ttl: tp.Optional[float] = None,
        refresh_ttl_on_access: tp.Optional[bool] = None,
    ) -> IncompletePair:
        """
        Store a request in the backend under the given key.

        Args:
            key: Unique identifier for grouping or looking up stored requests.
            request: The request object to store.
            ttl: Optional time-to-live (in seconds). If set, the entry expires after
                the given duration.
            refresh_ttl_on_access: If True, accessing this entry refreshes its TTL.
                If False, the TTL is fixed. If None, uses the backend's default behavior.

        Returns:
            The created IncompletePair object representing the stored request.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def add_response(self, pair_id: uuid.UUID, response: Response) -> CompletePair:
        """
        Add a response to an existing request pair.

        Args:
            pair_id: The unique identifier of the request pair.
            response: The response object to add.

        Returns:
            The updated response object.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def get_pairs(self, key: str) -> tp.List[CompletePair]:
        """
        Retrieve all responses associated with a given key.

        Args:
            key: The unique identifier for the request pairs.
            complete_only: If True, only return pairs with responses. If False,
                only return pairs without responses. If None, return all pairs.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def update_pair(
        self,
        id: uuid.UUID,
        new_pair: tp.Union[CompletePair, tp.Callable[[CompletePair], CompletePair]],
    ) -> tp.Optional[CompletePair]:
        """
        Update an existing request pair.

        Args:
            id: The unique identifier of the request pair to update.
            new_pair: The new pair data or a callable that takes the current pair
                and returns the updated pair.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def remove(self, id: uuid.UUID) -> None:
        """
        Remove a request pair from the storage.

        Args:
            id: The unique identifier of the request pair to remove.
        """
        raise NotImplementedError()
