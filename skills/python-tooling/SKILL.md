---
name: python-tooling
description: Use when setting up or changing Python tooling, or deciding what to run after a code change — uv (`uv add`, `uv remove`, `uv sync --locked`), ruff (`# noqa`), ty (`ty ignore[<rule>]` comments), complexipy, pytest and pytest-asyncio settings, the coverage gate, prek hooks, CI jobs, and `DeprecationWarning` / `filterwarnings` policy.
---

# Python Tooling

This skill owns the development toolchain of a Python service: the uv workflow, the ruff, ty, complexipy, pytest and coverage configuration that lives in `pyproject.toml`, the prek hook setup, the CI quality job, and what to do about warnings a run produces. The sibling skills describe what to write; every command they mention and every tool setting they rely on is defined here. An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires Python 3.13+, uv, ruff, ty, complexipy, prek, pytest, pytest-asyncio, pytest-cov.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `python-testing`, `postgres-database`, `project-scaffolding`.

Load `reference/setup.md` when you create or change `pyproject.toml`, `.pre-commit-config.yaml`, or the first-time setup of a repository. It carries the complete baseline for all three.

## Commands

The direct commands are the contract. A `Makefile` is a convenience wrapper over them: use the target when the repository already defines one, use the direct command when it does not, and do not add a `Makefile` to a repository that has none just to have the targets.

| Target | Direct command |
|---|---|
| `make lint` | `uv run ruff format` then `uv run ruff check --fix` |
| `make lint-no-format` | `uv run ruff check` |
| `make typecheck` | `uv run ty check` |
| `make complexitycheck` | `uv run complexipy .` |
| `make test` | `uv run pytest` |
| `make test-coverage` | `uv run pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90` |
| `make check` | the four above in order: lint, typecheck, complexitycheck, test-coverage |
| `make run` | `uv run python -m app.main` |

A project with a database adds these; `postgres-database` shows the direct `alembic` commands. They run against the `DATABASE_URL` in `.env`, and `downgrade` drops schema, so point them at the local compose database only, unless the user names another target:

| Target | Direct command |
|---|---|
| `make up-dependencies` | `docker compose up` (add `-d` when you run it from an agent shell; the target itself is foreground) |
| `make migration MSG="add authors"` | `uv run alembic revision --autogenerate -m "add authors"` |
| `make migrate` | `uv run alembic upgrade head` |
| `make upgrade` | `uv run alembic upgrade +1` |
| `make downgrade` | `uv run alembic downgrade -1` |

After changing a Python file, run `uv run ruff format <paths>` and `uv run ruff check --fix <paths>` on the files you changed; run them project-wide only when the repository is already clean or the task is the cleanup. Before opening a pull request, run the whole gate (`make check`), because type errors and complexity findings do not show up in the lint step.

## uv

uv owns the interpreter, the dependency lists in `pyproject.toml`, and `uv.lock`. Run tools through `uv run`, which resolves the project environment on its own: this workflow has no `uv venv` step and no activated virtualenv, so the same command works in a shell, in a hook and in CI.

```bash
uv add httpx                      # runtime dependency
uv add --group dev pytest-cov     # development dependency
uv remove httpx                   # drop a runtime dependency
uv remove --group dev pytest-cov  # drop a development dependency
uv lock --upgrade-package ruff    # move one package to a newer release
uv sync                           # install exactly what the lock file says
```

`uv add` resolves a current compatible version and writes it into both `pyproject.toml` and `uv.lock` in one step, so there is no reason to type a version number by hand. Pin one only for a real constraint — a known-broken release, or a migration the project has not finished — and say which in the same change.

`uv python pin 3.13` writes `.python-version` and is part of first-time setup. Without it uv installs the newest interpreter that satisfies `requires-python`, which is how a project written against the floor ends up running on a newer release.

## ruff

ruff is the formatter, the linter and the import sorter, so black, isort and the flake8 plugins it replaces stay out of the project. The baseline is 120-character lines, single quotes, and the rule families in `reference/setup.md`; `UP` is among them, which is what keeps `type X = ...`, `collections.abc` imports and PEP 696 defaults current on the 3.13 floor. Docstrings are not enforced: no `D` rules are selected, so a `pydocstyle.convention` line would configure a family that never runs.

Suppress a finding on the line it is reported on and name the rule, as in `# noqa: RUF012`. A blanket `# noqa` also silences future findings on that line, and `RUF100` reports either form once the finding is gone, which is the signal to delete the comment rather than keep it.

## ty

`uv run ty check` is the type checker. Suppress a single diagnostic on the line it is reported on, naming the rule. Three comment forms work and one common one does not:

| Comment at the end of the offending line | Suppresses |
|---|---|
| `# ty: ignore[invalid-argument-type]` | yes |
| `# type: ignore` | yes |
| `# type: ignore[ty:invalid-argument-type]` | yes |
| `# type: ignore[arg-type]`, or any other mypy code | no |

The last form is the trap: ty keeps reporting the diagnostic while the comment reads as though it were handled.

The baseline has no `[tool.ty.rules]` block. Turning a rule off project-wide also turns it off in code written later, and it hides ty's own unused-suppression diagnostics, which are what tell you a `# ty: ignore` or `# type: ignore` comment has outlived the problem it was added for.

## pytest and coverage

The baseline `[tool.pytest.ini_options]` is in `reference/setup.md`: `asyncio_mode = "auto"` so async tests need no `@pytest.mark.asyncio`, `addopts = "-ra"` for a compact summary of everything that was not a plain pass, and both pytest-asyncio loop-scope defaults set to `"session"`.

The loop scopes are a house default, not a requirement. Measured on a psycopg-backed suite with session-scoped engine, app and client fixtures and function-scoped tests, it passes with both options set, with only the fixture option, and with neither. Keeping both at `"session"` puts fixtures and their tests on one event loop, which a loop-bound driver such as asyncpg needs, and costs nothing on psycopg.

Coverage comes from `pytest-cov` in the dev group. The gate is `--cov-fail-under=90`, and it only means 90% if `[tool.coverage.report] precision = 2` is set as well — see the gotcha below.

## complexipy

`uv run complexipy .` is part of the gate. It measures cognitive complexity, which is a different number from ruff's `C901` cyclomatic complexity, so the two catch different functions; the baseline sets both limits to 12. A function over the limit gets split into named pieces. Raising the limit is a project-wide decision, not a way past one function.

## Hooks

`prek` is the hook runner. It reads `.pre-commit-config.yaml`, the format's fixed file name, and the `pre-commit` package itself is not installed.

```bash
uv add --group dev prek
uv run prek install
uv run prek run --all-files
```

ruff and ty run as `repo: local` hooks through `uv run`, so hooks use the versions the lock file pins instead of a second set from a hook mirror. The remote hooks repository is pinned with `rev:`; without it the runner has no version to resolve.

## CI

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run complexipy .
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90
```

The test step needs a Docker daemon on the runner for the Postgres testcontainer; GitHub-hosted Ubuntu runners have one. On a runner without it, provide Postgres as a CI service instead.

`--locked` makes a stale `uv.lock` fail the job instead of being rewritten in place, so CI installs what was reviewed. CI verifies formatting even though hooks format locally, because a hook can be skipped with `git commit --no-verify` or missed entirely in a clone where nobody ran `prek install`.

## Warnings

A warning from a run you started is part of the result you report: name the source, quote the message, and say whether your change caused it. Then take one of three routes.

- Fix it when it points at project code: the deprecated call, the moved import, or the dependency that needs upgrading.
- Suppress it narrowly when it comes from a dependency you cannot change. Scope the entry to message, category and module, and put the upstream issue above it.
- Track it when neither is possible now, so the suppression has a removal condition instead of becoming permanent.

```toml
[tool.pytest.ini_options]
filterwarnings = [
    # upstream issue: github.com/org/lib/issues/123 — remove when fixed
    "ignore:The @wait_container_is_ready decorator is deprecated:DeprecationWarning:testcontainers.core.waiting_utils",
]
```

The policy runs in the removal direction too. After a dependency upgrade, an entry that no longer matches any warning is dead configuration that hides the fact that upstream fixed the problem; `uv run pytest -W always` with the block removed shows whether anything still needs it. The entry above is a real example: the deprecation it names disappeared in a later testcontainers release, and the entry was deleted rather than carried forward.

Warnings that predate your change and have nothing to do with it are not yours to clean up in passing. Report them and leave them unless the task says otherwise.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| `pip install` / editing a version by hand in `pyproject.toml` | `uv add <pkg>`, `uv add --group dev <pkg>` | pip writes nothing to the lock file, and a hand-typed version is a guess nobody re-checks |
| `uv venv --python 3.13` and `source .venv/bin/activate` | `uv python pin 3.13`, `uv sync`, then `uv run <tool>` | activation is shell-specific and silently absent in hooks and CI, where `uv run` still works |
| `# type: ignore[assignment]` to quiet ty | `# ty: ignore[<rule>]` on the reported line | mypy codes suppress nothing in ty; the diagnostic stays and the comment hides that |
| Silencing a whole rule in `[tool.ty.rules]` | Suppress the one line, with the rule name | a project-wide override also covers code written after it |
| `filterwarnings = ["ignore::DeprecationWarning"]` | An entry scoped to message, category and module | the broad form also swallows the next warning, which is the one that matters |
| Keeping `filterwarnings` entries after an upgrade | Delete the entries that no longer match | they read as active suppressions and hide that upstream shipped the fix |
| `uv sync` in CI | `uv sync --locked` | a plain sync rewrites a stale lock, so CI tests a resolution nobody reviewed |
| Leaving `ruff format` out of CI because hooks run it | `uv run ruff format --check .` in the CI job | hooks are skippable and are not installed in a fresh clone |

## Gotchas

- `--cov-fail-under=90` passes below 90% unless `[tool.coverage.report] precision = 2` is set: pytest-cov compares `round(total, precision)` against the threshold, and precision defaults to 0. Measured at 89.62% coverage, the run printed `FAIL Required test coverage of 90% not reached` and still exited 0; with `precision = 2` the same run exited 1.
- Coverage of an async SQLAlchemy service is understated without `[tool.coverage.run] concurrency = ["thread", "greenlet"]`. SQLAlchemy runs the driver inside a greenlet and coverage.py stops tracing at the switch, so the statement after every `await session.scalar(...)` — usually the `if row is None:` guard and its `raise` — is reported as missed even when a test covers it. Measured on one suite of 97 tests: 92.17% without the setting and 96.33% with it, and the two service modules went from 88% and 79% to 100% and 95%.
- `unused-ignore-comment` and `unused-type-ignore-comment` are two different ty rules, for stale `# ty: ignore[...]` and stale `# type: ignore[...]` comments respectively. Substituting one for the other produces no `unknown-rule` warning and no effect.
- ty is pre-1.0. An upgrade can add diagnostics to code that checked clean, so move it with `uv lock --upgrade-package ty` on its own rather than inside a wider upgrade, and read the new findings before suppressing them.
- The hook runner needs a git index. Outside a git repository it fails outright with `fatal: not a git repository`; inside one with nothing staged, every hook reports `(no files to check) Skipped` and the run exits 0, which looks identical to success.
- A hook that rewrites files fails the commit it runs on with `- files were modified by this hook`. The fix is to stage the rewritten files and commit again, not to re-run with `--no-verify`.
- `uv add` and `uv remove` both re-lock and re-sync in one step, so a separate `uv sync` after them is redundant; `uv sync` is for a checkout someone else's lock file arrived in.
- ruff derives the target Python version from `requires-python`, so the baseline sets no `target-version`. A second copy of the floor drifts from the first one.
- pytest-asyncio no longer warns about an unset loop-scope default, so a project that dropped both options looks clean until a loop-bound driver is introduced.
