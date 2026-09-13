---
name: python-tooling
description: Use when setting up or changing Python tooling in `pyproject.toml` or `.pre-commit-config.yaml`, or deciding what to run after a code change — uv (`uv add`, `uv remove`, `uv sync --locked`), ruff (`# noqa`), ty (`ty ignore[rule]` comments), complexipy, pytest and pytest-asyncio settings, the coverage gate, prek hooks, CI jobs, and `DeprecationWarning` / `filterwarnings` policy.
---

# Python Tooling

This skill owns the toolchain of a Python service: the uv workflow, the ruff, ty, complexipy, pytest and coverage configuration in `pyproject.toml`, prek hooks, the CI quality job, and the warnings policy. Every command and tool setting the sibling skills rely on is defined here. An explicit user or project instruction (`AGENTS.md`, `pyproject.toml`, existing code) overrides a house default here; keep the invariants that still apply and name the default you departed from.

> Requires Python 3.13+, uv, ruff, ty, complexipy, prek, pytest, pytest-asyncio, pytest-cov.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` (load it alongside), `python-testing`, `postgres-database`, `project-scaffolding`.

Load `references/setup.md` when you create or change `pyproject.toml`, `.pre-commit-config.yaml`, or set up a repository for the first time; it carries the complete baseline for all three.

## Commands

The direct commands are the contract; a `Makefile` is a convenience wrapper. Use the target when the repository defines one, the direct command otherwise, and do not add a `Makefile` just to have the targets.

| Target | Direct command |
|---|---|
| `make lint` | `uv run ruff format` then `uv run ruff check --fix` |
| `make lint-no-format` | `uv run ruff check` |
| `make typecheck` | `uv run ty check` |
| `make complexitycheck` | `uv run complexipy .` |
| `make test` | `uv run pytest` |
| `make test-coverage` | `uv run pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90` |
| `make check` | lint, typecheck, complexitycheck, test-coverage, in that order |
| `make run` | `uv run python -m app.main` |

A project with a database adds these. They run against the `DATABASE_URL` in `.env`, and `downgrade` drops schema, so point them at the local compose database only unless the user names another target:

| Target | Direct command |
|---|---|
| `make up-dependencies` | `docker compose up` (add `-d` from an agent shell; the target itself is foreground) |
| `make migration MSG="add authors"` | `uv run alembic revision --autogenerate -m "add authors"` |
| `make migrate` | `uv run alembic upgrade head` |
| `make upgrade` | `uv run alembic upgrade +1` |
| `make downgrade` | `uv run alembic downgrade -1` |

After changing a Python file, run `uv run ruff format <paths>` and `uv run ruff check --fix <paths>` on the files you changed; go project-wide only when the repository is already clean or the task is the cleanup. Before opening a pull request run the whole gate (`make check`): type errors and complexity findings do not show up in the lint step.

## uv

uv owns the interpreter, the dependency lists in `pyproject.toml`, and `uv.lock`. Run tools through `uv run`, which resolves the project environment itself: no `uv venv` step, no activated virtualenv, so the same command works in a shell, a hook and CI.

```bash
uv add httpx                      # runtime dependency
uv add --group dev pytest-cov     # development dependency
uv remove httpx                   # drop a runtime dependency
uv remove --group dev pytest-cov  # drop a development dependency
uv lock --upgrade-package ruff    # move one package to a newer release
uv sync                           # install exactly what the lock file says
```

`uv add` resolves a current compatible version and writes it to both `pyproject.toml` and `uv.lock`, so never type a version by hand. Pin one only for a real constraint — a known-broken release, an unfinished migration — and say which in the same change.

`uv python pin 3.13` writes `.python-version` and is part of first-time setup. Without it uv installs the newest interpreter that satisfies `requires-python`, which is how a project written against the floor ends up running on a newer release.

## ruff

ruff is the formatter, linter and import sorter, so black, isort and the flake8 plugins stay out of the project. The baseline is 120-character lines, single quotes, and the rule families in `references/setup.md`; `UP` among them keeps `type X = ...`, `collections.abc` imports and PEP 696 defaults current on the 3.13 floor. No `D` rules are selected, so a `pydocstyle.convention` line configures a family that never runs.

Suppress a finding on the reported line and name the rule: `# noqa: RUF012`. A blanket `# noqa` also silences future findings on that line; `RUF100` reports either form once the finding is gone, which is the signal to delete the comment.

## ty

`uv run ty check` is the type checker. Suppress a single diagnostic on the reported line, naming the rule:

| Comment at the end of the offending line | Suppresses |
|---|---|
| `# ty: ignore[invalid-argument-type]` | yes |
| `# type: ignore` | yes |
| `# type: ignore[ty:invalid-argument-type]` | yes |
| `# type: ignore[arg-type]`, or any other mypy code | no — ty keeps reporting while the comment reads as handled |

The baseline has no `[tool.ty.rules]` block: a project-wide override also covers code written later, and it hides ty's unused-suppression diagnostics, which tell you a `# ty: ignore` has outlived its problem.

## pytest and coverage

The baseline `[tool.pytest.ini_options]` is in `references/setup.md`: `asyncio_mode = "auto"` so async tests need no `@pytest.mark.asyncio`, `addopts = "-ra"` for a compact summary of everything that was not a plain pass, and both pytest-asyncio loop-scope defaults (`asyncio_default_fixture_loop_scope`, `asyncio_default_test_loop_scope`) set to `"session"`.

The loop scopes are a house default: psycopg tolerates any combination, but both at `"session"` put fixtures and tests on one event loop, which a loop-bound driver such as asyncpg needs.

Coverage comes from `pytest-cov` in the dev group. The gate is `--cov-fail-under=90`, which only means 90% together with `[tool.coverage.report] precision = 2` (see Gotchas).

## complexipy

`uv run complexipy .` is part of the gate. It measures cognitive complexity, a different number from ruff's `C901` cyclomatic complexity, so the two catch different functions; the baseline sets both limits to 12. Split a function over the limit into named pieces; raising the limit is a project-wide decision, not a way past one function.

## Hooks

`prek` is the hook runner. It reads `.pre-commit-config.yaml` (the format's fixed file name); the `pre-commit` package itself is not installed.

```bash
uv add --group dev prek
uv run prek install
uv run prek run --all-files
```

ruff and ty run as `repo: local` hooks through `uv run`, so hooks use the lock file's versions rather than a second set from a hook mirror. The remote hooks repository needs a `rev:` pin.

## CI

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run complexipy .
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90
```

The test step needs a Docker daemon for the Postgres testcontainer; GitHub-hosted Ubuntu runners have one. On a runner without it, provide Postgres as a CI service instead.

`--locked` makes a stale `uv.lock` fail the job instead of being rewritten. CI checks formatting even though hooks format locally, because a hook can be skipped with `--no-verify` or never installed in a clone.

## Warnings

A warning from a run you started is part of the result: name the source, quote the message, say whether your change caused it. Then:

- Fix it when it points at project code: the deprecated call, the moved import, the dependency that needs upgrading.
- Suppress it narrowly when it comes from a dependency you cannot change: scope the entry to message, category and module, and put the upstream issue above it.
- Track it when neither is possible now, so the suppression has a removal condition.

```toml
[tool.pytest.ini_options]
filterwarnings = [
    # upstream issue: github.com/org/lib/issues/123 — remove when fixed
    "ignore:The @wait_container_is_ready decorator is deprecated:DeprecationWarning:testcontainers.core.waiting_utils",
]
```

After a dependency upgrade, delete entries that no longer match anything (`uv run pytest -W always` with the block removed shows what still needs it); a dead entry hides that upstream fixed the problem. The entry above is such a case: the Postgres container stopped using that decorator in a later testcontainers release, so nothing matched it any more; it stays here only as the shape of a scoped entry.

Warnings that predate your change and have nothing to do with it are not yours to clean up in passing: report them and leave them unless the task says otherwise.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| `pip install`, or a dependency typed by hand in `pyproject.toml` | `uv add <pkg>` / `uv add --group dev <pkg>` | pip writes nothing to the lock file; a hand-typed entry stays unlocked until someone runs `uv sync`, and a hand-typed version is a guess |
| `# type: ignore[assignment]` to quiet ty | `# ty: ignore[<rule>]` on the reported line | mypy codes suppress nothing in ty |
| `filterwarnings = ["ignore::DeprecationWarning"]` | An entry scoped to message, category and module | The broad form also swallows the next warning |

## Gotchas

- `--cov-fail-under=90` passes below 90% unless `[tool.coverage.report] precision = 2` is set: pytest-cov compares `round(total, precision)` against the threshold and precision defaults to 0, so 89.6% prints `FAIL Required test coverage of 90% not reached` and still exits 0.
- Coverage of an async SQLAlchemy service needs `[tool.coverage.run] concurrency = ["thread", "greenlet"]`: SQLAlchemy runs the driver in a greenlet and coverage.py stops tracing at the switch, so the line after every `await session.scalar(...)` — usually the `if book is None:` guard — is reported as missed even when covered.
- `unused-ignore-comment` and `unused-type-ignore-comment` are two different ty rules, for stale `# ty: ignore[...]` and stale `# type: ignore[...]` respectively. Substituting one for the other produces no `unknown-rule` warning and no effect.
- ty is pre-1.0: an upgrade can add diagnostics to clean code, so move it with `uv lock --upgrade-package ty` on its own and read the new findings before suppressing them.
- The hook runner needs a git index. Outside a repository it fails with `fatal: not a git repository`; inside one with nothing staged every hook reports `(no files to check) Skipped` and exits 0, which looks identical to success.
- A hook that rewrites files fails the commit with `- files were modified by this hook`. Stage the rewritten files and commit again; do not re-run with `--no-verify`.
- `uv add` and `uv remove` re-lock and re-sync in one step; `uv sync` is for a checkout someone else's lock file arrived in.
- ruff derives the target Python version from `requires-python`, so the baseline sets no `target-version`; a second copy of the floor drifts from the first.
- pytest-asyncio's warning about an unset loop-scope default is raised during `pytest_configure`, before pytest's warning capture starts, so neither the summary nor `pytest -W always` shows it (`PYTHONWARNINGS=always` does, and the session header prints `asyncio_default_fixture_loop_scope=None`); a project that dropped both options looks clean until a loop-bound driver is introduced.
