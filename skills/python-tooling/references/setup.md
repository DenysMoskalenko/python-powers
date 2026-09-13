# Python Tooling Setup

The complete baseline for a repository's tooling: first-time setup commands, the tool sections of `pyproject.toml`, and `.pre-commit-config.yaml`. Load this file when you create or change any of them; `SKILL.md` covers what the commands and settings mean day to day.

Contents:
- First-time setup
- `pyproject.toml` tool sections
- `.pre-commit-config.yaml`

## First-time setup

```bash
uv python pin 3.13
uv add --group dev ruff ty prek complexipy pytest pytest-asyncio pytest-cov
uv sync
uv run prek install
uv run prek run --all-files
```

Commit `.python-version` and `uv.lock` alongside `pyproject.toml`. Runtime dependencies go in with `uv add <package>`; the tool sections below are copied into `pyproject.toml` as they are, with `paths` and `known-local-folder` adjusted if the top-level package is not `app`.

## pyproject.toml tool sections

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
addopts = "-ra"

[tool.coverage.run]
# SQLAlchemy's async layer runs the driver in a greenlet; without this, coverage stops tracing at
# every `await session.scalar(...)` and reports the next line as never executed.
concurrency = ["thread", "greenlet"]

[tool.coverage.report]
# Without this the fail-under threshold is compared against a value rounded to whole percents.
precision = 2

[tool.ruff]
line-length = 120

[tool.ruff.format]
quote-style = "single"
docstring-code-format = true

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "F",     # Pyflakes
    "I",     # isort
    "S",     # flake8-bandit
    "T20",   # flake8-print
    "ASYNC", # flake8-async
    "A",     # flake8-builtins
    "B",     # flake8-bugbear
    "C4",    # flake8-comprehensions
    "C90",   # mccabe complexity
    "DTZ",   # flake8-datetimez
    "ARG",   # flake8-unused-arguments
    "BLE",   # flake8-blind-except
    "ERA",   # eradicate - commented-out code
    "ANN",   # flake8-annotations
    "FAST",  # FastAPI
    "RUF",   # Ruff-specific rules
    "UP",    # pyupgrade
]

[tool.ruff.lint.mccabe]
max-complexity = 12

[tool.ruff.lint.flake8-unused-arguments]
ignore-variadic-names = true

[tool.ruff.lint.flake8-annotations]
allow-star-arg-any = true

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101", "ARG", "ANN"]
"migrations/*" = ["ANN"]

[tool.ruff.lint.isort]
known-local-folder = ["tests", "app", "scripts"]
combine-as-imports = true
order-by-type = false             # sort imported objects by name, not by kind
force-sort-within-sections = true # keep `import x` and `from x import y` in one alphabetical run

[tool.complexipy]
paths = ["app", "tests", "scripts"]
max-complexity-allowed = 12
exclude = []
```

Everything else ruff supports is left at its default, `target-version` included. There is no `[tool.ty]` section: ty runs on its defaults, and diagnostics are suppressed per line.

## .pre-commit-config.yaml

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
        args: [ --markdown-linebreak-ext=md ]
      - id: end-of-file-fixer
      - id: check-added-large-files
        args: [ --maxkb=1024 ]
      - id: check-json
      - id: check-toml
      - id: check-yaml
      - id: check-merge-conflict

  - repo: local
    hooks:
      - id: ruff-check
        name: linter
        entry: uv run ruff check --fix
        language: system
        types: [ python ]
      - id: ruff-format
        name: formatter
        entry: uv run ruff format
        language: system
        types: [ python ]
      - id: ty
        name: ty
        entry: uv run ty check
        language: system
        types: [ python ]
        pass_filenames: false
```

`language: system` tells the runner to execute the entry as it stands instead of building an environment for it. `ty` checks the whole project in one pass, hence `pass_filenames: false`; it still runs only when a Python file is staged.
