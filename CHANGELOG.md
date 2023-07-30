# Changelog

## 0.0.7 (7/30/2023)

- Add support for `Heuristic Freshness`. (#11)
- Change `Controller.cache_heuristically` to `Controller.allow_heuristics`. (#12)
- Handle import errors. (#13)

## 0.0.6 (7/29/2023)

- Fix `Vary` header validation. (#8)
- Dump original requests with the responses. (#7) 

## 0.0.5 (7/29/2023)

- Fix httpx response streaming.

## 0.0.4 (7/29/2023)

- Change `YamlSerializer` name to `YAMLSerializer`.

## 0.0.3 (7/28/2023)

- Add `from_cache` response extension.
- Add `typing_extensions` into the requirements.

## 0.0.2 (7/25/2023)

- Add [redis](https://redis.io/) support.
- Make backends thread and task safe.
- Add black as a new linter.
- Add an expire time for cached responses.
