import typing as tp

import anyio

__all__ = (
    "AsyncFileManager",
    "FileManager"
)

class AsyncBaseFileManager:

    def __init__(self,
                 is_binary: bool) -> None:
        self.is_binary = is_binary

    async def write_to(self, path: str, data: tp.Union[bytes, str], is_binary: tp.Optional[bool] = None) -> None:
        raise NotImplementedError()

    async def read_from(self, path: str) -> tp.Union[bytes, str]:
        raise NotImplementedError()

class AsyncFileManager(AsyncBaseFileManager):

    async def write_to(self, 
                       path: str, 
                       data: tp.Union[bytes, str], 
                       is_binary: tp.Optional[bool] = None) -> None:
        is_binary = self.is_binary if is_binary is None else is_binary
        mode = 'wb' if is_binary else 'wt'
        async with await anyio.open_file(path, mode=mode) as f:
            await f.write(data)

    async def read_from(self, path: str, is_binary: tp.Optional[bool] = None) -> tp.Union[bytes, str]:
        is_binary = self.is_binary if is_binary is None else is_binary
        mode = 'rb' if is_binary else 'rt'
        async with await anyio.open_file(path, mode=mode) as f:
            return await f.read()

class BaseFileManager:

    def __init__(self,
                 is_binary: bool) -> None:
        self.is_binary = is_binary

    def write_to(self, path: str, data: tp.Union[bytes, str], is_binary: tp.Optional[bool] = None) -> None:
        raise NotImplementedError()

    def read_from(self, path: str, is_binary: tp.Optional[bool] = None) -> tp.Union[bytes, str]:
        raise NotImplementedError()

class FileManager(AsyncBaseFileManager):

    def write_to(self, path: str, data: tp.Union[bytes, str], is_binary: tp.Optional[bool] = None) -> None:
        is_binary = self.is_binary if is_binary is None else is_binary
        mode = 'wb' if is_binary else 'wt'
        with open(path, mode=mode) as f:
            f.write(data)

    def read_from(self, path: str, is_binary: tp.Optional[bool] = None) -> tp.Union[bytes, str]:
        is_binary = self.is_binary if is_binary is None else is_binary
        mode = 'rb' if is_binary else 'rt'
        with open(path, mode=mode) as f:
            return f.read()



