# Claude Code Guidelines

## Code Quality Rules

- **Never add linting ignore comments** (e.g., `# type: ignore`, `# noqa`, `# pyright: ignore`). Fix the underlying issue instead.
- All code must pass ruff and pyright checks without suppressions.
