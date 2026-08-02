# Temporary Test Scratchpad (`tests/temp`)

This directory is dedicated to **temporary tests**, ad-hoc reproduction scripts, fast verification snippets, and transient test fixtures.

## Policies & Retention

1. **Transient Scope**: Files in this directory are meant for active development and debugging tasks.
2. **Git Hygiene**: Temporary test files inside this directory (except `.gitkeep` and `README.md`) are excluded from Git commits via `.gitignore`.
3. **Graduation**: If a temporary test proves valuable for long-term regression prevention, refactor and move it to `tests/unit/` or `tests/integration/`.
