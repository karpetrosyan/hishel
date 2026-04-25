from __future__ import annotations

import abc
import time
import typing as tp
import uuid

from ..models import Entry, Request, Response


class SyncBaseStorage(abc.ABC):
    @abc.abstractmethod
    def create_entry(self, request: Request, response: Response, key: str, id_: uuid.UUID | None = None) -> Entry:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_entries(self, key: str) -> tp.List[Entry]:
        raise NotImplementedError()

    @abc.abstractmethod
    def update_entry(
        self,
        id: uuid.UUID,
        new_entry: tp.Union[Entry, tp.Callable[[Entry], Entry]],
    ) -> tp.Optional[Entry]:
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_entry(self, id: uuid.UUID) -> None:
        """
        Soft delete an entry by its ID.

        Implementations should look up the entry, mark it as deleted by setting
        its ``deleted_at`` timestamp, and persist the update to storage.

        Args:
            id: The ID of the entry to soft delete.
        """
        raise NotImplementedError()

    def close(self) -> None:
        pass

    def refresh_entry_ttl(self, id: uuid.UUID) -> None:
        """
        Reset the TTL of an entry to the storage's default TTL.

        Concrete storage implementations own their TTL logic and should
        override this method to reset the given entry's expiration accordingly.

        Args:
            id: The ID of the entry whose TTL should be refreshed.
        """
        raise NotImplementedError()

    def is_soft_deleted(self, pair: Entry) -> bool:
        """
        Check if a pair is soft deleted based on its metadata.

        Args:
            pair: The request pair to check.

        Returns:
            True if the pair is soft deleted, False otherwise.
        """
        return pair.meta.deleted_at is not None and pair.meta.deleted_at > 0

    def is_safe_to_hard_delete(self, pair: Entry) -> bool:
        """
        Check if a pair is safe to hard delete based on its metadata.

        If the pair has been soft deleted for more than 1 hour, it is considered safe to hard delete.

        Args:
            pair: The request pair to check.

        Returns:
            True if the pair is safe to hard delete, False otherwise.
        """
        return bool(pair.meta.deleted_at is not None and (pair.meta.deleted_at + 3600 < time.time()))

    def mark_pair_as_deleted(self, pair: Entry) -> Entry:
        """
        Mark a pair as soft deleted by setting its deleted_at timestamp.

        Args:
            pair: The request pair to mark as deleted.
        Returns:
            The updated request pair with the deleted_at timestamp set.
        """
        pair.meta.deleted_at = time.time()
        return pair
