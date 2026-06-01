---
name: project-scaffolding
description: Use when starting a brand-new Python/FastAPI service from zero — "create an app that…", bootstrapping a fresh repo, or scaffolding a new microservice/API that needs tests, linters, CI, and Docker working from the first commit. Greenfield only; never for adding features to an existing project. For tooling changes in an existing repo see `python-tooling`.
---

# Project Scaffolding (Greenfield Only)

When creating a brand-new service from zero, generate it from the BoilerplateBuilder template instead of hand-assembling the app structure, tests, tooling, Docker, and CI. The template ships a project where the test suite, linters, and CI already pass. Treat the template as an implementation detail — infer its inputs from the conversation so the user never has to know a generator was involved.

> Requires uv (or pip) and network access to `github.com/DenysMoskalenko/BoilerplateBuilder`.

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

Infer every other input from the conversation too. When a value genuinely forks the result and the conversation doesn't settle it, ask **one domain-level question** ("Should this persist data, or just respond to requests?") — never a question about cookiecutter, prompts, or the template by name. When the user doesn't care, fall back to the baseline:

| Input | Baseline | Override when… |
|---|---|---|
| `python_version` | `3.13` | the user pins an older runtime |
| `use_pre_commit` | `yes` | — |
| `use_github_actions` | `yes` | the user says no CI / hosts elsewhere |
| `initialize_git` | `yes` | the user asks to skip it (e.g. a nested service folder that must not own its own `.git`) |
| `use_otel_observability` | `no` | the user mentions tracing, metrics, or observability |
| `generate_local_otel_stack` | `no` | OTEL is on **and** the user wants a local Grafana stack |

These tables cover the inputs you normally set. For anything not covered here — an input you're unsure about, an allowed value, or an option-specific detail — read the template directly instead of guessing:

- Inputs and their allowed values: [`cookiecutter.json`](https://github.com/DenysMoskalenko/BoilerplateBuilder/blob/main/cookiecutter.json)
- What each `project_type` ships and how it runs: [the template README](https://github.com/DenysMoskalenko/BoilerplateBuilder)

Consulting the template is your own research — keep it invisible to the user; never surface its prompts at them (see [Red Flags](#red-flags--stop)).

## Generate the project

Drive the generator non-interactively, passing only the inputs that differ from the baseline you decided:

```bash
uv tool run cookiecutter https://github.com/DenysMoskalenko/BoilerplateBuilder \
  --no-input \
  project_name="Books" \
  project_type=fastapi_db \
  python_version=3.13
```

- `--no-input` skips the interactive prompts and applies the template default for every key you omit.
- **Always pass `project_type` explicitly** — the template's own default is the heaviest variant (`fastapi_db_agent`).
- Boolean inputs take the strings `yes` / `no`.
- **Create New vs Extract Here** (`extract_to_current_dir`): the default `Create New` generates a fresh subdirectory named after the project — use it when there is no target directory yet. Pass `extract_to_current_dir="Extract Here"` when the user is already inside the directory the project should fill (they made and opened an empty folder). Either way, only ever generate into an **empty** location — never one that already holds a project.

## After scaffolding

1. `cd` into the generated project and confirm the green baseline **before writing any feature code** — run its quality gate (commands owned by `python-tooling`, typically `make check` or `make test`). A failing baseline is a generation problem, not your feature's; regenerate rather than patching around it.
2. Continue with the domain skills for the chosen `project_type` (see the hand-off column above). From here on it is ongoing work and this skill steps out.

## Red Flags — STOP

These mean you are scaffolding when you should not, or leaking the generator at the user. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Hand-assemble `app/`, `pyproject.toml`, Docker, or CI for a new service from scratch | Generate from the template — it ships a green baseline |
| Run the generator inside an existing project to "add structure" or a missing piece | When to use — greenfield only; existing projects are owned by the domain skills |
| Ask the user about cookiecutter, prompts, `project_type`, or the template by name | Infer the project shape — keep the generator invisible; ask domain questions only |
| Leave `project_type` to the template default | Generate the project — pass it explicitly (the default is the heaviest variant) |
| Extract into a non-empty directory | Generate the project — create a fresh directory; never overwrite an existing tree |
| Re-state ruff / pytest / uv config or `make` commands in this skill | Ownership — `python-tooling` owns tooling; point to it |
| Keep using this skill once the project exists | After scaffolding — hand off to the domain skills; this skill is time-zero only |

## Gotchas

- The template's default `project_type` is `fastapi_db_agent` — set it explicitly so a slim service doesn't inherit a database and an agent it never asked for.
- Inputs are strings: booleans are `yes` / `no`, and `extract_to_current_dir` is `Create New` / `Extract Here` — not `true` / `false`.
- Under `--no-input` an unconsidered key silently inherits the template default — decide every value before generating, then pass only the ones that differ from baseline.
- The generated project already wires the `python-tooling`, `python-testing`, `fastapi-service` (and `postgres-database` / `ai-agents`) patterns — extend them, don't re-create them.
- A fresh scaffold passes its own test and lint gate immediately; if it doesn't, regenerate rather than debugging a baseline you didn't write.
