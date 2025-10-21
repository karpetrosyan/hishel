## [1.0.0dev0] - 2025-10-19

### ⚙️ Miscellaneous Tasks

- *(docs)* Use mike powered versioning
- *(docs)* Improve docs versioning, deploy dev doc on ci
## [0.1.5] - 2025-10-18

### 🚀 Features

- *(perf)* Set chunk size to 128KB for httpx to reduce SQLite read/writes
- Better cache-control parsing
- Add close method to storages API (#384)
- *(perf)* Increase requests buffer size to 128KB, disable charset detection

### 🐛 Bug Fixes

- *(docs)* Fix some line breaks

### ⚙️ Miscellaneous Tasks

- Remove some redundant files from repo
## [0.1.4] - 2025-10-14

### 🚀 Features

- Add support for a sans-IO API (#366)
- Allow already consumed streams with `CacheTransport` (#377)
- Add sqlite storage for beta storages
- Get rid of some locks from sqlite storage
- Better async implemetation for sqlite storage

### 🐛 Bug Fixes

- Create an sqlite file in a cache folder
- Fix beta imports

### ⚙️ Miscellaneous Tasks

- Improve CI (#369)
- *(internal)* Remove src folder (#373)
- *(internal)* Temporary remove python3.14 from CI
- *(tests)* Add sqlite tests for new storage
- *(tests)* Move some tests to beta
## [0.1.3] - 2025-07-01

### 🚀 Features

- Add `path_prefix` support in `S3Storage` and `AsyncS3Storage` (#342)

### 🐛 Bug Fixes

- Avoid race condition when unlinking files in `FileStorage` (#334)

### ⚙️ Miscellaneous Tasks

- Remove `types-redis` from dev dependencies (#336)
- Bump redis to 6.0.0 and address async `.close()` deprecation warning (#336)

## [0.1.2] - 2025-04-05

### 🚀 Features

- Use `SyncByteStream` instead of `ByteStream` (#298)

### 🐛 Bug Fixes

- Add check for fips compliant python (#325)
- Fix compatibility with httpx (#291)
- Don't raise exceptions if date-containing headers are invalid (#318)
- Fix for S3 Storage missing metadata in API request (#320)

## [0.1.1] - 2024-11-02

### 🐛 Bug Fixes

- Fix typing extensions not found (#290)

## [0.1.0] - 2024-11-02

### 🚀 Features

- Add support for Python 3.12 (#286)

### ⚙️ Miscellaneous Tasks

- Drop Python 3.8 (#286)
- Specify usedforsecurity=False in blake2b (#285)

## [0.0.33] - 2024-10-04

### 📚 Documentation

- Add Logging section to the documentation

## [0.0.32] - 2024-09-27

### 🐛 Bug Fixes

- Don't raise an exception if the `Date` header is not present (#273)

## [0.0.31] - 2024-09-22

### 🐛 Bug Fixes

- Ignore file not found error when cleaning up a file storage (#264)
- Fix `AssertionError` on `client.close()` when use SQLiteStorage (#269)
- Fix ignored flags when use `force_cache` (#271)

## [0.0.30] - 2024-07-12

### 🚀 Features

- Add `cache_private` property to the controller to support acting as shared cache (#224)
- Add `remove` support for storages (#241)

### 🐛 Bug Fixes

- Fix cache update on revalidation response with content (rfc9111 section 4.3.3) (#239)
- Fix request extensions that were not passed into revalidation request for transport-based implementation (#247)

### ⚙️ Miscellaneous Tasks

- Improve efficiency of scanning cached responses in `FileStorage` by reducing number of syscalls (#252)

## [0.0.29] - 2024-06-23

### 📚 Documentation

- Documentation hotfix (#244)

## [0.0.28] - 2024-06-23

### 🚀 Features

- Add `revalidated` response extension (#242)

## [0.0.27] - 2024-05-31

### 🐛 Bug Fixes

- Fix `RedisStorage` when using without ttl (#231)

## [0.0.26] - 2024-04-12

### 🚀 Features

- Prevent cache hits from resetting the ttl (#215)

### ⚙️ Miscellaneous Tasks

- Expose `AsyncBaseStorage` and `BaseStorage` (#220)

## [0.0.25] - 2024-03-26

### 🚀 Features

- Add `force_cache` property to the controller, allowing RFC9111 rules to be completely disabled (#204)
- Add `.gitignore` to cache directory created by `FileStorage` (#197)

### ⚙️ Miscellaneous Tasks

- Remove `stale_*` headers from the `CacheControl` class (#199)

## [0.0.24] - 2024-02-14

### 🐛 Bug Fixes

- Fix `botocore is not installed` exception when using any kind of storage (#186)

## [0.0.23] - 2024-02-14

### 🚀 Features

- Make `S3Storage` to check staleness of all cache files with set interval (#182)
- Support caching for `POST` and other HTTP methods (#183)

### 🐛 Bug Fixes

- Fix an issue where an empty file in `FileCache` could cause a parsing error (#181)

## [0.0.22] - 2024-01-31

### 🚀 Features

- Make `FileStorage` to check staleness of all cache files with set interval (#169)
- Support AWS S3 storages (#164)

### ⚙️ Miscellaneous Tasks

- Move `typing_extensions` from requirements.txt to pyproject.toml (#161)

## [0.0.21] - 2023-12-29

### 🐛 Bug Fixes

- Fix inner transport and connection pool instances closing (#147)

### ⚙️ Miscellaneous Tasks

- Improve error message when the storage type is incorrect (#138)

## [0.0.20] - 2023-12-12

### 🚀 Features

- Add in-memory storage (#133)
- Allow customization of cache key generation (#130)

## [0.0.19] - 2023-11-30

### 🚀 Features

- Add `force_cache` extension to enforce the request to be cached, ignoring the HTTP headers (#117)
- Support float numbers for storage ttl (#107)

### 🐛 Bug Fixes

- Fix issue where sqlite storage cache get deleted immediately (#119)

## [0.0.18] - 2023-11-23

### 🚀 Features

- Add `cache_disabled` extension to temporarily disable the cache (#109)

### 🐛 Bug Fixes

- Fix issue where freshness cannot be calculated to re-send request (#104)

### ⚙️ Miscellaneous Tasks

- Update `datetime.datetime.utcnow()` to `datetime.datetime.now(datetime.timezone.utc)` since `datetime.datetime.utcnow()` has been deprecated (#111)

## [0.0.17] - 2023-11-06

### 🐛 Bug Fixes

- Fix `Last-Modified` validation

## [0.0.16] - 2023-10-25

### 🚀 Features

- Add `install_cache` function (#95)
- Add sqlite support (#92)

### ⚙️ Miscellaneous Tasks

- Move `ttl` argument to `BaseStorage` class (#94)

## [0.0.14] - 2023-10-23

### 🚀 Features

- Add `must-understand` response directive support (#90)

### ⚙️ Miscellaneous Tasks

- Replace `AsyncResponseStream` with `AsyncCacheStream` (#86)

## [0.0.13] - 2023-10-05

### 🚀 Features

- Add support for Python 3.12 (#71)

### 🐛 Bug Fixes

- Fix connections releasing from the connection pool (#83)

## [0.0.12] - 2023-09-08

### 🚀 Features

- Add metadata into the response extensions (#56)

## [0.0.11] - 2023-08-15

### 🚀 Features

- Add support for request `cache-control` directives (#42)

### ⚙️ Miscellaneous Tasks

- Drop httpcore dependency (#40)
- Support HTTP methods only if they are defined as cacheable (#37)

## [0.0.10] - 2023-08-07

### 🚀 Features

- Add Response metadata (#33)
- Use stale responses only if the client is disconnected (#28)

### 📚 Documentation

- Add API Reference documentation (#30)

## [0.0.9] - 2023-08-01

### 🚀 Features

- Expose Controller API (#23)

## [0.0.8] - 2023-07-31

### ⚙️ Miscellaneous Tasks

- Skip redis tests if the server was not found (#16)
- Decrease sleep time for the storage ttl tests (#18)
- Fail coverage under 100 (#19)

## [0.0.7] - 2023-07-30

### 🚀 Features

- Add support for `Heuristic Freshness` (#11)

### ⚙️ Miscellaneous Tasks

- Change `Controller.cache_heuristically` to `Controller.allow_heuristics` (#12)
- Handle import errors (#13)

## [0.0.6] - 2023-07-29

### 🐛 Bug Fixes

- Fix `Vary` header validation (#8)

### ⚙️ Miscellaneous Tasks

- Dump original requests with the responses (#7)

## [0.0.5] - 2023-07-29

### 🐛 Bug Fixes

- Fix httpx response streaming

## [0.0.4] - 2023-07-29

### ⚙️ Miscellaneous Tasks

- Change `YamlSerializer` name to `YAMLSerializer`

## [0.0.3] - 2023-07-28

### 🚀 Features

- Add `from_cache` response extension

### ⚙️ Miscellaneous Tasks

- Add `typing_extensions` into the requirements

## [0.0.2] - 2023-07-25

### 🚀 Features

- Add redis support
- Make backends thread and task safe

### ⚙️ Miscellaneous Tasks

- Add black as a new linter
- Add an expire time for cached responses