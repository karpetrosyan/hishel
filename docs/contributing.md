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

2. **Clone and create a branch**:
```bash
git clone https://github.com/username/hishel
cd hishel
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

Hishel uses an **unasync** strategy similar to [HTTP Core](https://github.com/encode/httpcore) to maintain both async and sync APIs without code duplication.

### How It Works

1. **Write async code only** (when there's a sync equivalent): Primary development for dual async/sync code happens in async files located in:
   - `hishel/_core/_async/`
   - `tests/_core/_async/`

2. **Automatic generation**: The `scripts/unasync` script automatically transforms async code into sync equivalents:
   - `hishel/_core/_async/` → `hishel/_core/_sync/`
   - `tests/_core/_async/` → `tests/_core/_sync/`

3. **Pattern substitution**: The script performs intelligent substitutions:
   - `async def` → `def`
   - `async with` → `with`
   - `await` → (removed)
   - `AsyncIterator` → `Iterator`
   - And many more patterns (see `scripts/unasync` for the full list)

### The `scripts/unasync` Script

This Python script is the core of the async-to-sync transformation:

- **Manual execution**: `./scripts/unasync` - Generates sync files from async files
- **Check mode**: `./scripts/unasync --check` - Verifies async/sync files are in sync (used in CI)
- **Automatic invocation**: Automatically called by `scripts/fix` and checked by `scripts/lint`

**Key Features:**

- Transforms async patterns to their sync equivalents using regex substitution
- Processes entire directories or individual files
- Validates that all defined substitution patterns are actually used
- Can operate in check-only mode to verify consistency without modifying files

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

## Questions?

If you have questions about contributing, feel free to:
- Open an issue for discussion
- Ask in an existing pull request
- Check the [documentation](https://hishel.com)

Thank you for contributing to Hishel! 🎉

