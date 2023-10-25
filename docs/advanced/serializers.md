---
icon: simple/yaml
---

Serializers are a component of [storages](#storages) that simply serialize and de-serialize responses.
Hishel will use JSONSerializer by default, but you can explicitly specify a serializer or even write your own.

Example of the serialized responses:

=== "JSON"

    ``` json
    {
        "response": {
            "status": 301,
            "headers": [
                [
                    "Content-Length",
                    "0"
                ],
                [
                    "Location",
                    "https://github.com/"
                ]
            ],
            "content": "",
            "extensions": {
                "http_version": "HTTP/1.1",
                "reason_phrase": "Moved Permanently"
            }
        },
        "request": {
            "method": "GET",
            "url": "https://www.github.com/",
            "headers": [
                [
                    "Host",
                    "www.github.com"
                ],
                [
                    "Accept",
                    "*/*"
                ],
                [
                    "Accept-Encoding",
                    "gzip, deflate"
                ],
                [
                    "Connection",
                    "keep-alive"
                ],
                [
                    "User-Agent",
                    "python-httpx/0.24.1"
                ]
            ],
            "extensions": {
                "timeout": {
                    "connect": 5.0,
                    "read": 5.0,
                    "write": 5.0,
                    "pool": 5.0
                }
            }
        },
        "metadata": {
            "cache_key": "71b46af84732856e5c16d503b655fcd0",
            "number_of_uses": 0,
            "created_at": "Mon, 21 Aug 2023 05:22:20 GMT"
        }
    }
    ```

=== "Yaml"

    ``` yaml
    response:
      status: 301
      headers:
      - - Content-Length
        - '0'
      - - Location
        - https://github.com/
      content: ''
      extensions:
        http_version: HTTP/1.1
        reason_phrase: Moved Permanently
    request:
      method: GET
      url: https://www.github.com/
      headers:
      - - Host
        - www.github.com
      - - Accept
        - '*/*'
      - - Accept-Encoding
        - gzip, deflate
      - - Connection
        - keep-alive
      - - User-Agent
        - python-httpx/0.24.1
      extensions:
        timeout:
          connect: 5.0
          read: 5.0
          write: 5.0
          pool: 5.0
    metadata:
      cache_key: 71b46af84732856e5c16d503b655fcd0
      number_of_uses: 0
      created_at: Mon, 21 Aug 2023 05:22:20 GMT

    ```


### Using the JSONSerializer

Example:
```python
import hishel

serializer = hishel.JSONSerializer()
storage = hishel.FileStorage(serializer=serializer)
```

Because serializers are supported by all of the built-in `hishel` [storages](#storages), you can pass serializers to any of them.

Example:
```python
import hishel

serializer = hishel.JSONSerializer()
storage = hishel.RedisStorage(serializer=serializer)
```

### Using the YAMLSerizlier

Example:
```python
import hishel

serializer = hishel.YAMLSerializer()
storage = hishel.FileStorage(serializer=serializer)
```

!!! note
    Make sure `Hishel` has the yaml extension installed if you want to use the `YAMLSerializer`.
    ``` shell
    $ pip install hishel[yaml]
    ```

### Using the PickleSerializer

Example:
```python
import hishel

serializer = hishel.PickleSerializer()
storage = hishel.FileStorage(serializer=serializer)
```


