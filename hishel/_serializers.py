import base64
import json
import pickle
import typing as tp

import yaml
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

class DictSerializer(BaseSerializer):

    def dumps(self, response: Response) -> tp.Union[str, bytes]:
        response_dict = {
            "status": response.status,
            "headers": [
                (key.decode(), value.decode()) for key, value in response.headers],
            "content": base64.b64encode(response.content).decode('ascii'),
            "extensions": {key: value for key, value in response.extensions.items() if key.lower() != "network_stream"}
        }

        return json.dumps(response_dict, indent=4)

    def loads(self, data: tp.Union[str, bytes]) -> Response:
        response_dict = json.loads(data)

        return Response(
            status=response_dict["status"],
            headers=[
                (
                    key.encode('ascii'),
                    value.encode('ascii')
                ) for key, value in response_dict["headers"]],
            content=base64.b64decode(response_dict["content"].encode())
        )

    @property
    def is_binary(self) -> bool:
        return False

class YamlSerializer(BaseSerializer):


    def dumps(self, response: Response) -> str | bytes:
        response_dict = {
            "status": response.status,
            "headers": [
                (key.decode(), value.decode()) for key, value in response.headers],
            "content": base64.b64encode(response.content).decode('ascii'),
            "extensions": {key: value for key, value in response.extensions.items() if key.lower() != "network_stream"}
        }
        return yaml.safe_dump(response_dict)

    def loads(self, data: str | bytes) -> Response:
        response_dict = yaml.safe_load(data)

        return Response(
            status=response_dict["status"],
            headers=[
                (
                    key.encode('ascii'),
                    value.encode('ascii')
                ) for key, value in response_dict["headers"]],
            content=base64.b64decode(response_dict["content"].encode())
        )

    @property
    def is_binary(self) -> bool:
        return False
