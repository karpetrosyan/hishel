import typing as tp

import anyio


class AsyncBaseFileManager:

    def __init__(self,
                 is_binary: bool) -> None:
        self.is_binary = is_binary

    async def write_to(self, path: str, data: tp.Union[bytes, str]) -> None:
        raise NotImplementedError()

    async def read_from(self, path: str) -> tp.Union[bytes, str]:
        raise NotImplementedError()

class AsyncFileManager(AsyncBaseFileManager):

    async def write_to(self, path: str, data: tp.Union[bytes, str]) -> None:
        mode = 'wb' if self.is_binary else 'wt'
        async with await anyio.open_file(path, mode=mode) as f:
            await f.write(data)

    async def read_from(self, path: str) -> tp.Union[bytes, str]:
        mode = 'rb' if self.is_binary else 'rt'
        async with await anyio.open_file(path, mode=mode) as f:
            await f.read()



