from __future__ import annotations

import abc
import time
import typing as tp
import uuid
from abc import ABC

from hishel.beta._core.models import CompletePair, IncompletePair, Request, Response


class SyncBaseStorage(ABC):
    @abc.abstractmethod
    def create_pair(
        self,
        request: Request,
        id: uuid.UUID | None = None,
    ) -> IncompletePair:
        """
        Store a request in the backend under the given key.

        Args:
            request: The request object to store.

        Returns:
            The created IncompletePair object representing the stored request.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def add_response(self, pair_id: uuid.UUID, response: Response, key: str | bytes) -> CompletePair:
        """
        Add a response to an existing request pair.

        Args:
            pair_id: The unique identifier of the request pair.
            response: The response object to add.
            key: The cache key associated with the request pair.

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

    def is_soft_deleted(self, pair: IncompletePair | CompletePair) -> bool:
        """
        Check if a pair is soft deleted based on its metadata.

        Args:
            pair: The request pair to check.

        Returns:
            True if the pair is soft deleted, False otherwise.
        """
        return pair.meta.deleted_at is not None and pair.meta.deleted_at > 0

    def is_safe_to_hard_delete(self, pair: IncompletePair | CompletePair) -> bool:
        """
        Check if a pair is safe to hard delete based on its metadata.

        If the pair has been soft deleted for more than 1 hour, it is considered safe to hard delete.

        Args:
            pair: The request pair to check.

        Returns:
            True if the pair is safe to hard delete, False otherwise.
        """
        return bool(pair.meta.deleted_at is not None and (pair.meta.deleted_at + 3600 < time.time()))

    @tp.overload
    def mark_pair_as_deleted(self, pair: CompletePair) -> CompletePair: ...
    @tp.overload
    def mark_pair_as_deleted(self, pair: IncompletePair) -> IncompletePair: ...
    def mark_pair_as_deleted(self, pair: CompletePair | IncompletePair) -> CompletePair | IncompletePair:
        """
        Mark a pair as soft deleted by setting its deleted_at timestamp.

        Args:
            pair: The request pair to mark as deleted.
        Returns:
            The updated request pair with the deleted_at timestamp set.
        """
        pair.meta.deleted_at = time.time()
        return pair


class AsyncBaseStorage(ABC):
    @abc.abstractmethod
    async def create_pair(
        self,
        request: Request,
        id: uuid.UUID | None = None,
    ) -> IncompletePair:
        """
        Store a request in the backend under the given key.

        Args:
            request: The request object to store.

        Returns:
            The created IncompletePair object representing the stored request.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def add_response(self, pair_id: uuid.UUID, response: Response, key: str | bytes) -> CompletePair:
        """
        Add a response to an existing request pair.

        Args:
            pair_id: The unique identifier of the request pair.
            response: The response object to add.
            key: The cache key associated with the request pair.

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

    def is_soft_deleted(self, pair: IncompletePair | CompletePair) -> bool:
        """
        Check if a pair is soft deleted based on its metadata.

        Args:
            pair: The request pair to check.

        Returns:
            True if the pair is soft deleted, False otherwise.
        """
        return pair.meta.deleted_at is not None and pair.meta.deleted_at > 0

    def is_safe_to_hard_delete(self, pair: IncompletePair | CompletePair) -> bool:
        """
        Check if a pair is safe to hard delete based on its metadata.

        If the pair has been soft deleted for more than 1 hour, it is considered safe to hard delete.

        Args:
            pair: The request pair to check.

        Returns:
            True if the pair is safe to hard delete, False otherwise.
        """
        return bool(pair.meta.deleted_at is not None and (pair.meta.deleted_at + 3600 < time.time()))

    @tp.overload
    def mark_pair_as_deleted(self, pair: CompletePair) -> CompletePair: ...
    @tp.overload
    def mark_pair_as_deleted(self, pair: IncompletePair) -> IncompletePair: ...
    def mark_pair_as_deleted(self, pair: CompletePair | IncompletePair) -> CompletePair | IncompletePair:
        """
        Mark a pair as soft deleted by setting its deleted_at timestamp.

        Args:
            pair: The request pair to mark as deleted.
        Returns:
            The updated request pair with the deleted_at timestamp set.
        """
        pair.meta.deleted_at = time.time()
        return pair
