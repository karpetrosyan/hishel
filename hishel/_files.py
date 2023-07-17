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

    async def read_from(self, path: str, is_binary: tp.Optional[bool] = None) -> tp.Union[bytes, str]:
        raise NotImplementedError()

class AsyncFileManager(AsyncBaseFileManager):

    async def write_to(self,
                       path: str,
                       data: tp.Union[bytes, str],
                       is_binary: tp.Optional[bool] = None) -> None:
        is_binary = self.is_binary if is_binary is None else is_binary
        if is_binary:
            assert isinstance(data, bytes)
            await anyio.Path(path).write_bytes(data)
        else:
            assert isinstance(data, str)
            await anyio.Path(path).write_text(data)

    async def read_from(self, path: str, is_binary: tp.Optional[bool] = None) -> tp.Union[bytes, str]:
        is_binary = self.is_binary if is_binary is None else is_binary

        if is_binary:
            return await anyio.Path(path).read_bytes()
        else:
            return await anyio.Path(path).read_text()
        assert False

class BaseFileManager:

    def __init__(self,
                 is_binary: bool) -> None:
        self.is_binary = is_binary

    def write_to(self, path: str, data: tp.Union[bytes, str], is_binary: tp.Optional[bool] = None) -> None:
        raise NotImplementedError()

    def read_from(self, path: str, is_binary: tp.Optional[bool] = None) -> tp.Union[bytes, str]:
        raise NotImplementedError()

class FileManager(BaseFileManager):

    def write_to(self, path: str, data: tp.Union[bytes, str], is_binary: tp.Optional[bool] = None) -> None:
        is_binary = self.is_binary if is_binary is None else is_binary
        mode = 'wb' if is_binary else 'wt'
        with open(path, mode) as f:
            f.write(data)

    def read_from(self, path: str, is_binary: tp.Optional[bool] = None) -> tp.Union[bytes, str]:
        is_binary = self.is_binary if is_binary is None else is_binary
        mode = 'rb' if is_binary else 'rt'
        with open(path, mode) as f:
            return tp.cast(tp.Union[bytes, str], f.read())




