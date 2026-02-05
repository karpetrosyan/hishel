## What's Changed in 1.1.9
### ⚙️ Miscellaneous Tasks

* chore: drop python 3.9 support by @CharString in [#418](https://github.com/karpetrosyan/hishel/pull/418)
### 📦 Dependencies

* chore(deps-dev): bump the python-packages group across 1 directory with 5 updates by @dependabot[bot] in [#440](https://github.com/karpetrosyan/hishel/pull/440)

### Contributors
* @CharString
* @dependabot[bot]

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.8...1.1.9

## What's Changed in 1.1.8
### ⚙️ Miscellaneous Tasks

* chore(ci): remove redis action by @karpetrosyan in [#428](https://github.com/karpetrosyan/hishel/pull/428)
### 🐛 Bug Fixes

* fix: prevent race conditions by @karpetrosyan in [#436](https://github.com/karpetrosyan/hishel/pull/436)

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.7...1.1.8

## What's Changed in 1.1.7
### ♻️ Refactoring

* refactor(storage): create sqlite database path only when creating connections by @jeefberkey in [#426](https://github.com/karpetrosyan/hishel/pull/426)
### ⚙️ Miscellaneous Tasks

* chore(deps-dev): bump the python-packages group with 5 updates by @dependabot[bot] in [#424](https://github.com/karpetrosyan/hishel/pull/424)
### 🐛 Bug Fixes

* fix(cache): Lambda parameter name clashes the loop variable being closed over by @dump247 in [#427](https://github.com/karpetrosyan/hishel/pull/427)
### 📚 Documentation

* add release process guidelines for maintainers by @karpetrosyan
### 🚀 Features

* Feature/accept pathlib path in SqliteStorage by @daudef in [#419](https://github.com/karpetrosyan/hishel/pull/419)

### Contributors
* @karpetrosyan
* @daudef
* @dependabot[bot]
* @jeefberkey
* @dump247

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.6...1.1.7

## What's Changed in 1.1.6
### 📚 Documentation

* remove some stale httpx configs by @karpetrosyan
### 🚀 Features

* Add support for request no-cache directive by @karpetrosyan in [#416](https://github.com/karpetrosyan/hishel/pull/416)

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.5...1.1.6

## What's Changed in 1.1.5
### 🐛 Bug Fixes

* filter out soft-deleted, expired and incomplete entries in `get_entries` by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.4...1.1.5

## What's Changed in 1.1.4
### 🐛 Bug Fixes

* don't raise an error on consumed streams that were read into memory by @karpetrosyan
* close sqlite connections properly by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.3...1.1.4

## What's Changed in 1.1.3
### ⚙️ Miscellaneous Tasks

* improve git-cliff docs by @karpetrosyan
### 🐛 Bug Fixes

* fix: add BaseFilter to __all__ exports by @martinblech in [#408](https://github.com/karpetrosyan/hishel/pull/408)
* fix: set `after_revalidation=True` for `NeedsToBeUpdated` -> `FromCache` transition by @jlopex in [#402](https://github.com/karpetrosyan/hishel/pull/402)

### Contributors
* @karpetrosyan
* @martinblech
* @jlopex

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.2...1.1.3

## What's Changed in 1.1.2
### 🐛 Bug Fixes

* respect shared option when excluding unstorable headers by @karpetrosyan
* remove s-maxage consideration for private caches by @karpetrosyan
* ensure 304 responses don't leak by @karpetrosyan

### Contributors
* @karpetrosyan
* @jlopex

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.1...1.1.2

## What's Changed in 1.1.1
### ⚙️ Miscellaneous Tasks

* chore(deps-dev): bump the python-packages group with 10 updates by @dependabot[bot] in [#396](https://github.com/karpetrosyan/hishel/pull/396)
### 📦 Dependencies

* chore(deps): bump astral-sh/setup-uv from 5 to 7 by @dependabot[bot] in [#393](https://github.com/karpetrosyan/hishel/pull/393)
* chore(deps): bump actions/download-artifact from 4 to 6 by @dependabot[bot] in [#394](https://github.com/karpetrosyan/hishel/pull/394)
* chore(deps): bump actions/upload-artifact from 4 to 5 by @dependabot[bot] in [#395](https://github.com/karpetrosyan/hishel/pull/395)

### Contributors
* @karpetrosyan
* @dependabot[bot]

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.0...1.1.1

## What's Changed in 1.1.0
### ⚙️ Miscellaneous Tasks

* add in memory example by @karpetrosyan
### 🐛 Bug Fixes

* pass any response with non-expected status code on revalidation to client by @karpetrosyan
* pass any response with non-expected status code on revalidation to client by @karpetrosyan
### 🚀 Features

* allow setting storage base with via `database_path` for sqlite storage by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0...1.1.0

## What's Changed in 1.0.0
### ⚙️ Miscellaneous Tasks

* add examples, improve docs by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0b1...1.0.0

## What's Changed in 1.0.0b1
### ♻️ Refactoring

* add policies by @karpetrosyan
### ⚙️ Miscellaneous Tasks

* add graphql docs by @karpetrosyan
* improve sans-io diagram colors by @karpetrosyan
### 🐛 Bug Fixes

* filter out `Transfer-Encoding` header for asgi responses by @karpetrosyan
* body-sensitive responses caching by @karpetrosyan
### 🚀 Features

* add global `use_body_key` setting by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev3...1.0.0b1

## What's Changed in 1.0.0.dev3
### ♻️ Refactoring

* automatically generate httpx sync integration from async by @karpetrosyan
* replace pairs with entries, simplify storage API by @karpetrosyan
### ⚙️ Miscellaneous Tasks

* more robust compressed response caching by @karpetrosyan
* add custom integrations docs by @karpetrosyan
* simplify metadata docs by @karpetrosyan
### 🐛 Bug Fixes

* add date header for proper age calculation by @karpetrosyan
* handle httpx iterable usage instead of iterator correctly by @karpetrosyan
* fix compressed data caching for requests by @karpetrosyan
* raise on consumed httpx streams, which we can't store as is (it's already decoded) by @karpetrosyan
* add missing permissions into `publish.yml` by @karpetrosyan
### 🚀 Features

* add logging for asgi by @karpetrosyan
* add blacksheep integration examples by @karpetrosyan
* add integrations with fastapi and asgi by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev2...1.0.0.dev3

## What's Changed in 1.0.0.dev2
### ⚙️ Miscellaneous Tasks

* fix time travel date, explicitly specify the timezone by @karpetrosyan
* add import without extras check in ci by @karpetrosyan
* remove redundant utils and tests by @karpetrosyan
### 🐛 Bug Fixes

* don't raise an error on 3xx during revalidation by @karpetrosyan
* fix check for storing auth requests by @karpetrosyan
### 🚀 Features

* add hishel_created_at response metadata by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev1...1.0.0.dev2

## What's Changed in 1.0.0.dev1
### ⚙️ Miscellaneous Tasks

* remove some redundant utils methods by @karpetrosyan
### 📦 Dependencies

* improve git-cliff by @karpetrosyan
* install async extra with httpx by @karpetrosyan
* make `anysqlite` optional dependency by @karpetrosyan
* make httpx and async libs optional dependencies by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev0...1.0.0.dev1

## What's Changed in 1.0.0.dev0
### ⚙️ Miscellaneous Tasks

* improve docs versioning, deploy dev doc on ci by @karpetrosyan
* use mike powered versioning by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/0.1.5...1.0.0.dev0

## What's Changed in 0.1.5
### ⚙️ Miscellaneous Tasks

* remove some redundant files from repo by @karpetrosyan
### 🐛 Bug Fixes

* fix some line breaks by @karpetrosyan
### 🚀 Features

* increase requests buffer size to 128KB, disable charset detection by @karpetrosyan
* feat: add close method to storages API by @karpetrosyan in [#384](https://github.com/karpetrosyan/hishel/pull/384)
* better cache-control parsing by @karpetrosyan
* set chunk size to 128KB for httpx to reduce SQLite read/writes by @karpetrosyan

### Contributors
* @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/0.1.4...0.1.5

## What's Changed in 0.1.4
### ⚙️ Miscellaneous Tasks

* move some tests to beta by @karpetrosyan
* add sqlite tests for new storage by @karpetrosyan
* temporary remove python3.14 from CI by @karpetrosyan
* chore(internal): remove src folder by @karpetrosyan in [#373](https://github.com/karpetrosyan/hishel/pull/373)
* chore: improve CI by @karpetrosyan in [#369](https://github.com/karpetrosyan/hishel/pull/369)
### 🐛 Bug Fixes

* fix beta imports by @karpetrosyan
* create an sqlite file in a cache folder by @karpetrosyan
### 🚀 Features

* better async implemetation for sqlite storage by @karpetrosyan
* get rid of some locks from sqlite storage by @karpetrosyan
* add sqlite storage for beta storages by @karpetrosyan
* feat: allow already consumed streams with `CacheTransport` by @jamesbraza in [#377](https://github.com/karpetrosyan/hishel/pull/377)
* feat: add support for a sans-IO API by @karpetrosyan in [#366](https://github.com/karpetrosyan/hishel/pull/366)

### Contributors
* @karpetrosyan
* @jamesbraza
* @GugNersesyan
* @dependabot[bot]
* @mmdbalkhi
* @AstraLuma
* @deathaxe

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/0.1.3...0.1.4

