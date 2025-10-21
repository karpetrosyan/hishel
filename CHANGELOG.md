# Changelog

All notable changes to this project will be documented in this file.

## 1.0.0dev1 - 2025-10-21
### <!-- 7 -->⚙️ Miscellaneous Tasks
- Remove some redundant utils methods

## 1.0.0.dev0 - 2025-10-19
### <!-- 7 -->⚙️ Miscellaneous Tasks
- Use mike powered versioning
- Improve docs versioning, deploy dev doc on ci

## 0.1.5 - 2025-10-18
### <!-- 0 -->🚀 Features
- Set chunk size to 128KB for httpx to reduce SQLite read/writes
- Better cache-control parsing
- Add close method to storages API (#384)
- Increase requests buffer size to 128KB, disable charset detection

### <!-- 1 -->🐛 Bug Fixes
- Fix some line breaks

### <!-- 7 -->⚙️ Miscellaneous Tasks
- Remove some redundant files from repo

## 0.1.4 - 2025-10-14
### <!-- 0 -->🚀 Features
- Add support for a sans-IO API (#366)
- Allow already consumed streams with `CacheTransport` (#377)
- Add sqlite storage for beta storages
- Get rid of some locks from sqlite storage
- Better async implemetation for sqlite storage

### <!-- 1 -->🐛 Bug Fixes
- Create an sqlite file in a cache folder
- Fix beta imports

### <!-- 7 -->⚙️ Miscellaneous Tasks
- Improve CI (#369)
- Remove src folder (#373)
- Temporary remove python3.14 from CI
- Add sqlite tests for new storage
- Move some tests to beta

