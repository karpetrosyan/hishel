## What's Changed in 1.1.2
* fix: respect shared option when excluding unstorable headers by @karpetrosyan
* fix: remove s-maxage consideration for private caches by @karpetrosyan
* fix: respect shared option when excluding unstorable headers by @jlopex in [#401](https://github.com/karpetrosyan/hishel/pull/401)
* fix: remove s-maxage consideration for private caches by @jlopex in [#400](https://github.com/karpetrosyan/hishel/pull/400)
* fix: ensure 304 responses don't leak by @karpetrosyan

## New Contributors
* @jlopex made their first contribution in [#401](https://github.com/karpetrosyan/hishel/pull/401)

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.1...1.1.2

## What's Changed in 1.1.1
* Revert "Revert "chore(deps): bump actions/upload-artifact from 4 to 5 "" by @karpetrosyan
* Revert "chore(deps): bump actions/download-artifact from 4 to 6 " by @karpetrosyan
* Revert "chore(deps): bump actions/upload-artifact from 4 to 5 " by @karpetrosyan
* update uv.lock by @karpetrosyan
* Version 1.1.1 by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.1.0...1.1.1

## What's Changed in 1.1.0
* Version 1.1.0 by @karpetrosyan
* fix: pass any response with non-expected status code on revalidation to client by @karpetrosyan
* fix: pass any response with non-expected status code on revalidation to client by @karpetrosyan
* feat: allow setting storage base with via `database_path` for sqlite storage by @karpetrosyan
* fix in memory example by @karpetrosyan
* chore: add in memory example by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0...1.1.0

## What's Changed in 1.0.0
* Version 1.0.0 by @karpetrosyan
* chore(docs): add examples, improve docs by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0b1...1.0.0

## What's Changed in 1.0.0b1
* Version 1.0.0b1 by @karpetrosyan
* improve docs by @karpetrosyan
* fix: filter out `Transfer-Encoding` header for asgi responses by @karpetrosyan
* fix body sensitive docs by @karpetrosyan
* refactor: add policies by @karpetrosyan
* chore(docs): add graphql docs by @karpetrosyan
* feat: add global `use_body_key` setting by @karpetrosyan
* chore(docs): improve sans-io diagram colors by @karpetrosyan
* fix: body-sensitive responses caching by @karpetrosyan
* mention body sensitive content caching by @karpetrosyan
* clean up roadmap by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev3...1.0.0b1

## What's Changed in 1.0.0.dev3
* Version 1.0.0.dev3 by @karpetrosyan
* fix ci by @karpetrosyan
* fix: add date header for proper age calculation by @karpetrosyan
* rename some methods by @karpetrosyan
* refactor: automatically generate httpx sync integration from async by @karpetrosyan
* change pairs to entries in some places by @karpetrosyan
* fix lint format by @karpetrosyan
* refactor: replace pairs with entries, simplify storage API by @karpetrosyan
* better docs by @karpetrosyan
* better custom integrations docs by @karpetrosyan
* more private by @karpetrosyan
* fix lint, make things private by @karpetrosyan
* dont fail if unasync rule was not used by @karpetrosyan
* chore: more robust compressed response caching by @karpetrosyan
* chore(docs): add custom integrations docs by @karpetrosyan
* feat: add logging for asgi by @karpetrosyan
* fix: handle httpx iterable usage instead of iterator correctly by @karpetrosyan
* feat: add blacksheep integration examples by @karpetrosyan
* Change note syntax for ASGI middleware by @karpetrosyan
* fix lint by @karpetrosyan
* feat: add integrations with fastapi and asgi by @karpetrosyan
* fix readme by @karpetrosyan
* add icon for introduction page by @karpetrosyan
* fix test by @karpetrosyan
* properly close resource by @karpetrosyan
* fix: fix compressed data caching for requests by @karpetrosyan
* fix: raise on consumed httpx streams, which we can't store as is (it's already decoded) by @karpetrosyan
* chore(docs): simplify metadata docs by @karpetrosyan
* fix: add missing permissions into `publish.yml` by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev2...1.0.0.dev3

## What's Changed in 1.0.0.dev2
* Version 1.0.0.dev2 by @karpetrosyan
* unasync by @karpetrosyan
* chore: fix time travel date, explicitly specify the timezone by @karpetrosyan
* fix: don't raise an error on 3xx during revalidation by @karpetrosyan
* chore: add import without extras check in ci by @karpetrosyan
* chore(internal): remove redundant utils and tests by @karpetrosyan
* feat: add hishel_created_at response metadata by @karpetrosyan
* fix: fix check for storing auth requests by @karpetrosyan
* better git-cliff by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev1...1.0.0.dev2

## What's Changed in 1.0.0.dev1
* Version 1.0.0.dev1 by @karpetrosyan
* fix changelog + uv lock by @karpetrosyan
* fix linting by @karpetrosyan
* chore(internal): remove some redundant utils methods by @karpetrosyan
* fix mike deploy by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/1.0.0.dev0...1.0.0.dev1

## What's Changed in 1.0.0.dev0
* fix publish.yml by @karpetrosyan
* fix format by @karpetrosyan
* prepare 1.0.0.dev0 release by @karpetrosyan
* improve `CacheOptions` docs by @karpetrosyan
* don't make release version latest by default by @karpetrosyan
* fix changelog by @karpetrosyan
* fix action permissions by @karpetrosyan
* improve docs introduction by @karpetrosyan
* better docs publishing, better project description by @karpetrosyan
* fix docs publishing by @karpetrosyan
* fix docs deploying by @karpetrosyan
* chore(docs): improve docs versioning, deploy dev doc on ci by @karpetrosyan
* fix unasync by @karpetrosyan
* fix unasync by @karpetrosyan
* fix unasync by @karpetrosyan
* Version 1.0.0.dev0 by @karpetrosyan
* chore(docs): use mike powered versioning by @karpetrosyan
* fix changelog by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/0.1.5...1.0.0.dev0

## What's Changed in 0.1.5
* Version 0.1.5 by @karpetrosyan in [#385](https://github.com/karpetrosyan/hishel/pull/385)
* feat(perf): increase requests buffer size to 128KB, disable charset detection by @karpetrosyan
* feat: add close method to storages API by @karpetrosyan in [#384](https://github.com/karpetrosyan/hishel/pull/384)
* fix headers by @karpetrosyan
* fix lint by @karpetrosyan
* ruff format by @karpetrosyan
* feat: better cache-control parsing by @karpetrosyan
* feat(perf): set chunk size to 128KB for httpx to reduce SQLite read/writes by @karpetrosyan
* fix(docs): fix some line breaks by @karpetrosyan
* chore: remove some redundant files from repo by @karpetrosyan

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/0.1.4...0.1.5

## What's Changed in 0.1.4
* Version 0.1.4 by @karpetrosyan in [#381](https://github.com/karpetrosyan/hishel/pull/381)
* fix lint by @karpetrosyan
* more docs! by @karpetrosyan
* ensure connection is not stored by @karpetrosyan
* fix annotations by @karpetrosyan
* fix typing by @karpetrosyan
* format by @karpetrosyan
* more docs! more tests! by @karpetrosyan
* lot of fixes by @karpetrosyan
* remove redundant files by @karpetrosyan
* remove docs footer by @karpetrosyan
* fix: fix beta imports by @karpetrosyan
* uv lock by @karpetrosyan
* fix: create an sqlite file in a cache folder by @karpetrosyan
* better unasync by @karpetrosyan
* feat: better async implemetation for sqlite storage by @karpetrosyan
* feat: get rid of some locks from sqlite storage by @karpetrosyan
* chore(tests): move some tests to beta by @karpetrosyan
* fix tests by @karpetrosyan
* fix tests by @karpetrosyan
* fix lint by @karpetrosyan
* chore(tests): add sqlite tests for new storage by @karpetrosyan
* feat: add sqlite storage for beta storages by @karpetrosyan
* Adding `.venv` to `.gitignore` by @jamesbraza in [#379](https://github.com/karpetrosyan/hishel/pull/379)
* Revert "add ethical ads" by @karpetrosyan
* add ethical ads by @karpetrosyan
* feat: allow already consumed streams with `CacheTransport` by @jamesbraza in [#377](https://github.com/karpetrosyan/hishel/pull/377)
* chore(ci): fix lint script by @GugNersesyan in [#375](https://github.com/karpetrosyan/hishel/pull/375)
* chore(internal): temporary remove python3.14 from CI by @karpetrosyan
* chore(internal): remove src folder by @karpetrosyan in [#373](https://github.com/karpetrosyan/hishel/pull/373)
* New storage API by @karpetrosyan in [#359](https://github.com/karpetrosyan/hishel/pull/359)
* chore: improve CI by @karpetrosyan in [#369](https://github.com/karpetrosyan/hishel/pull/369)
* feat: add support for a sans-IO API by @karpetrosyan in [#366](https://github.com/karpetrosyan/hishel/pull/366)
* Enhance documentation with donation link by @karpetrosyan in [#368](https://github.com/karpetrosyan/hishel/pull/368)
* Update README to include donation link by @karpetrosyan in [#367](https://github.com/karpetrosyan/hishel/pull/367)
* Added `Metadata` to public API by @jamesbraza in [#363](https://github.com/karpetrosyan/hishel/pull/363)
* Bump the python-packages group with 10 updates by @dependabot[bot] in [#354](https://github.com/karpetrosyan/hishel/pull/354)
* skip anysqlite, yaml and redis tests if optional deps are missing by @mmdbalkhi in [#348](https://github.com/karpetrosyan/hishel/pull/348)
* Don't bomb if directory creation races by @AstraLuma in [#353](https://github.com/karpetrosyan/hishel/pull/353)
* Cleanup module imports by @deathaxe in [#351](https://github.com/karpetrosyan/hishel/pull/351)

## New Contributors
* @jamesbraza made their first contribution in [#379](https://github.com/karpetrosyan/hishel/pull/379)
* @GugNersesyan made their first contribution in [#375](https://github.com/karpetrosyan/hishel/pull/375)
* @mmdbalkhi made their first contribution in [#348](https://github.com/karpetrosyan/hishel/pull/348)
* @AstraLuma made their first contribution in [#353](https://github.com/karpetrosyan/hishel/pull/353)
* @deathaxe made their first contribution in [#351](https://github.com/karpetrosyan/hishel/pull/351)

**Full Changelog**: https://github.com/karpetrosyan/hishel/compare/0.1.3...0.1.4

<!-- generated by git-cliff -->
