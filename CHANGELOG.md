# Changelog

All notable changes to this project will be documented in this file.

## 1.1.0 - 2025-10-31
### ⚙️ Miscellaneous Tasks
- Add in memory example

### 🐛 Bug Fixes
- Pass any response with non-expected status code on revalidation to client

### 🚀 Features
- Allow setting storage base with via `database_path` for sqlite storage

## 1.0.0 - 2025-10-28
### ⚙️ Miscellaneous Tasks
- Add examples, improve docs

## 1.0.0b1 - 2025-10-28
### ♻️ Refactoring
- Add policies

### ⚙️ Miscellaneous Tasks
- Improve sans-io diagram colors
- Add graphql docs

### 🐛 Bug Fixes
- Body-sensitive responses caching
- Filter out `Transfer-Encoding` header for asgi responses

### 🚀 Features
- Add global `use_body_key` setting

## 1.0.0.dev3 - 2025-10-26
### ♻️ Refactoring
- Replace pairs with entries, simplify storage API
- Automatically generate httpx sync integration from async

### ⚙️ Miscellaneous Tasks
- Simplify metadata docs
- Add custom integrations docs
- More robust compressed response caching

### 🐛 Bug Fixes
- Add missing permissions into `publish.yml`
- Raise on consumed httpx streams, which we can't store as is (it's already decoded)
- Fix compressed data caching for requests
- Handle httpx iterable usage instead of iterator correctly
- Add date header for proper age calculation

### 🚀 Features
- Add integrations with fastapi and asgi
- Add blacksheep integration examples
- Add logging for asgi

## 1.0.0.dev2 - 2025-10-21
### ⚙️ Miscellaneous Tasks
- Remove redundant utils and tests
- Add import without extras check in ci
- Fix time travel date, explicitly specify the timezone

### 🐛 Bug Fixes
- Fix check for storing auth requests
- Don't raise an error on 3xx during revalidation

### 🚀 Features
- Add hishel_created_at response metadata

## 1.0.0.dev1 - 2025-10-21
### ⚙️ Miscellaneous Tasks
- Remove some redundant utils methods

### 📦 Dependencies
- Make httpx and async libs optional dependencies
- Make `anysqlite` optional dependency
- Install async extra with httpx
- Improve git-cliff

## 1.0.0.dev0 - 2025-10-19
### ⚙️ Miscellaneous Tasks
- Use mike powered versioning
- Improve docs versioning, deploy dev doc on ci

## 0.1.5 - 2025-10-18
### ⚙️ Miscellaneous Tasks
- Remove some redundant files from repo

### 🐛 Bug Fixes
- Fix some line breaks

### 🚀 Features
- Set chunk size to 128KB for httpx to reduce SQLite read/writes
- Better cache-control parsing
- Add close method to storages API (#384)
- Increase requests buffer size to 128KB, disable charset detection

## 0.1.4 - 2025-10-14
### ⚙️ Miscellaneous Tasks
- Improve CI (#369)
- Remove src folder (#373)
- Temporary remove python3.14 from CI
- Add sqlite tests for new storage
- Move some tests to beta

### 🐛 Bug Fixes
- Create an sqlite file in a cache folder
- Fix beta imports

### 🚀 Features
- Add support for a sans-IO API (#366)
- Allow already consumed streams with `CacheTransport` (#377)
- Add sqlite storage for beta storages
- Get rid of some locks from sqlite storage
- Better async implemetation for sqlite storage

