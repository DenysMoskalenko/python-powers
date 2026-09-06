# AI Python Powers

Reusable engineering skills for AI-assisted Python development.

This repository is a shared playbook for humans and coding agents building modern Python services. It captures practical conventions for Python 3.13+, FastAPI, PostgreSQL, testing, tooling, and pydantic-ai so teams can make fewer repeated decisions and get more predictable AI-assisted changes.

The main artifact is the [`skills/`](skills/) directory. Each skill is a focused Markdown guide that an agent can load when working in that domain.

## What's Inside

| Skill | Use it for |
| --- | --- |
| [`python-code-style`](skills/python-code-style/SKILL.md) | Python 3.13+ application and library style: typing, model-first data design, naming, dependency injection, fail-fast discipline, and architecture principles. |
| [`python-tooling`](skills/python-tooling/SKILL.md) | uv workflow, ruff, ty, complexipy, pytest and coverage configuration, prek hooks, direct commands behind the Makefile targets, CI jobs, and the warnings policy. |
| [`python-testing`](skills/python-testing/SKILL.md) | FastAPI API-level testing with httpx2, the app and client fixtures, polyfactory factories, data helpers, dependency-override utilities, assertion patterns, flaky-test triage, and the coverage policy. |
| [`fastapi-service`](skills/fastapi-service/SKILL.md) | FastAPI routes, query-parameter models, PATCH semantics, services, schemas, settings, lifespan, exception handlers, and dependency wiring without a repository layer. |
| [`postgres-database`](skills/postgres-database/SKILL.md) | PostgreSQL 18, SQLAlchemy 2.0 async models and loading strategy, service-owned queries, Alembic migrations, and testcontainers-backed database fixtures. |
| [`ai-agents`](skills/ai-agents/SKILL.md) | pydantic-ai 2.x agents in FastAPI services: typed dependencies, tools, instructions, model registry with FallbackModel, provider error mapping, conversations and streaming, and tests. |
| [`project-scaffolding`](skills/project-scaffolding/SKILL.md) | Generating a brand-new FastAPI service from a pinned BoilerplateBuilder revision with tests, linters, CI, and Docker working from the first commit. Greenfield HTTP services only — not CLIs, libraries, scripts, or features in an existing project. |
| [`skill-writer`](skills/skill-writer/SKILL.md) | House rules for adding, editing, splitting, or reviewing skills in this repository, and for writing their eval cases. |

Some skills include additional reference material linked from their main guide. Every code example comes from a project that passes its quality gate on current library releases; feature modules live in `app/domains/<feature>/`, the layout the scaffolding template generates.

## How To Use

Use the skills as context for AI-assisted engineering work:

1. Pick the skill that matches the task.
2. Load its `SKILL.md` before editing code or documentation.
3. Load related skills only when their domain is actually involved.
4. Follow the ownership boundaries in each skill instead of mixing unrelated rules into one place.

Typical combinations:

| Task | Skills |
| --- | --- |
| Start a brand-new service from scratch | `project-scaffolding` (then the domain skills it hands off to) |
| Add or refactor Python application code | `python-code-style` |
| Build a FastAPI endpoint backed by PostgreSQL | `python-code-style`, `fastapi-service`, `postgres-database`, `python-testing` |
| Add an AI assistant endpoint to a service | `python-code-style`, `fastapi-service`, `ai-agents`, `python-testing` |
| Change linting, typing, dependencies, or test commands | `python-tooling` |
| Edit one of this repository's skills | `skill-writer` plus the skill being changed |

## Evals

`evals/` holds runnable trigger and behaviour cases plus a headless runner (`python3 evals/run_evals.py`) that loads the plugin into a fresh scratch project, checks which skill fired, and grades the code the agent wrote with and without the skill. See [`evals/README.md`](evals/README.md). The human-readable specification behind the cases is [`evals/scenarios.md`](evals/scenarios.md); `uv run evals/check_skills.py` is the static check (frontmatter, line budgets, links, code fences, manifests) and spends no API calls.

## Install As A Claude Code Plugin

The plugin manifest lives at [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json).

**From GitHub:**

```bash
claude plugin marketplace add https://github.com/DenysMoskalenko/python-powers
claude plugin install python-powers@python-powers
```

**Local development:**

```bash
git clone https://github.com/DenysMoskalenko/python-powers
claude plugin marketplace add ./python-powers
claude plugin install python-powers@python-powers
```

After installation, the skills listed above are available to Claude Code via the `Skill` tool.

## Install As A Codex Plugin

This repository is a Codex plugin marketplace. The marketplace file lives at
[`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json), and the
plugin manifest lives at [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json).

**Codex app:**

Open **Plugins**, add this GitHub marketplace, then install and enable
**Python Powers**:

```text
git@github.com:DenysMoskalenko/python-powers.git
```

**Codex CLI:**

```bash
codex plugin marketplace add git@github.com:DenysMoskalenko/python-powers.git
codex plugin add python-powers@python-powers
```

Start a new Codex thread after installation so the skills are loaded.

## Install As A Cursor Plugin

This repository is also importable as a Cursor plugin. The Cursor plugin manifest
lives at [`.cursor-plugin/plugin.json`](.cursor-plugin/plugin.json) and points Cursor
at the root [`skills/`](skills/) directory.

In a Cursor Agent chat, run:

```text
/add-plugin python-powers@https://github.com/DenysMoskalenko/python-powers
```

For local testing, copy or symlink this repository to:

```text
~/.cursor/plugins/local/python-powers
```

Then restart Cursor or run `Developer: Reload Window`.

## Install With The Skills CLI

Any agent that supports the Agent Skills format (Copilot, Gemini CLI, OpenCode, and others) can pull the `skills/` tree directly:

```bash
npx skills add DenysMoskalenko/python-powers
```

## Principles

- Keep guidance reusable across Python services.
- Prefer clear ownership over duplicated rules.
- Use realistic examples that can be adapted into production services.
- Keep skills terse enough for agents to load and follow.
- Put supporting material in `reference/` when it would bloat the main skill.

## Contributing

Changes should improve shared, reusable Python engineering guidance. Good contributions include clearer examples, corrected patterns, reduced overlap between skills, and reference material that supports an existing skill.

Avoid adding app-specific conventions, one-off team workflows, unproven tool recommendations, or claims about CI and release processes that are not represented in this repository.

When changing a skill, read [`skills/skill-writer/SKILL.md`](skills/skill-writer/SKILL.md) first and keep the edit scoped to that skill's ownership. Before opening a pull request run `uv run evals/check_skills.py`, `claude plugin validate .` (which checks only the marketplace manifest), and the eval cases for the touched skill (they spend API calls; see [`evals/README.md`](evals/README.md)).

## License

This project is licensed under the [Apache License 2.0](LICENSE).
