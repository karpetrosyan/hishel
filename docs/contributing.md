---
icon: material/hand-coin-outline
---

# Contributing to Hishel

Thank you for being interested in contributing to `Hishel`! We appreciate your efforts and welcome contributions of all kinds.

You can contribute by:

- Reviewing [pull requests](https://github.com/karpetrosyan/hishel/pulls)
- [Opening an issue](https://github.com/karpetrosyan/hishel/issues/new) to report bugs or suggest features
- [Adding a new feature](https://github.com/karpetrosyan/hishel/compare)
- ⭐ **Starring the repository** on [GitHub](https://github.com/karpetrosyan/hishel) - it helps the project grow!

This guide will help you understand the development process and repository structure.

## Getting Started

### Setting Up Your Development Environment

1. **Fork the repository**: Fork [Hishel](https://github.com/karpetrosyan/hishel/) to your GitHub account

2. **Clone and create a branch**, starting from `v2` for Hishel 2.x or `master` for Hishel 1.x:
```bash
git clone https://github.com/username/hishel
cd hishel
git switch v2
git switch -c my-feature-name
```

3. **Install dependencies**: This project uses `uv` for dependency management. Make sure you have it installed, then install the project dependencies:
```bash
uv sync --all-extras --dev
```

## Repository Structure

### The `scripts/` Folder

The `scripts/` directory contains utility scripts to simplify development and maintenance tasks:

- **`scripts/fix`** - Automatically fixes code style issues, formats code, and generates synchronous code from async code
- **`scripts/lint`** - Validates code quality (linting, formatting, type checking, async/sync consistency)
- **`scripts/test`** - Runs the test suite with coverage reporting
- **`scripts/unasync`** - Converts async code to sync code (see below for details)

### Usage Example

```bash
# Fix code style and generate sync files
./scripts/fix

# Check code quality
./scripts/lint

# Run tests with coverage
./scripts/test
```

## Critical: Async/Sync Code Generation

**⚠️ IMPORTANT: Do not manually edit auto-generated synchronous files!**

Hishel maintains both async and sync APIs without code duplication using an **unasync** strategy similar to [httpcore](https://github.com/encode/httpcore).

### How It Works

**Write async code once** - All shared async/sync functionality is written in async files:

- `src/hishel/httpx/_async.py` and `src/hishel/httpx2/_async.py` → auto-generates → `_sync.py` next to each
- `src/hishel/_async_rfc.py` → auto-generates → `_sync_rfc.py`
- `src/hishel/_core/_storages/_async_base.py` and `_async_redis.py` → auto-generates → `_sync_base.py` and `_sync_redis.py`
- `tests/_core/_async/test_sqlite_storage.py` and `test_redis_storage.py` → auto-generates → the same files in `tests/_core/_sync/`
- `tests/test_async_httpx.py` and `test_async_httpx2.py` → auto-generates → `tests/test_sync_httpx.py` and `test_sync_httpx2.py`

**The exception is SQLite** - `_async_sqlite.py` and `_sync_sqlite.py` are written by hand, because the sync storage also has to handle threads. Change both together. `tests/_core/_async/test_sqlite_concurrency.py` and `tests/_core/_sync/test_sqlite_threading.py` are also written by hand.

**Automatic transformation** - The `scripts/unasync` script converts async code to sync:

```python
# Async code (you write this)
async def store(self, key: str) -> None:
    async with self.connection as conn:
        await conn.execute(...)


# Sync code (automatically generated)
def store(self, key: str) -> None:
    with self.connection as conn:
        conn.execute(...)
```

### Using the Script

```bash
# Generate sync files from async files
./scripts/unasync

# Check if sync files are up-to-date (CI)
./scripts/unasync --check

# Or use helper scripts
./scripts/fix     # Auto-generates sync files + formatting
./scripts/lint    # Checks sync files are up-to-date
```

### Development Rules

✅ **DO**:
- Write and edit async files only (`_async.py` and `_async_*.py`), plus `_sync_sqlite.py`
- Run `./scripts/fix` before committing
- Let the script generate all other sync files

❌ **DON'T**:
- Manually edit sync files (`_sync.py` and `_sync_*.py`), other than `_sync_sqlite.py`
- Commit async changes without running unasync
- Modify the sync test files directly

## Development Workflow

### Before Submitting a PR

1. **Make your changes** in the async versions of files
2. **Run the fix script**:
   ```bash
   ./scripts/fix
   ```
3. **Run the linter**:
   ```bash
   ./scripts/lint
   ```
4. **Run tests**:
   ```bash
   ./scripts/test
   ```

## Releasing (Maintainers Only)

This section is for maintainers who have permissions to publish new releases.

### Release Process

Hishel 2.x is released from the `v2` branch, and Hishel 1.x from `master`. Run these steps on the branch you are releasing. Until 2.0 is ready, use prerelease versions like `2.0.0a2` on `v2`, because a stable version would become what `pip install hishel` installs.

1. **Update the version** in `pyproject.toml`:
   ```toml
   [project]
   version = "2.0.0a2"  # Update to new version
   ```

2. **Generate the changelog** using `git cliff`:
   ```bash
   git cliff --output CHANGELOG.md 0.1.3.. --tag 2.0.0a2
   ```
   - Start from `0.1.3` (versions before this didn't use conventional commits)
   - Specify the new release tag with `--tag`

3. **Commit the changes** with an unconventional commit message:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "Version 2.0.0a2"
   ```

4. **Create a git tag** for the release:
   ```bash
   git tag 2.0.0a2
   ```

5. **Push to GitHub** (both commits and tags):
   ```bash
   git push
   git push --tags
   ```

6. **Ensure CI passes** - Wait for all GitHub Actions workflows to complete successfully

7. **Done!** - The release is published once CI passes

## Questions?

If you have questions about contributing, feel free to:
- Open an issue for discussion
- Ask in an existing pull request
- Check the [documentation](https://hishel.com)

Thank you for contributing to Hishel! 🎉

