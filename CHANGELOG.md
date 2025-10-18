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
## [0.1.3] - 2025-07-06

### 🚀 Features

- Support providing a path prefix to S3 storage (#342)

### 📚 Documentation

- Update link to httpx transports page (#337)
## [0.1.2] - 2025-04-04

### 🐛 Bug Fixes

- Requirements.txt to reduce vulnerabilities (#263)
## [0.0.30] - 2024-07-12

### 🐛 Bug Fixes

- Requirements.txt to reduce vulnerabilities (#245)
- Requirements.txt to reduce vulnerabilities (#255)
## [0.0.27] - 2024-05-31

### 🐛 Bug Fixes

- *(redis)* Do not update metadata with negative ttl (#231)
## [0.0.1] - 2023-07-22
