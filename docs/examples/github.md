---
icon: simple/github
---


On this page, we'll look at why HTTP caching is important when using [GitHub APIs](https://docs.github.com/en/rest?apiVersion=2022-11-28).

Let's create a simple program that takes the name of the github repository and displays the stars in real time.

To use **GitHub APIs**, we first need an access token. [See how to create a github token here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-personal-access-token-classic).

However, if we write a program that makes a large number of HTTP requests to the **GItHub servers**, we will be blocked for a period of time because github has [rate limits](https://docs.github.com/en/rest/overview/rate-limits-for-the-rest-api?apiVersion=2022-11-28) in place to prevent overloading their servers.

In such cases, APIs frequently provide HTTP caching functionality, which we can use to retrieve the response from the local cache or make a new request if the data on the server has changed.

To ensure that cached responses are not counted, we should also display the rate limit.

```python
import os
from time import sleep

import hishel

TOKEN = os.getenv("TOKEN")

client = hishel.CacheClient(
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Accept": "application/vnd.github+json",
    },
)

repo = input("Enter repo name: ")  # example: "karpetrosyan/hishel"
organization, repo = repo.split("/")


while True:
    stars_response = client.get(f"https://api.github.com/repos/{organization}/{repo}")
    stars = stars_response.json()["stargazers_count"]

    rate_response = client.get("https://api.github.com/rate_limit")
    remaining = rate_response.json()["rate"]["remaining"]

    print(f"\rStars: {stars} Remaining rate limit: {remaining}", end="")
    sleep(1)
```

Change `hishel.CacheClient` to `httpx.Client` to see how quickly you are **wasting your rate limits**!

When `HTTPX` makes a **real request** in each iteration, `Hishel` consumes the rate limit only once and stores the response in the **local cache**.

Also, keep in mind that when the stars count is updated, it will not be displayed immediately when using `Hishel` because it uses the cached response; instead, it will wait until the local response is considered stale before re-validating that response.

Because `GitHub` sends a header indicating that this response has a maximum lifespan of 60 seconds, you will see the updated stars count after 60 seconds.

Here is what that header looks like:
```
Cache-Control: private, max-age=60, s-maxage=60
```

Anyway, if you want to see the update **without any delay**, you can explicitly tell the `Hishel` that you want to always re-validate the response before using it, which is also free and doesn't have a rate limit!

Example:

```python
client = hishel.CacheClient(
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Accept": "application/vnd.github+json",
    },
    controller=hishel.Controller(always_revalidate=True)
)
```

