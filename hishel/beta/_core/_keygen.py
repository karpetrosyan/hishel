from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Generator


class KeyGen(ABC):
    @abstractmethod
    def decoder(self) -> Generator[None, bytes | None, bytes]: ...


class HashKeyGen(KeyGen):
    def __init__(self, algorithm: str) -> None:
        self.algorithm = algorithm

    def decoder(self) -> Generator[None, bytes | None, bytes]:
        hasher = hashlib.new(self.algorithm)
        while True:
            chunk = yield None
            if chunk is None:
                break
            hasher.update(chunk)

        return hasher.digest()
