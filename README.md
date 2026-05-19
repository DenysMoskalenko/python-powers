# AI Python Powers

Reusable engineering skills for AI-assisted Python development.

This repository is a shared playbook for humans and coding agents building modern Python services. It captures practical conventions for Python 3.13+, FastAPI, PostgreSQL, testing, tooling, and pydantic-ai so teams can make fewer repeated decisions and get more predictable AI-assisted changes.

The main artifact is the [`skills/`](skills/) directory. Each skill is a focused Markdown guide that an agent can load when working in that domain.

## What's Inside

| Skill | Use it for |
| --- | --- |
| [`python-code-style`](skills/python-code-style/SKILL.md) | Python 3.13+ style, typing, naming, dependency injection, model-first data design, and general architecture rules. |
| [`python-tooling`](skills/python-tooling/SKILL.md) | uv, ruff, ty, pytest configuration, pre-commit hooks, optional Makefile wrappers, and CI quality jobs. |
| [`python-testing`](skills/python-testing/SKILL.md) | FastAPI API-level testing, pytest fixtures, polyfactory factories, dependency overrides, and assertion patterns. |
| [`fastapi-service`](skills/fastapi-service/SKILL.md) | FastAPI routes, services, schemas, settings, exception handling, and dependency wiring without a repository layer. |
| [`postgres-database`](skills/postgres-database/SKILL.md) | PostgreSQL, SQLAlchemy 2.0 async, Alembic migrations, service-owned queries, and testcontainers-backed database tests. |
| [`ai-agents`](skills/ai-agents/SKILL.md) | pydantic-ai agents in FastAPI services, typed dependencies, tools, model registry patterns, provider mapping, and tests. |
| [`skill-writer`](skills/skill-writer/SKILL.md) | House rules for adding, editing, splitting, or reviewing skills in this repository. |

Some skills include additional reference material linked from their main guide.

## How To Use

Use the skills as context for AI-assisted engineering work:

1. Pick the skill that matches the task.
2. Load its `SKILL.md` before editing code or documentation.
3. Load related skills only when their domain is actually involved.
4. Follow the ownership boundaries in each skill instead of mixing unrelated rules into one place.

Typical combinations:

| Task | Skills |
| --- | --- |
| Add or refactor Python application code | `python-code-style` |
| Build a FastAPI endpoint backed by PostgreSQL | `python-code-style`, `fastapi-service`, `postgres-database`, `python-testing` |
| Add an AI assistant endpoint to a service | `python-code-style`, `fastapi-service`, `ai-agents`, `python-testing` |
| Change linting, typing, dependencies, or test commands | `python-tooling` |
| Edit one of this repository's skills | `skill-writer` plus the skill being changed |

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

This repository is importable as a Codex plugin from GitHub. The plugin manifest lives
at [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) and points Codex at the
root [`skills/`](skills/) directory.

In Codex, import this repository URL:

```text
https://github.com/DenysMoskalenko/python-powers
```

After installation, enable **AI Python Powers** and use the skills listed above.

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

## Principles

- Keep guidance reusable across Python services.
- Prefer clear ownership over duplicated rules.
- Use realistic examples that can be adapted into production services.
- Keep skills terse enough for agents to load and follow.
- Put supporting material in `reference/` when it would bloat the main skill.

## Contributing

Changes should improve shared, reusable Python engineering guidance. Good contributions include clearer examples, corrected patterns, reduced overlap between skills, and reference material that supports an existing skill.

Avoid adding app-specific conventions, one-off team workflows, unproven tool recommendations, or claims about CI and release processes that are not represented in this repository.

When changing a skill, read [`skills/skill-writer/SKILL.md`](skills/skill-writer/SKILL.md) first and keep the edit scoped to that skill's ownership.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
