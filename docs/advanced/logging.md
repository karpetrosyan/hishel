---
icon: material/file-document-edit
---

[Logging](https://en.wikipedia.org/wiki/Logging_(computing)) is an important part of every application that helps developers better understand how the program operates. Hishel supports a variety of logs that can show you how the library impacts your program.

Hishel will support several loggers for different parts of the program. Currently, we support only one logger called `hishel.controller`, which logs any event related to the cache. For example, it logs when a response is considered stale, when revalidation occurs, when a response is used from the cache, and more.

## Controller logs

The [controller](./controllers.md) is a part of the Hishel library that interprets the caching specification. It determines whether a response can be cached or retrieved from the cache.

You can configure the controller logger for debugging purposes or to better understand how caching works. It can also be crucial when you're just starting out and want to understand why a particular response isn't being cached.

For example, let's enable logging and see what gets logged when making an HTTP request to the Hishel documentation.

```python
import logging
import hishel

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("hishel.controller").setLevel(logging.DEBUG)

client = hishel.CacheClient()

response = client.get(
    "https://hishel.com",
)
```

Here is what Hishel will log for this program:

```
2024-09-30 16:32:34,799 - hishel.controller - DEBUG - Considering the resource located at https://hishel.com/ as cachable since it meets the criteria for being stored in the cache.
```

If you run this program a second time, you will receive the response from the cache because hishel.com sends all the necessary caching headers. So, for the second run, you will see a log entry about the successfully reused response.

```
2024-09-30 16:35:14,102 - hishel.controller - DEBUG - Considering the resource located at https://hishel.com/ as valid for cache use since it is fresh.
```

If we wait some time, the cached response will, of course, become stale. After some time, you can run this program again and see that the response needs to be revalidated from the server to obtain the most recent data. The logs could look like this:

```
2024-09-30 16:39:42,502 - hishel.controller - DEBUG - Considering the resource located at https://hishel.com/ as needing revalidation since it is not fresh.
2024-09-30 16:39:42,502 - hishel.controller - DEBUG - Adding the 'If-Modified-Since' header with the value of 'Fri, 27 Sep 2024 07:42:28 GMT' to the request for the resource located at https://hishel.com/.
```

The controller will indicate not only that the response was cached but also why it was considered cacheable.

Examples:

- For permanent redirects
```
2024-09-30 16:43:04,672 - hishel.controller - DEBUG - Considering the resource located at https://www.github.com/ as cachable since its status code is a permanent redirect.
```

- When [force_cache](./extensions.md#force_cache) is enabled
```
2024-09-30 16:45:10,468 - hishel.controller - DEBUG - Considering the resource located at https://www.google.com/ as valid for cache use since the request is forced to use the cache.
```

Or when it's considered as not cachable

```
2024-09-30 17:02:24,961 - hishel.controller - DEBUG - Considering the resource located at https://www.python.org/ as not cachable since it does not contain any of the required cache directives.
```

[Here](https://github.com/karpetrosyan/hishel/pull/275) you can find a full list of the controller logs. Note that this is the list of initial logs; any logs added later will not be updated in this list.