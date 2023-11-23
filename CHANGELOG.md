# Changelog

## 0.0.18 (23/11/2023)

- Fix issue where freshness cannot be calculated to re-send request. (#104)
- Add `cache_disabled` extension to temporarily disable the cache (#109)
- Update `datetime.datetime.utcnow()` to `datetime.datetime.now(datetime.timezone.utc)` since `datetime.datetime.utcnow()` has been deprecated. (#111)

## 0.0.17 (6/11/2023) 

- Fix `Last-Modified` validation.

## 0.0.16 (25/10/2023) 

- Add `install_cache` function. (#95)
- Add sqlite support. (#92)
- Move `ttl` argument to `BaseStorage` class. (#94)

## 0.0.14 (23/10/2023)

- Replace `AsyncResponseStream` with `AsyncCacheStream`. (#86)
- Add `must-understand` response directive support. (#90)

## 0.0.13 (5/10/2023)

- Add support for Python 3.12. (#71)
- Fix connections releasing from the connection pool. (#83)

## 0.0.12 (8/9/2023)

- Add metadata into the response extensions. (#56)

## 0.0.11 (15/8/2023) 

- Add support for request `cache-control` directives. (#42)
- Drop httpcore dependency. (#40)
- Support HTTP methods only if they are defined as cacheable. (#37)

## 0.0.10 (7/8/2023) 

- Add Response metadata. (#33)
- Add API Reference documentation. (#30)
- Use stale responses only if the client is disconnected. (#28)

## 0.0.9 (1/8/2023) 

- Expose Controller API. (#23)

## 0.0.8 (31/7/2023)

- Skip redis tests if the server was not found. (#16)
- Decrease sleep time for the storage ttl tests. (#18)
- Fail coverage under 100. (#19)

## 0.0.7 (30/7/2023)

- Add support for `Heuristic Freshness`. (#11)
- Change `Controller.cache_heuristically` to `Controller.allow_heuristics`. (#12)
- Handle import errors. (#13)

## 0.0.6 (29/7/2023)

- Fix `Vary` header validation. (#8)
- Dump original requests with the responses. (#7) 

## 0.0.5 (29/7/2023)

- Fix httpx response streaming.

## 0.0.4 (29/7/2023)

- Change `YamlSerializer` name to `YAMLSerializer`.

## 0.0.3 (28/7/2023)

- Add `from_cache` response extension.
- Add `typing_extensions` into the requirements.

## 0.0.2 (25/7/2023)

- Add [redis](https://redis.io/) support.
- Make backends thread and task safe.
- Add black as a new linter.
- Add an expire time for cached responses.
