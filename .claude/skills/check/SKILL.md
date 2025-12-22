---
name: check
description: Run all code quality checks including ruff linting, ruff formatting, pyright type checking, and pytest tests. Use when the user wants to verify code quality, run checks before committing, or ensure all tests pass.
allowed-tools: Bash
---

# Code Quality Check

Run the complete quality pipeline for the Mobile Geodatabase library.

## Commands to Run (in sequence)

```bash
# 1. Lint check
uv run ruff check src tests

# 2. Format check
uv run ruff format --check src tests

# 3. Type check (strict mode)
uv run pyright src tests

# 4. Run all tests
uv run pytest
```

## All-in-One Command

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src tests && uv run pytest
```

## Expected Results

- **Ruff lint**: Should pass with no errors
- **Ruff format**: Should show "All checks passed!"
- **Pyright**: 0 errors expected (warnings from fiona stubs are acceptable)
- **Pytest**: All tests should pass (some may be skipped if test DB is missing)

## Code Quality Rules

Per CLAUDE.md:

- Never add linting ignore comments (`# type: ignore`, `# noqa`, `# pyright: ignore`)
- All code must pass ruff and pyright without suppressions
- Python 3.12+ required with modern union syntax (`X | Y`)
