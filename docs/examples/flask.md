As a `Flask` user, you can use the power of `HTTPX` using its synchronous interface.

Here is a simple example:

``` python
from flask import Flask
from httpx import Client
from httpx import Limits

app = Flask(__name__)
client = Client(limits=Limits(max_connections=1000))

@app.route("/")
def main():
    response = client.get('https://www.encode.io')
    return str(response.status_code)
```

Now let's do some load testing using the popular load testing tool [Locust](https://locust.io/).

[Here are](https://raw.githubusercontent.com/karosis88/hishel/master/docs/static/flask_without_cache.png) the test results:

<a href="https://raw.githubusercontent.com/karosis88/hishel/master/docs/static/flask_without_cache.png">
    <img src="https://raw.githubusercontent.com/karosis88/hishel/master/docs/static/flask_without_cache.png" alt="pypi">
</a>

We got only **±20 RPS**, which is not very good.

Now let's change the `httpx.Client` to `hishel.CacheClient` and do the same tests again.

``` python hl_lines="2 6"
from flask import Flask
from hishel import CacheClient
from httpx import Limits

app = Flask(__name__)
client = CacheClient(limits=Limits(max_connections=1000))

@app.route("/")
def main():
    response = client.get('https://www.encode.io')
    return str(response.status_code)
```

[Here are](https://raw.githubusercontent.com/karosis88/hishel/master/docs/static/flask_with_cache.png) the test results:

<a href="https://raw.githubusercontent.com/karosis88/hishel/master/docs/static/flask_with_cache.png">
    <img src="https://raw.githubusercontent.com/karosis88/hishel/master/docs/static/flask_with_cache.png" alt="pypi">
</a>

Now we have more than **±800 RPS** using the power of HTTP caching.