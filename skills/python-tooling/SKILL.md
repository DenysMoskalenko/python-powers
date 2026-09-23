---
name: python-tooling
description: Use when bootstrapping or changing Python tooling in `pyproject.toml` or `.pre-commit-config.yaml`, or deciding what to run after a code change — uv dependency management, ruff formatting/linting, ty type checking, complexipy, pytest and pytest-asyncio settings, the coverage gate, prek hooks, optional Makefile wrappers, CI quality jobs, and `DeprecationWarning` / `filterwarnings` policy.
---

# Python Tooling

Recommended baseline for modern Python projects. Prefer `pyproject.toml` for tool configuration when the tool supports it, keep tool-specific files when it does not (for example `.pre-commit-config.yaml`), and expose common workflows either through direct `uv run ...` commands or optional `make` wrappers. Adapt command names to the repo instead of assuming one fixed Makefile surface.

> Requires Python 3.13+, uv, ruff, ty.

**Related**: `python-code-style`, `python-testing`, `project-scaffolding`.

For code style rules use `python-code-style`. For test layout and helpers use `python-testing`.

For first-time project setup, full `pyproject.toml` tool snippets, and the baseline
`.pre-commit-config.yaml`, load `references/setup.md`.

## uv — Dependency Management

### Adding Dependencies

```bash
uv add <package>           # production dependency
uv add --group dev <package>  # dev dependency
```

Always use the latest version. Never guess or hardcode version numbers — `uv add` resolves the latest automatically.

### Running Commands

When you invoke tools directly, run them through `uv run`:

```bash
uv run pytest
uv run ruff check
uv run alembic upgrade head
```

This ensures the correct virtualenv and dependencies are used regardless of shell activation state.

## ruff — Formatting and Linting

Ruff owns formatting, linting, and import sorting. Do not add black, isort, or flake8
separately unless the repo has a specific migration constraint.

Baseline choices:
- **120-character lines** — wide enough for modern screens, narrow enough for side-by-side diffs
- **Single quotes** — less visual noise than double quotes
- **Tests ignore S101** (assert) and **ARG** (unused arguments) — these are normal in test code
- **isort integrated** — import sorting handled by ruff, no separate isort config needed

Load `references/setup.md` when creating or changing the full ruff configuration.

### Usage

```bash
# After an edit: only the files you changed
uv run ruff format <paths>
uv run ruff check --fix <paths>

# Whole project: `make lint` if the project exposes Make targets, otherwise
uv run ruff format .
uv run ruff check --fix .
```

**Always run the formatter+linter after changing any Python file**, on the files you changed. `make lint` reformats the whole project, so use it only when the repository is already clean or the task is the cleanup.

## ty — Type Checking

```bash
# If the project exposes a Make target
make typecheck

# Otherwise run ty directly
uv run ty check
```

Load `references/setup.md` when creating or changing the full ty configuration.

## pytest — Test Configuration

Use pytest through the repo's wrapper or `uv run pytest`. Keep output compact enough to
spot failures quickly.

- Use `asyncio_mode = auto` so async tests run without `@pytest.mark.asyncio`
- Use `addopts = -ra` for compact extra summaries of skipped, xfailed, and failed tests
- Add `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"` only when you actually use session-scoped async fixtures — the fixture setting alone leaves function-scoped tests on a different event loop than the fixtures
- Add targeted `filterwarnings` entries only for third-party warnings you intentionally suppress
- Load `references/setup.md` when creating or changing the baseline pytest configuration

## Zero Warnings Policy

The app, tests, migrations, and any scripts must run cleanly — no deprecation notices, `RuntimeWarning`s, or stray tracebacks. A noisy run hides real problems.

When a warning or non-fatal error appears:

1. **Surface it to the user immediately.** State what the warning is, where it came from, and whether it looks actionable.
2. **Propose a concrete next step**, one of:
   - **Fix it** — upgrade the dependency, change the API call, or adjust the code. Preferred when the warning points at your code.
   - **Suppress it** — add a targeted `filterwarnings` entry (pytest) or `warnings.filterwarnings(...)` (app) scoped to the exact message, module, and category. Never silence broad categories.
   - **Track it** — if it is a third-party issue that cannot be fixed now, link the upstream issue in a comment next to the suppression so it can be removed later.
3. **Never swallow errors silently.** A bare `except Exception: pass` or unchecked warning is a bug hiding in plain sight.

Example of a narrow suppression:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    # upstream issue: github.com/org/lib/issues/123 — remove when fixed
    "ignore:The @wait_container_is_ready decorator is deprecated:DeprecationWarning:testcontainers.core.waiting_utils",
]
```

The rule: a clean output is a feature. If you cannot make it clean, explain why, show the suppression, and link the follow-up.

## pre-commit

The hook runner is `prek` (`uv run prek install`, `uv run prek run --all-files`), not the
`pre-commit` package; it reads the same `.pre-commit-config.yaml`. Hooks should run project
tools from the project's uv environment. Keep ruff and ty as `repo: local` hooks using
`uv run`; do not use `astral-sh/ruff-pre-commit` for the baseline. Load `references/setup.md`
for the full `.pre-commit-config.yaml` snippet.

## Optional Makefile Workflow

If the project uses `make`, make it the single entry point for common quality workflows. If it does not, run the equivalent `uv run ...` commands directly.

| Command | What it does |
|---------|-------------|
| `make lint` | Format + lint with auto-fix |
| `make lint-no-format` | Lint only, no format check (`ruff check`) |
| `make typecheck` | Type check with ty |
| `make complexitycheck` | Cognitive complexity check with complexipy |
| `make test` | Run pytest |
| `make test-coverage` | Tests with 90% coverage gate |
| `make check` | lint + typecheck + complexitycheck + test-coverage (full quality gate) |

### Workflow Rules

1. **After every Python code change**: run the formatter+linter pair on the changed files (`uv run ruff format <paths>` and `uv run ruff check --fix <paths>`; `make lint` only when the repository is already clean)
2. **Before opening a PR**: run the full local quality gate (`make check` or the equivalent direct command sequence); `make check` starts with `make lint`, so on a repository that is not formatter-clean run `make lint-no-format typecheck complexitycheck test-coverage` instead
3. **If the repo defines wrappers**: keep wrapper names boring and obvious (`lint`, `typecheck`, `test`, `check`)
4. **If the repo does not define wrappers**: document the direct `uv run ...` commands instead of adding `make` just for habit

## CI Pipeline

A minimal CI pipeline usually runs:

1. **Lint job**: `ruff format --check` + `ruff check` (CI checks, doesn't fix) + `ty check` + `complexipy`
2. **Test job**: `pytest` (after lint passes)

CI checks formatting even though hooks format locally: a hook can be skipped with `--no-verify` or never installed in a clone. The CI lint job should use the direct commands; `make lint-no-format` runs only `ruff check`.

## Gotchas

- Never guess dependency versions — `uv add` resolves the latest automatically
- `uv run` is required even with an activated venv if you want consistent behavior in CI
- ruff replaces black, isort, and most flake8 plugins — don't add those separately
- ty is different from mypy — some type: ignore comments may need `# type: ignore[ty:...]` syntax
- Treat `make` targets as optional convenience wrappers, not as part of Python itself — some projects expose only direct `uv run ...` commands
- If a tool requires its own config file, keep it there instead of forcing everything into `pyproject.toml`
