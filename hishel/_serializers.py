import base64
import json
import pickle
import typing as tp

import yaml
from httpcore import Response

HEADERS_ENCODING = 'iso-8859-1'
KNOWN_RESPONSE_EXTENSIONS = ('http_version', 'reason_phrase')

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
        clone_response = Response(
            status=response.status,
            headers=response.headers,
            content=response.content,
            extensions={key: value for key, value in response.extensions.items() if key in KNOWN_RESPONSE_EXTENSIONS}
        )
        return pickle.dumps(clone_response)

    def loads(self, data: tp.Union[str, bytes]) -> Response:
        assert isinstance(data, bytes)
        return tp.cast(Response, pickle.loads(data))

    @property
    def is_binary(self) -> bool:  # pragma: no cover
        return True

class DictSerializer(BaseSerializer):

    def dumps(self, response: Response) -> tp.Union[str, bytes]:
        response_dict = {
            "status": response.status,
            "headers": [
                (
                    key.decode(HEADERS_ENCODING),
                    value.decode(HEADERS_ENCODING)
                ) for key, value in response.headers],
            "content": base64.b64encode(response.content).decode('ascii'),
            "extensions": {
                key: value.decode('ascii') for key, value in response.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS}
        }

        return json.dumps(response_dict, indent=4)

    def loads(self, data: tp.Union[str, bytes]) -> Response:
        response_dict = json.loads(data)

        return Response(
            status=response_dict["status"],
            headers=[
                (
                    key.encode(HEADERS_ENCODING),
                    value.encode(HEADERS_ENCODING)
                ) for key, value in response_dict["headers"]],
            content=base64.b64decode(response_dict["content"].encode('ascii')),
            extensions={
                key: value.encode('ascii') for key, value in response_dict["extensions"].items()
                if key in KNOWN_RESPONSE_EXTENSIONS}
        )

    @property
    def is_binary(self) -> bool:
        return False

class YamlSerializer(BaseSerializer):


    def dumps(self, response: Response) -> tp.Union[str, bytes]:
        response_dict = {
            "status": response.status,
            "headers": [
                (
                    key.decode(HEADERS_ENCODING),
                    value.decode(HEADERS_ENCODING)
                ) for key, value in response.headers],
            "content": base64.b64encode(response.content).decode('ascii'),
            "extensions": {
                key: value.decode('ascii') for key, value in response.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS}
        }
        return yaml.safe_dump(response_dict, sort_keys=False)

    def loads(self, data: tp.Union[str, bytes]) -> Response:
        response_dict = yaml.safe_load(data)

        return Response(
            status=response_dict["status"],
            headers=[
                (
                    key.encode(HEADERS_ENCODING),
                    value.encode(HEADERS_ENCODING)
                ) for key, value in response_dict["headers"]],
            content=base64.b64decode(response_dict["content"].encode('ascii')),
            extensions={
                key: value.encode('ascii') for key, value in response_dict["extensions"].items()
                if key in KNOWN_RESPONSE_EXTENSIONS}
        )

    @property
    def is_binary(self) -> bool:  # pragma: no cover
        return False
