import base64
import json
import pickle
import typing as tp

import yaml
from httpcore import Response, Request
from hishel._utils import normalized_url

HEADERS_ENCODING = "iso-8859-1"
KNOWN_RESPONSE_EXTENSIONS = ("http_version", "reason_phrase")
KNOWN_REQUEST_EXTENSIONS = ("timeout", "sni_hostname")

__all__ = ("PickleSerializer", "JSONSerializer", "YAMLSerializer", "BaseSerializer")


class BaseSerializer:
    def dumps(self, response: Response, request: Request) -> tp.Union[str, bytes]:
        raise NotImplementedError()

    def loads(self, data: tp.Union[str, bytes]) -> tp.Tuple[Response, Request]:
        raise NotImplementedError()

    @property
    def is_binary(self) -> bool:
        raise NotImplementedError()


class PickleSerializer(BaseSerializer):
    def dumps(self, response: Response, request: Request) -> tp.Union[str, bytes]:
        clone_response = Response(
            status=response.status,
            headers=response.headers,
            content=response.content,
            extensions={
                key: value
                for key, value in response.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        )
        return pickle.dumps(clone_response)

    def loads(self, data: tp.Union[str, bytes]) -> tp.Tuple[Response, Request]:
        assert isinstance(data, bytes)
        return tp.cast(Response, pickle.loads(data))

    @property
    def is_binary(self) -> bool:  # pragma: no cover
        return True


class JSONSerializer(BaseSerializer):
    def dumps(self, response: Response, request: Request) -> tp.Union[str, bytes]:
        response_dict = {
            "status": response.status,
            "headers": [
                (key.decode(HEADERS_ENCODING), value.decode(HEADERS_ENCODING))
                for key, value in response.headers
            ],
            "content": base64.b64encode(response.content).decode("ascii"),
            "extensions": {
                key: value.decode("ascii")
                for key, value in response.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        }

        request_dict = {
            "method": request.method.decode('ascii'),
            "url": normalized_url(request.url),
            "headers": [
                (key.decode(HEADERS_ENCODING), value.decode(HEADERS_ENCODING))
                for key, value in request.headers
            ],
            "extensions": {
                key: value
                for key, value in request.extensions.items()
                if key in KNOWN_REQUEST_EXTENSIONS
            },
        }

        full_json = {
            "response": response_dict,
            "request": request_dict
        }

        return json.dumps(full_json, indent=4)

    def loads(self, data: tp.Union[str, bytes]) -> tp.Tuple[Response, Request]:
        full_json = json.loads(data)

        response_dict = full_json['response']
        request_dict = full_json['request']

        response = Response(
            status=response_dict["status"],
            headers=[
                (key.encode(HEADERS_ENCODING), value.encode(HEADERS_ENCODING))
                for key, value in response_dict["headers"]
            ],
            content=base64.b64decode(response_dict["content"].encode("ascii")),
            extensions={
                key: value.encode("ascii")
                for key, value in response_dict["extensions"].items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        )

        request = Request(
            method=request_dict["method"],
            url=request_dict["url"],
            headers=[
                (key.encode(HEADERS_ENCODING), value.encode(HEADERS_ENCODING))
                for key, value in request_dict["headers"]
            ],
            extensions={
                key: value
                for key, value in request_dict["extensions"].items()
                if key in KNOWN_REQUEST_EXTENSIONS
            },
        )

        return response, request

    @property
    def is_binary(self) -> bool:
        return False


class YAMLSerializer(BaseSerializer):
    def dumps(self, response: Response, request: Request) -> tp.Union[str, bytes]:
        response_dict = {
            "status": response.status,
            "headers": [
                (key.decode(HEADERS_ENCODING), value.decode(HEADERS_ENCODING))
                for key, value in response.headers
            ],
            "content": base64.b64encode(response.content).decode("ascii"),
            "extensions": {
                key: value.decode("ascii")
                for key, value in response.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        }
        return yaml.safe_dump(response_dict, sort_keys=False)

    def loads(self, data: tp.Union[str, bytes]) -> tp.Tuple[Response, Request]:
        response_dict = yaml.safe_load(data)

        response = Response(
            status=response_dict["status"],
            headers=[
                (key.encode(HEADERS_ENCODING), value.encode(HEADERS_ENCODING))
                for key, value in response_dict["headers"]
            ],
            content=base64.b64decode(response_dict["content"].encode("ascii")),
            extensions={
                key: value.encode("ascii")
                for key, value in response_dict["extensions"].items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        )

    @property
    def is_binary(self) -> bool:  # pragma: no cover
        return False
