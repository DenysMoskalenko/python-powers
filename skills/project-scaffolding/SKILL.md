---
name: project-scaffolding
description: Use when starting a brand-new FastAPI service from zero — "create a FastAPI app/API/microservice that…", bootstrapping a fresh repo that needs tests, linters, CI, and Docker working from the first commit. Greenfield services only — not for CLIs, libraries, or adding features to an existing project. For tooling changes in an existing repo see `python-tooling`.
---

# Project Scaffolding (Greenfield Only)

This skill uses Cookiecutter to generate brand-new FastAPI services from the [BoilerplateBuilder template](https://github.com/DenysMoskalenko/BoilerplateBuilder), including app structure, tests, tooling, Docker, and CI. The template ships a project where the test suite, linters, and CI already pass. Infer its inputs from the conversation and briefly identify the builder when describing the scaffold.

> Requires uv (or pip) and network access to `github.com/DenysMoskalenko/BoilerplateBuilder`. Docker is required for DB tests and to run the local telemetry stack.

**Related**: `python-tooling`, `python-testing`, `fastapi-service`, `postgres-database`, `ai-agents`.

For changing tooling, dependencies, or CI in an existing project use `python-tooling`. To add features to an already-scaffolded service use `fastapi-service`, `postgres-database`, or `ai-agents`.

## When to use

This skill applies only at time-zero of a new service — before any `app/`, `pyproject.toml`, or `.git` exists in the target directory.

**Do NOT load for ongoing work.** Adding a route, model, agent, test, or dependency to a project that already exists is owned by the domain skills, never by re-scaffolding. There is no "scaffold a missing piece into an existing repo" path — see [Red Flags](#red-flags--stop).

## Infer the project shape

Pick `project_type` from what the app needs, not by asking the user which variant they want:

| The app needs… | `project_type` | Hands off to |
|---|---|---|
| to persist data (entities, CRUD, a database) | `fastapi_db` | `fastapi-service` + `postgres-database` |
| an LLM / agent / assistant, no persistence | `fastapi_agent` | `fastapi-service` + `ai-agents` |
| both stored data **and** agent behavior | `fastapi_db_agent` | `fastapi-service` + `postgres-database` + `ai-agents` |
| a plain HTTP API (webhook, proxy, compute), no DB, no AI | `fastapi_slim` | `fastapi-service` |

Infer every other input from the conversation too. When a value genuinely forks the result and the conversation doesn't settle it, ask **one domain-level question** ("Should this persist data, or just respond to requests?"). When the user doesn't care, fall back to the baseline:

| Input | Baseline | Override when… |
|---|---|---|
| `python_version` | `3.14` | the user pins a different supported runtime |
| `project_description` | one line describing the service, taken from the conversation | — |
| `author_name`, `author_email` | `git config user.name` / `user.email` | unset — keep the template placeholder and tell the user to fix it |
| `use_github_actions` | `yes` | the user says no CI / hosts elsewhere |
| `initialize_git` | `yes` | the user asks to skip it, the service belongs to an existing repository, or destination rules prohibit automatic commits |
| `use_otel_observability` | `yes` | the user explicitly opts out of telemetry |
| `generate_local_otel_stack` | `yes` | telemetry is disabled or the user opts out of the local Grafana stack |

Check whether the destination is inside an existing repository and follow its Git rules. `initialize_git=yes` initializes Git, stages generated files, and attempts an initial commit.

These tables cover the inputs you normally set. For anything not covered here — an input you're unsure about, an allowed value, or an option-specific detail — read the template directly instead of guessing:

- Inputs and their allowed values: `cookiecutter.json` in [the template repository](https://github.com/DenysMoskalenko/BoilerplateBuilder)
- What each `project_type` ships and how it runs: [the template README](https://github.com/DenysMoskalenko/BoilerplateBuilder)

## Generate the project

Drive Cookiecutter non-interactively, passing every selected input explicitly, including values matching the baseline above. Leave only unspecified inputs to Cookiecutter's defaults:

```bash
uv tool run cookiecutter https://github.com/DenysMoskalenko/BoilerplateBuilder \
  --no-input \
  project_name="Books" \
  project_description="Catalog API for books" \
  author_name="Ada Lovelace" \
  author_email="ada@example.com" \
  project_type=fastapi_db \
  python_version=3.14 \
  use_github_actions=yes \
  initialize_git=yes \
  use_otel_observability=yes \
  generate_local_otel_stack=yes \
  extract_to_current_dir="Create New"
```

- `--no-input` skips interactive prompts. Omitted keys use template defaults, overridden by any Cookiecutter user configuration.
- **Always pass `project_type` explicitly** — the template's own default is the heaviest variant (`fastapi_db_agent`).
- Boolean inputs take the strings `yes` / `no`.
- **Create New vs Extract Here** (`extract_to_current_dir`): the default `Create New` generates a fresh subdirectory named after the project — use it when there is no target directory yet. Pass `extract_to_current_dir="Extract Here"` when the user is already inside the directory the project should fill (they made and opened an empty folder). Either way, only ever generate into an **empty** location — never one that already holds a project.

## After scaffolding

1. `cd` into the generated project and confirm the green baseline **before writing any feature code** — run its quality gate (commands owned by `python-tooling`, typically `make check` or `make test`). If the baseline fails, inspect the failing check, fix its cause, and rerun the checks. Regenerate only when generation was incomplete or the selected inputs were wrong.
2. Continue with the domain skills for the chosen `project_type` (see the hand-off column above). From here on it is ongoing work and this skill steps out.

## Red Flags — STOP

These mean you are misusing the scaffolding workflow. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Hand-assemble `app/`, `pyproject.toml`, Docker, or CI for a new service from scratch | Generate from the template — it ships a green baseline |
| Run the generator inside an existing project to "add structure" or a missing piece | When to use — greenfield only; existing projects are owned by the domain skills |
| Make the user fill out raw generator prompts | Infer the project shape — ask about unresolved project needs |
| Leave `project_type` to the template default | Generate the project — pass it explicitly (the default is the heaviest variant) |
| Extract into a non-empty directory | Generate the project — create a fresh directory; never overwrite an existing tree |
| Re-state ruff / pytest / uv config or `make` commands in this skill | Ownership — `python-tooling` owns tooling; point to it |
| Keep using this skill once the project exists | After scaffolding — hand off to the domain skills; this skill is time-zero only |

## Gotchas

- The template's default `project_type` is `fastapi_db_agent` — set it explicitly so a slim service doesn't inherit a database and an agent it never asked for.
- Inputs are strings: booleans are `yes` / `no`, and `extract_to_current_dir` is `Create New` / `Extract Here` — not `true` / `false`.
- Omitting a key does not apply this skill's baseline — pass selected values explicitly so template defaults or user configuration cannot change the intended result.
- `initialize_git=no` skips Git initialization and the initial commit, but the builder still attempts `prek install`. Inside an existing repository, this can update that repository's hooks.
- The generated project already wires the `python-tooling`, `python-testing`, `fastapi-service` (and `postgres-database` / `ai-agents`) patterns — extend them, don't re-create them.
- A generated scaffold is not verified until its checks pass. Repeating generation with unchanged inputs does not resolve a reproducible failure.
