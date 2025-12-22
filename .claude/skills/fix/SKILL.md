---
name: fix
description: Automatically fix linting and formatting issues using ruff. Use when code has style issues, formatting problems, or when the user wants to clean up code before committing.
allowed-tools: Bash
---

# Auto-Fix Code Issues

Automatically fix linting and formatting issues in the Mobile Geodatabase library.

## Commands to Run

```bash
# 1. Fix linting issues (auto-fixable)
uv run ruff check --fix src tests

# 2. Format code
uv run ruff format src tests
```

## Combined Command

```bash
uv run ruff check --fix src tests && uv run ruff format src tests
```

## What Gets Fixed

**Ruff check --fix** handles:

- Unused imports
- Import sorting
- Simple code style issues
- Many common linting violations

**Ruff format** handles:

- Code formatting (black-compatible)
- Line length (88 characters)
- Whitespace and indentation
- Quote style consistency

## After Fixing

Run the full check to verify:

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src tests
```

## Important Notes

- Some issues cannot be auto-fixed and require manual intervention
- Type errors (pyright) must be fixed manually
- Never add ignore comments - fix the underlying issue instead
