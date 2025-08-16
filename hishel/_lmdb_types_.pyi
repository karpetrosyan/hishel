from contextlib import contextmanager
from typing import Any, Iterator

class Database: ...

class Transaction:
    def get(self, key: bytes, *, db: Database | None = None) -> bytes | None:
        """
        Get the value associated with the given key.
        """
        pass

    def put(self, key: bytes, value: bytes, *, db: Database | None = None, dupdata: bool = False) -> None:
        """
        Put a key-value pair into the database.
        """
        pass

    def delete(self, key: bytes, *, db: Database | None = None) -> bool:
        """
        Delete the key from the database.
        """
        pass

    def cursor(self, db: Database) -> Any:
        """
        Create a cursor for iterating over key-value pairs in the database.
        """
        pass

class Environment:
    @contextmanager
    def begin(self, *, db: Database | None = None, write: bool = False) -> Iterator[Transaction]:
        """
        Begin a transaction in the environment.
        """
        raise NotImplementedError("It's only for type hinting purposes")

    def open_db(self, key: bytes, dupsort: bool = False) -> Database:
        """
        Open a database within the environment.
        """
        raise NotImplementedError("It's only for type hinting purposes")

def open(
    path: str,
    *,
    max_dbs: int = 0,
) -> Environment:
    """
    Open an LMDB environment at the specified path.
    """
    raise NotImplementedError("It's only for type hinting purposes")
