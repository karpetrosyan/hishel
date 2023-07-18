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


class PickleSerializer(BaseSerializer):

    def dumps(self, response: Response) -> tp.Union[str, bytes]:
        response.read()
        clone_response = Response(
            status=response.status,
            headers=response.headers,
            content=response.content,
            extensions={key: value for key, value in response.extensions.items() if key != 'network_stream'}
        )
        return pickle.dumps(clone_response)

    def loads(self, data: tp.Union[str, bytes]) -> Response:
        assert isinstance(data, bytes)
        return tp.cast(Response, pickle.loads(data))

    @property
    def is_binary(self) -> bool:
        return True
