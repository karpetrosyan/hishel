---
icon: material/hand-coin-outline
---

Thank you for being interested in contributing to `Hishel`. We appreciate your efforts.
You can contribute by reviewing the [pull requests](https://github.com/karpetrosyan/hishel/pulls), [opening an issue](https://github.com/karpetrosyan/hishel/issues/new), or [adding a new feature](https://github.com/karpetrosyan/hishel/compare).

Here I will describe the development process and the tricks that we use during the development.

## Setting up

First, you should fork the [Hishel](https://github.com/karpetrosyan/hishel/) so you can create your own branch and work on it.

Then you should `git clone` your fork and create a new branch for your pull request.

``` bash
git clone https://github.com/username/hishel
cd hishel
git switch -c my-feature-name
```

## Scripts

`Hishel` provides a script directory to simplify the development process. Here is what each command does.

- **scripts/install** _Set up the virtual environment and install all the necessary dependencies_
- **scripts/lint** _Runs linter, formatter, and unasync to enforce code style_
- **scripts/check** _Runs all the necessary checks, including linter, formatter, static type analyzer, and unasync checks_
- **scripts/test** _Runs `scripts/check` + `pytest` over the coverage._

Example:

``` bash
>>> ./scripts/install
>>> source ./venv/bin/activate
>>> ./scripts/test
+ ./scripts/check
+ ruff format tests hishel --diff
26 files left unchanged
+ ruff tests hishel
+ mypy tests hishel
Success: no issues found in 38 source files
+ python unasync.py --check
hishel/_async/_client.py -> hishel/_sync/_client.py
hishel/_async/_pool.py -> hishel/_sync/_pool.py
hishel/_async/_transports.py -> hishel/_sync/_transports.py
hishel/_async/_mock.py -> hishel/_sync/_mock.py
hishel/_async/_storages.py -> hishel/_sync/_storages.py
hishel/_async/__init__.py -> hishel/_sync/__init__.py
tests/_async/test_storages.py -> tests/_sync/test_storages.py
tests/_async/test_transport.py -> tests/_sync/test_transport.py
tests/_async/__init__.py -> tests/_sync/__init__.py
tests/_async/test_client.py -> tests/_sync/test_client.py
tests/_async/test_pool.py -> tests/_sync/test_pool.py
+ coverage run -m pytest tests
============================ test session starts =============================
platform linux -- Python 3.10.12, pytest-7.4.3, pluggy-1.3.0
rootdir: /home/test/programs/gitprojects/hishel
configfile: pyproject.toml
plugins: anyio-4.1.0, asyncio-0.21.1
asyncio: mode=stric`t
collected 158 items                                                          

tests/test_controller.py ..........................................    [ 26%]
tests/test_headers.py .....................                            [ 39%]
tests/test_lfu_cache.py ......                                         [ 43%]
tests/test_serializers.py .....                                        [ 46%]
tests/test_utils.py ........                                           [ 51%]
tests/_async/test_client.py ..                                         [ 53%]
tests/_async/test_pool.py ..................                           [ 64%]
tests/_async/test_storages.py ...........                              [ 71%]
tests/_async/test_transport.py ..................                      [ 82%]
tests/_sync/test_client.py .                                           [ 83%]
tests/_sync/test_pool.py .........                                     [ 89%]
tests/_sync/test_storages.py ........                                  [ 94%]
tests/_sync/test_transport.py .........                                [100%]

============================ 158 passed in 2.97s ============================= 
```

!!! note
    Some tests may fail if you don't have all the necessary services. For example, you don't have Redis to pass the integration tests, so there is a Docker compose file in the root directory to start those services.


## Async and Sync

Like `HTTP Core`, `Hishel` also uses the unasync strategy to support both async and sync code.

The idea behind `unasync` is that you are writing only async code and also using some logic that converts your async code to sync code rather than writing almost the same code twice.

In `Hishel`, there is a `unasync.py` script that converts an async directory to a sync one.

!!! warning
    You should not write any code in the `hishel/_sync` directory. It is always generated by the `unasync.py` scripts, and after running CI, all your changes to that directory would be lost.

Unasync scripts would automatically be called from `scripts/lint`, so you should just write an async code and then call `scripts/lint`.
