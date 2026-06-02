# Python Tooling Setup Reference

Full baseline snippets for bootstrapping or changing Python project tooling. Load this
only when creating or editing `pyproject.toml`, `.pre-commit-config.yaml`, or first-time
project setup commands.

Contents:
- uv environment setup
- ruff configuration
- ty configuration
- pytest configuration
- pre-commit configuration

## uv Environment Setup

```bash
uv venv --python 3.13
source .venv/bin/activate
uv sync
```

## ruff Configuration

```toml
[tool.ruff]
line-length = 120
target-version = "py313"

[tool.ruff.format]
quote-style = "single"
indent-style = "space"
docstring-code-format = true

[tool.ruff.lint]
select = [
    "E",     # Errors
    "F",     # Pyflakes
    "I",     # isort
    "S",     # flake8-bandit (security)
    "T20",   # flake8-print
    "ASYNC", # flake8-async
    "A",     # flake8-builtins
    "B",     # flake8-bugbear
    "C4",    # flake8-comprehensions
    "C90",   # McCabe complexity
    "DTZ",   # flake8-datetimez
    "ARG",   # flake8-unused-arguments
    "BLE",   # flake8-blind-except
    "ERA",   # eradicate (commented code)
    "ANN",   # flake8-annotations
    "FAST",  # FastAPI
    "RUF",   # Ruff-specific
]
pydocstyle.convention = 'google'

[tool.ruff.lint.mccabe]
max-complexity = 15

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101", "ARG"]

[tool.ruff.lint.isort]
known-local-folder = ["tests", "app", "scripts"]
split-on-trailing-comma = true
combine-as-imports = true
case-sensitive = false
detect-same-package = true
order-by-type = false
force-sort-within-sections = true
```

## ty Configuration

```toml
[tool.ty.rules]
unused-ignore-comment = "ignore"
```

## pytest Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-ra"
```

Add `asyncio_default_fixture_loop_scope = "session"` only when the project actually uses
session-scoped async fixtures.

## pre-commit Configuration

Ruff and ty must run from the project's uv environment, so keep them as local hooks.

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
      - id: check-json
      - id: check-toml
      - id: check-yaml
      - id: check-merge-conflict

  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]
      - id: ty
        name: ty check
        entry: uv run ty check
        language: system
        types: [python]
        pass_filenames: false
```
