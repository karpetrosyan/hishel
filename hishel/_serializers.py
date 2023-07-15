import pickle
import typing as tp

from httpcore import Response


class BaseSerializer:

    def dumps(self, response: Response) -> tp.Union[str, bytes]:
        raise NotImplementedError()

    def loads(self, data: tp.Union[str, bytes]) -> Response:
        raise NotImplementedError()

    @property
    def is_binary(self) -> bool:
        raise NotImplementedError()


class PickleSerializer:

    def dumps(self, response: Response) -> tp.Union[str, bytes]:
        return pickle.dumps(response)

    def loads(self, data: tp.Union[str, bytes]) -> Response:
        assert isinstance(data, bytes)
        return pickle.loads(data)

    @property
    def is_binary(self) -> bool:
        return True
