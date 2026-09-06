---
name: project-scaffolding
description: Use when starting a new FastAPI HTTP service from scratch — "create a FastAPI app/API/microservice that…", an empty repo that needs tests, linters, CI, and Docker green from the first commit. Greenfield HTTP services only — not for CLIs, libraries, scripts, or features in an existing project. For tooling changes in an existing repo see `python-tooling`.
---

# Project Scaffolding (Greenfield Only)

Generate a new service from a pinned revision of the BoilerplateBuilder cookiecutter template rather than hand-assembling `app/`, tests, tooling, Docker, and CI, because the generated project already passes its own quality gate before any feature code exists. This applies only at time zero of a new service: once the project is there, adding a route, model, agent, test, or dependency belongs to the domain skills, and nothing here scaffolds a missing piece into a repo that already holds a project. An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires uv, git, make, network access to github.com, and a running Docker daemon for fastapi_db / fastapi_db_agent.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `python-tooling`, `python-testing`, `fastapi-service`, `postgres-database`, `ai-agents`.

Ask the user about their domain, not about the template. Before running the generator, name the BoilerplateBuilder revision you will pin and what its post-generation hook does on their machine: `uv lock && uv sync` over the network, `git init` plus an initial commit when `initialize_git=yes`, and `prek install`; with `Extract Here`, also list the files it overwrites (`README.md`, `.gitignore`). Run it once they confirm. That confirmation is not the one domain question below. Afterwards, report the revision you used and the result of the quality gate, so the origin of their code and its verified state are both on the record.

## Choose the project type

If what the user described is not an HTTP service — a CLI, a library, a one-off script, a notebook — this skill does not apply: say so and continue without the template.

Infer `project_type` from what the service has to do:

| The service needs… | `project_type` | Hand off to |
|---|---|---|
| to persist data (entities, CRUD, a database) | `fastapi_db` | `fastapi-service` + `postgres-database` |
| an LLM, agent, or assistant, with no persistence | `fastapi_agent` | `fastapi-service` + `ai-agents` |
| both stored data and agent behaviour | `fastapi_db_agent` | `fastapi-service` + `postgres-database` + `ai-agents` |
| a plain HTTP API — webhook, proxy, compute | `fastapi_slim` | `fastapi-service` |

Ask at most one domain question per scaffold, and only when the conversation leaves the persist/agent axis genuinely open: "Should this service persist data, or only respond to requests?" Every other input has a baseline below, so nothing else is worth a round trip.

## Inputs

Always pass `project_name` and `project_type`. Derive the description and author fields from context, and pass the rest only when they differ from the baseline.

| Input | What to pass |
|---|---|
| `project_name` | a valid distribution name — letters, digits, `_`, `-`, no spaces |
| `project_type` | from the table above, always explicitly |
| `project_description` | one line describing the service, taken from the conversation |
| `author_name`, `author_email` | `git config user.name` and `user.email`; when unset, keep the template placeholder and tell the user to fix it |
| `python_version` | baseline `3.13`, the floor these skills are written against; the template also accepts `3.12` and `3.11` for a caller who pins an older runtime and accepts that examples using PEP 695 syntax no longer apply |
| `use_github_actions` | baseline `yes`; `no` when CI lives elsewhere |
| `initialize_git` | baseline `yes`; `no` when the target directory already has `.git` |
| `use_otel_observability` | baseline `no`; `yes` when the user asks for tracing or metrics |
| `generate_local_otel_stack` | baseline `no`; `yes` only together with `use_otel_observability=yes`, otherwise the hook exits with an error |
| `extract_to_current_dir` | baseline `Create New`, which makes a subdirectory named after the project; `Extract Here` when the user is already inside the directory the project should fill |

Generate only into an empty target, meaning a directory that holds nothing but `.git`. A freshly cloned or `git init`-ed repository qualifies, and there you pass `initialize_git=no`. A directory that already holds `app/`, `pyproject.toml`, or any other project is not a target.

## Generate the project

```bash
uv tool run cookiecutter https://github.com/DenysMoskalenko/BoilerplateBuilder \
  --checkout 492fc9b1e752a761e6a65182626502b8569e8143 \
  --no-input \
  project_name="Books" \
  project_type=fastapi_db \
  project_description="Catalog API for books" \
  author_name="Ada Lovelace" \
  author_email="ada@example.com"
```

- `--checkout` pins the revision this skill was verified against, so the same prompt produces the same project tomorrow. To bump it, regenerate all four project types from the new revision, run `make check` in each, then update the hash here, in `evals/cases.json` (`beh-scaffold-command`), and in `evals/scenarios.md`.
- `--no-input` skips the interactive prompts and applies the template default for every key you omit.
- `-o <dir>` generates into somewhere other than the current directory; with `Extract Here` that directory is the one the project fills.

## After scaffolding

1. Run the quality gate in the project root: `make check`, or the equivalent direct commands from `python-tooling`.
2. When it fails, check the prerequisites before blaming the generator — `uv`, `git`, and `make` on `PATH`, plus a running Docker daemon for the DB types, whose tests start the Postgres container through testcontainers. Once the environment is sound, generate again into a fresh directory and keep the failed one for diagnosis instead of patching or overwriting it.
3. Do not redo first-time setup from `python-tooling`. The hook has already copied `dist.env` to `.env`, run `uv lock && uv sync`, formatted and auto-fixed with ruff, created the initial commit when `initialize_git=yes`, and installed the prek hooks against `.pre-commit-config.yaml`.
4. Replace the sample domains with the real one. `app/domains/examples` (DB types) and `app/domains/examples_agent` (agent types) are disposable reference code; `app/domains/health_checks` stays. On DB types, delete the shipped example model and its `add_example_model` migration under `migrations/versions/`, then generate a fresh initial migration as described in `postgres-database`.
5. Continue with the hand-off skills for the chosen type. The work is ongoing from here and this skill steps out.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| Hand-assembling `app/`, `pyproject.toml`, Docker, and CI for a new service | Generate from the pinned template | The generated baseline already passes lint, type checks, and tests on the first commit |
| Running the generator inside an existing project to add a missing piece | Use the domain skill that owns that piece | The template writes a whole tree and overwrites same-named files, so it damages a project it did not create |
| Omitting `--checkout` | Pin the verified revision | `main` moves, so the same prompt silently starts producing a different project |
| Asking the user about cookiecutter, its prompts, or input names | Ask the one domain question and name the template revision you are about to use | Users can answer product questions, not template mechanics, and provenance belongs in the report rather than the interview |
| A `project_name` containing spaces | Letters, digits, `_`, and `-` only | The name becomes the distribution name, the database user and name, and the image tag; a space breaks `uv lock` inside the hook |
| Writing feature code on a red `make check` | Fix the prerequisites, or regenerate into a fresh directory | A failure at time zero comes from the environment or the template, never from code that does not exist yet |
| Keeping the `examples` / `examples_agent` domains and the example migration | Replace them with the real domain and a fresh initial migration | They are reference code, and the sample migration pins a schema this service does not have |

## Gotchas

- Cookiecutter silently ignores a key that is absent from `cookiecutter.json`, so a typo or a retired input such as `use_pre_commit` looks accepted and changes nothing; values for keys that do exist are validated against their choice list.
- Every input is a string: booleans are `yes` / `no`, and `extract_to_current_dir` is `Create New` / `Extract Here`, not `true` / `false`.
- `Extract Here` overwrites same-named files in the target directory, `README.md` and `.gitignore` included, so a clone that carries either one loses it.
- The template's own default for `project_type` is `fastapi_db_agent`, the heaviest variant, so a slim service inherits a database and an agent whenever the key is omitted.
