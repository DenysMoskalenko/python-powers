# Skill Evaluation Scenarios

Spot-check scenarios for each skill in this repository. Not runnable tests — use them manually when editing a skill to confirm the change still produces the expected behavior, or as QA prompts for a fresh agent session.

## Format

Every scenario is structured as:

```markdown
### Eval <N> — <short descriptor>

**Prompt**: "<exact question to feed the agent>"

**Must produce**:
- <behavior or token the skill should drive>
- <another expected behavior>

**Must not produce**:
- <anti-pattern the skill should prevent>
- <another forbidden output>
```

Guidelines for writing scenarios:

1. **Prompts are verbatim** — copy-pasteable, realistic user wording, not abstract. `"Add GET /v1/authors/{id}"` beats `"Implement an author endpoint"`.
2. **Must-produce lists concrete tokens** (function names, type names, decorators) that would appear in a correct answer. Vague expectations like "good code" are useless.
3. **Must-not-produce calls out the specific anti-pattern** the skill was written to prevent. If you cannot name a specific anti-pattern, the scenario tests nothing.
4. **Aim for 3-4 scenarios per skill** — one success-path scenario plus 2-3 scenarios exercising the skill's core rules.
5. **Update scenarios when editing a skill.** If a skill change would break a scenario, either adjust the change or justify updating the scenario in the diff.

## How to use

- **Before** editing a skill, read the scenarios below for that skill to understand what it was written to enable.
- **After** editing, re-read the scenarios and confirm mentally that the skill still drives the *must-produce* behaviors and still prevents the *must-not-produce* ones.
- For a new skill, add a fresh `## <skill-name>` section at the bottom of this file with 3-4 scenarios written in the format above.

---

## python-code-style

### Eval 1 — Reject `Any` and raw `dict`

**Prompt**: "Write a function that takes a request payload and returns a response dict."

**Must produce**:
- Pydantic `BaseModel` (or `dataclass`/`TypedDict`) for both input and output
- Typed return, no `Any` anywhere
- Descriptive names (not `data`, `info`, `stuff`)

**Must not produce**:
- `def handle(payload: dict[str, Any]) -> dict[str, Any]`
- A function returning an untyped dict

### Eval 2 — No `utils.py`

**Prompt**: "I need a function that formats a user's full name. Where does it live?"

**Must produce**:
- Colocated with the feature that owns `User` (service, schema, or domain module)
- Explicitly refuses `utils.py` / `helpers.py` / `common.py`

**Must not produce**:
- "Put it in `app/utils/strings.py`"

### Eval 3 — Literal vs StrEnum

**Prompt**: "I'm adding sorting with `asc`/`desc` values to one endpoint. Type for the field?"

**Must produce**:
- `Literal['asc', 'desc']` (small, local, single field)
- Rationale: "no iteration needed, single field, two values"

**Must not produce**:
- `str` with runtime validation
- `StrEnum` for only two values used in one place

### Eval 4 — Fail fast

**Prompt**: "This charge function sometimes fails silently. Fix it."

**Must produce**:
- Raises a specific domain exception
- Uses `raise ... from exc` to chain
- Refuses `except Exception: pass`

**Must not produce**:
- Logging and returning `None` on error

### Eval 5 — Inspect context before patching

**Prompt**: "This line is wrong: `if user is not None:`. Change it to `if user is None:`."

**Must produce**:
- Reads the enclosing function/class/module before editing
- Checks relevant callers or tests when the branch meaning is not obvious
- Explains no edit is needed if the quoted line is correct in context

**Must not produce**:
- Patching only the quoted line without inspecting surrounding code
- Assuming the user's proposed replacement is technically correct

---

## python-tooling

### Eval 1 — Adding a dependency

**Prompt**: "Add `structlog` to the project."

**Must produce**:
- `uv add structlog` (latest version resolved automatically)
- No hand-written version number in `pyproject.toml`

**Must not produce**:
- `pip install structlog`
- `uv add structlog==24.1.0` with a guessed version

### Eval 2 — Treating a warning

**Prompt**: "My test run shows a `DeprecationWarning` from an upstream library. What do I do?"

**Must produce**:
- Surface the warning clearly
- Offer: fix / suppress narrowly / track upstream
- If suppressing: scoped `filterwarnings` with message + module + category, plus an upstream issue link

**Must not produce**:
- Broad `filterwarnings = ["ignore::DeprecationWarning"]`

### Eval 3 — Run after every change

**Prompt**: "I just changed `app/modules/authors/service.py`. What should I run?"

**Must produce**:
- `make lint` (or `uv run ruff format . && uv run ruff check --fix .`)
- Mention of `make typecheck` and `make test` before PR
- `make check` before opening a PR

**Must not produce**:
- Full `pyproject.toml` or `.pre-commit-config.yaml` setup snippets

### Eval 4 — Local pre-commit tools

**Prompt**: "Add the baseline pre-commit config for a new Python service."

**Must produce**:
- Use `python-tooling/reference/setup.md` for the baseline setup snippet
- `repo: local` hooks for both `ruff check --fix` and `ruff format`
- Ruff hook entries that run through `uv run`
- Local `ty` hook using `uv run ty check`

**Must not produce**:
- `repo: https://github.com/astral-sh/ruff-pre-commit`

---

## python-testing

### Eval 1 — API test, not unit test

**Prompt**: "Write a test that creates an author and verifies it returns 201."

**Must produce**:
- Test uses `AsyncClient` (HTTP-level)
- Uses `AuthorCreateFactory.build()` for payload
- `response.status_code == 201` and body comparison

**Must not produce**:
- Unit test that mocks `AuthorService` directly
- In-memory SQLite or SQLAlchemy mock

### Eval 2 — Test naming

**Prompt**: "Name the test for 'fails when birthday is in the future'."

**Must produce**:
- `test_fail_future_birthday` (or similar `test_fail_<reason>`)
- Grouped in a `TestAuthorsCreate` class alongside `test_success`

**Must not produce**:
- `test_validation`, `test_bad_input`, `test_case_2`

### Eval 3 — Data factory overrides

**Prompt**: "In a test I need an author named 'Jane' — what's the helper call?"

**Must produce**:
- `await create_test_author(session, first_name='Jane')`
- Helper receives kwargs, forwards as factory overrides

**Must not produce**:
- Hand-built `AuthorCreate(first_name='Jane', last_name='X', birthday=..., description=...)` with every field

---

## fastapi-service

### Eval 1 — New CRUD endpoint

**Prompt**: "Add `GET /v1/authors/{id}` that returns an Author or 404."

**Must produce**:
- Route uses `Annotated[AuthorService, Depends()]` and delegates immediately
- Service raises `NotFoundError` (domain), never `HTTPException`
- Response schema has `ConfigDict(from_attributes=True)`
- Exception handler translates `NotFoundError` → 404

**Must not produce**:
- `raise HTTPException(status_code=404)` inside the service

### Eval 2 — Schema layering

**Prompt**: "Design schemas for an Author domain: create, update, response, list filters."

**Must produce**:
- `_AuthorBase` with shared fields (`min_length`, `max_length`, `examples`)
- `AuthorCreate(_AuthorBase)` with validators
- `AuthorUpdate(AuthorCreate)` (reuse)
- `Author(_AuthorBase)` with `id`, timestamps, `from_attributes=True`
- `AuthorListFilters`, `AuthorListSorting(BaseListSorting)` with `Literal` for `sort_by`

**Must not produce**:
- Flat unordered field list with no inheritance
- Bare `str` for `sort_by`

### Eval 3 — Service internals

**Prompt**: "Write `AuthorService` with `get_author_by_id`, `create_author`, and a private `_validate_author_unique`."

**Must produce**:
- Public methods first, private after
- `session: Annotated[AsyncSession, Depends(get_session)]` constructor
- Simple CRUD writes use the injected session directly
- Raises domain exceptions

**Must not produce**:
- `await self._session.commit()` inside this request-scoped service

### Eval 4 — Module placement

**Prompt**: "Where do the routes, schemas, and service for a new `reviews` feature go?"

**Must produce**:
- `app/modules/reviews/` holding flat `routes.py`, `schemas.py`, `service.py`
- Promote a concern to a subpackage only once it splits into 2+ files (facade `__init__.py`, internal siblings import directly)
- SQLAlchemy models stay centralized in `app/infrastructure/db/models/`

**Must not produce**:
- The feature's routes, schemas, and service split across separate top-level layers instead of one `app/modules/reviews/` slice
- A `services/` or `schemas/` subpackage created for a single file

---

## postgres-database

### Eval 1 — New model

**Prompt**: "Add a `BookModel` with `id`, `title`, `author_id` FK, timestamps."

**Must produce**:
- `Mapped[]` annotations for all columns
- `server_default=func.now()` for timestamps
- Explicit `String(N)` lengths
- Named `UniqueConstraint` in `__table_args__` when needed
- `relationship(..., back_populates=..., passive_deletes=True)` for ORM side

**Must not produce**:
- Pre-SQLAlchemy-2.0 `Column()` syntax
- Integer / string columns without explicit length

### Eval 2 — Migration

**Prompt**: "I added a new column. Generate a migration."

**Must produce**:
- `make migration MSG="..."` (autogenerate)
- Hand-edit only to adjust migration metadata if needed
- Refuse to hand-write the SQL from scratch

**Must not produce**:
- `alembic revision -m "..."` without `--autogenerate`
- Manually authored `op.add_column(...)` calls without running autogenerate first

### Eval 3 — Query with pagination + filtering

**Prompt**: "List authors with optional name filter + pagination."

**Must produce**:
- `select(AuthorModel)` base query
- `_apply_filters(query, filters)` helper extracts filtering
- Pagination via `apaginate(session, query, pagination_params, transformer=lambda rows: TypeAdapter(list[Author]).validate_python(rows, from_attributes=True))`
- Filtering uses `icontains` / `ilike` for case-insensitive text

**Must not produce**:
- `LIMIT/OFFSET` math by hand
- Bare `==` on text fields when case-insensitive matching was asked

### Eval 4 — CRUD write transaction boundary

**Prompt**: "Write `AuthorService.create_author` for a normal POST endpoint backed by SQLAlchemy."

**Must produce**:
- Validate domain invariants, execute `insert(...).returning(AuthorModel)`, and return the response schema
- Let `open_db_session()` or the caller-owned session handle commit/rollback

**Must not produce**:
- `session.commit()` or `session.rollback()` inside this request-scoped CRUD service
- `async with self._session.begin_nested():` wrapping the single-statement write
- Justification framing `begin_nested()` as needed "for test rollback" or "for safety"

### Eval 5 — Paginated list with M2M collection

**Prompt**: "Add a paginated `list_books` endpoint that returns each book with its tags (many-to-many) and its author (many-to-one)."

**Must produce**:
- `select(BookModel)` with `.options(selectinload(BookModel.tags))` for the M2M collection
- `.options(selectinload(BookModel.author))` for the many-to-one — it's a to-one *on a list*, so `selectinload`, not `joinedload`
- Pagination via `apaginate(...)` with a `TypeAdapter` transformer
- Note that `lazy='raise'` would otherwise raise on tag/author access during serialization

**Must not produce**:
- `joinedload(BookModel.tags)` on the M2M (cartesian product / subquery wrap on LIMIT)
- `joinedload(BookModel.author)` on the many-to-one — a to-one across a list is the wide-shared-parent blow-up case; use `selectinload`
- Any reliance on lazy access (no `for tag in book.tags` outside an explicitly loaded query)
- `subqueryload(...)` instead of `selectinload(...)`

### Eval 6 — Diagnose `lazy='raise'` error

**Prompt**: "I'm getting `sqlalchemy.exc.InvalidRequestError: 'BookModel.tags' is not available due to lazy='raise'` when serializing a book in the response."

**Must produce**:
- Diagnose as a missing eager-load in the originating query
- Add `.options(selectinload(BookModel.tags))` to the `select(BookModel)` that fetched the book
- Confirm the rule: every relationship access requires explicit loading at query time

**Must not produce**:
- Suggestion to change `lazy='raise'` to `'select'` / `'raise_on_sql'` / `'joined'` / `'selectin'` on the model
- Workarounds that keep the original query unchanged
- Catching the `InvalidRequestError` and falling back

### Eval 7 — Refuse weakening the model default

**Prompt**: "Can we just drop `lazy='raise'` from the relationships? It's annoying to add `.options(...)` every time."

**Must produce**:
- Refusal grounded in the no-hidden-loads rule
- Restate that `lazy='raise'` exists to surface missing loads at the query site instead of leaking N+1 / `MissingGreenlet` to runtime
- Offer the correct path: keep `lazy='raise'`, add `.options(joinedload(...))` / `.options(selectinload(...))` per query

**Must not produce**:
- Approval of removing or weakening `lazy='raise'`
- Suggestion to set a class-wide eager loader (`lazy='selectin'` / `lazy='joined'`) as the default
- Framing the rule as optional or per-team preference

### Eval 8 — Single-object fetch of a to-one

**Prompt**: "Add `get_book_by_id` that returns the book with its author (many-to-one)."

**Must produce**:
- `select(BookModel)` with `.options(joinedload(BookModel.author))` — a to-one fetched for a single parent is one round-trip, one joined row
- `.filter(BookModel.id == book_id)` and a scalar fetch

**Must not produce**:
- `.options(selectinload(BookModel.author))` here — a single-object to-one fetch gains nothing from the second SELECT, just an extra round-trip
- `.unique()` (no row multiplication on a to-one, so it is not needed)
- Lazy access of `book.author` (would raise under `lazy='raise'`)

---

## ai-agents

### Eval 1 — New agent

**Prompt**: "Define a read-only catalog assistant agent with two tools: count_items, list_items."

**Must produce**:
- Agent as a module `app/modules/catalog_assistant/` (`agents.py`, `prompts.py`, `service.py`, `routes.py`, `schemas/`)
- `@dataclass(frozen=True, slots=True)` for deps in `schemas/schemas_agent.py`
- `build_catalog_assistant_agent(model: Model)` factory in `agents.py`
- `Agent[Deps, Output]` fully typed
- Tools registered with `@agent.tool` inside the builder
- Tool inputs as Pydantic `BaseModel` subclasses
- `retries=0`
- System prompt is rule-based ("Use X for Y")

**Must not produce**:
- The agent's pieces (builder, route, service, schemas) split across separate top-level layers instead of one `app/modules/catalog_assistant/` module
- Tools that import services directly instead of using `ctx.deps`
- System prompt as a description ("You can use…")
- Global/module-level agent instance

### Eval 2 — Agent as FastAPI dependency

**Prompt**: "Wire the catalog assistant into a POST endpoint."

**Must produce**:
- `get_catalog_assistant_agent` and `build_catalog_assistant_agent` both in `app/modules/catalog_assistant/agents.py`
- `get_catalog_assistant_agent` depends on request payload + model registry
- Route injects `Agent[...]` via `Depends(get_catalog_assistant_agent)`
- Service method accepts the agent and calls `agent.run(question, deps=...)`

**Must not produce**:
- Builder/dependency split across separate `builder.py` / `dependencies.py` files
- Agent constructed inside the route
- Service owning the agent as a class attribute

### Eval 3 — Testing

**Prompt**: "Write a happy-path test for the catalog assistant endpoint."

**Must produce**:
- `pytest_configure` sets `ALLOW_MODEL_REQUESTS = False`
- Fixture yields an agent built with `TestModel()`
- `agent.override(model=build_mock_model(CatalogAssistantResponse(answer=...)))` for the specific test
- Assertions on `response.status_code` and `response.json()`

**Must not produce**:
- Test that reaches a real provider
- Hand-rolled `ModelResponse` with index-based output tool lookup

### Eval 4 — Provider error mapping

**Prompt**: "What happens if Bedrock throttles?"

**Must produce**:
- Explicit test that maps `ClientError(ThrottlingException)` → HTTP 429
- Test uses `build_raising_model(exc)` from `reference/testing.md`
- Points to app-level exception handlers as the integration surface

**Must not produce**:
- Patching pydantic-ai internals
- 500 as the default for all provider errors

---

## skill-writer

### Eval 1 — Refuse out-of-scope request

**Prompt**: "Create a new skill in `~/.cursor/skills/` for reviewing PRs."

**Must produce**:
- Explicit refusal: this skill only covers `skills/` in THIS repository
- Pointer to use the appropriate Cursor skill-authoring guide instead

**Must not produce**:
- Creating files in `~/.cursor/skills/`
- Applying this skill's house style to a foreign skill system

### Eval 2 — Reject a too-narrow new skill

**Prompt**: "Add a skill for setting up pytest-asyncio correctly."

**Must produce**:
- Observation that the scope fits inside `python-tooling` (pytest config section) or `python-testing`
- Concrete proposal to extend one of those skills instead of creating a new skill
- Rationale: fewer than 3 distinct triggers for a standalone skill

**Must not produce**:
- Creating `skills/pytest-asyncio-setup/SKILL.md` as a standalone skill

### Eval 3 — Description that summarizes workflow

**Prompt**: "Write a description for a new redis-caching skill: 'Use to set up Redis caching by declaring a RedisClient dependency, adding a get_cache/set_cache pattern, and wiring expiration policies.'"

**Must produce**:
- Rejection: the description summarizes the workflow; agent will follow the description and skip the body
- Rewritten description starting with "Use when…", listing triggers (cache layer, TTL/expiration, cache invalidation, eviction policy)
- A disambiguation clause ONLY if a sibling skill could be confused (e.g., `For Redis-backed sessions see \`redis-sessions\``); otherwise no clause

**Must not produce**:
- Keeping the workflow-summary form as-is
- Adding a `compatibility:` frontmatter field in the rewrite
- Adding a "Does not cover Redis sessions, queues, or general key-value stores" line when no sibling Redis skill exists (the name + topics already exclude them — dead-weight tax on every discovery decision)

### Eval 4 — Oversized SKILL.md

**Prompt**: "The new ai-agents SKILL.md is 420 lines. What should I do?"

**Must produce**:
- Identify the largest cohesive block (testing patterns, providers, or advanced examples)
- Move it to `skills/ai-agents/reference/<topic>.md`
- Leave a one-line pointer from `SKILL.md`
- Target ≤ 300 lines in the main file

**Must not produce**:
- Inlining content more tightly to stay under the limit without splitting
- Adding a second SKILL.md under a subfolder

### Eval 5 — Dead-weight exclusions in description

**Prompt**: "Review this description: `Use when working with PostgreSQL via SQLAlchemy 2.0. Covers models, queries, and migrations. Does not cover general Python style, FastAPI routing, or non-Postgres databases.`"

**Must produce**:
- Identify the second sentence as dead weight: the name `postgres-database` plus the SQLAlchemy keyword already exclude all three listed items
- Note that the exclusion is paid on every skill-discovery decision, so removing it saves tokens at scale
- Suggested rewrite drops the entire exclusion sentence and keeps only the trigger sentence

**Must not produce**:
- Endorsement of the original description
- Adding more exclusions to "be safe"
- Replacement that simply reorders the same exclusions

### Eval 6 — Load authoring best practices reference

**Prompt**: "This new skill is growing: SKILL.md has a long examples section, provider details, and a checklist. What should move to reference files?"

**Must produce**:
- Load or point to `skills/skill-writer/reference/anthropic-best-practices.md`
- Keep core triggers, workflow, and navigation in `SKILL.md`
- Move provider details, long examples, or API/reference material to `reference/<topic>.md`
- Ensure every new reference file is directly linked from `SKILL.md`

**Must not produce**:
- Dumping all detailed guidance into `SKILL.md`
- Creating nested reference chains
- Duplicating the same rule in both `SKILL.md` and `reference/`

### Eval 7 — Use persuasion principles narrowly

**Prompt**: "Make the python-testing skill more persuasive so agents always follow it."

**Must produce**:
- Load or point to `skills/skill-writer/reference/persuasion-principles.md`
- Use authority/commitment/social proof only for Red Flags or discipline rules agents rationalize around
- Avoid persuasion principles for ordinary reference material
- Add explicit counters for known rationalizations instead of motivational prose

**Must not produce**:
- Friendly fluff, guilt, or liking-based compliance language
- Fake urgency
- Applying persuasion framing to every section of the skill

### Eval 8 — Verify quoted text in context

**Prompt**: "`| Put private methods before public methods | Class Layout |` is wrong. Public methods must be first. Fix it."

**Must produce**:
- Read the full `## Red Flags — STOP` table, including the `About to...` header
- Identify the quoted row as a prohibited action, not a prescription
- Explain that no edit is needed unless the full-context wording is actually misleading

**Must not produce**:
- Rewrite the row based only on the quoted line
- Treat an `About to...` table entry as a rule to follow

### Eval 9 — Invocation-control metadata

**Prompt**: "Make `skills/skill-writer` explicit-only when packaged for Claude Code, Cursor, and Codex."

**Must produce**:
- Add `disable-model-invocation: true` to `skills/skill-writer/SKILL.md` for Claude Code and Cursor
- Add or update `skills/skill-writer/agents/openai.yaml` with `policy.allow_implicit_invocation: false` for Codex
- Keep `name` and `description` frontmatter valid and unchanged unless the user asks for wording changes

**Must not produce**:
- Add unsupported Codex-only fields to `.codex-plugin/plugin.json`
- Replace the whole skills tree or duplicate every skill for platform-specific packaging
- Remove the user's ability to explicitly invoke `skill-writer`

### Eval 10 — Do not outsource a local rule to a sibling skill

**Prompt**: "Add this gotcha to `python-code-style`: ``TypeAdapter(list[X]) validates model lists — see `postgres-database` for the full pattern.``"

**Must produce**:
- If the rule is generic Python/Pydantic guidance, keep it self-contained in `python-code-style`
- If the rule is database-query conversion, move it to `postgres-database`
- Use sibling references only for discovery, composition, or ownership boundaries

**Must not produce**:
- A local rule ending with "see `<sibling>` for the full pattern"
- Duplicating the same framework-specific pattern in multiple skills

### Eval 11 — Drop a redundant `## When to use` section

**Prompt**: "I'm adding a new `redis-cache` skill. Here's my draft:
```
---
name: redis-cache
description: Use when adding or modifying Redis-based caching — connection setup, cache key design, TTL policies, invalidation, or testing cache layers.
---

# Redis Cache Patterns

...overview...

## When to use

Load this skill when:
- Adding or modifying Redis caching
- Designing cache keys or TTL policies
- Setting up cache invalidation
- Testing cache layers

## Connection setup
...
```
Review it."

**Must produce**:
- Flag the `## When to use` block as redundant — it paraphrases the description in bullets and the loader only sees the description
- Recommend dropping the section entirely (or keeping only "Do not load for:" exclusions / sub-triggers the description cannot fit)
- Note that a one-line sibling pointer ("For X use `<sibling>`") belongs under the overview, not its own section
- Keep the description as the single trigger surface

**Must not produce**:
- Approval of the `## When to use` bullet list as-is
- A suggestion to "make the When to use section more detailed" or "add more triggers there"
- Treating `## When to use` as a mandatory skeleton element

---

## project-scaffolding

### Eval 1 — Greenfield: infer and scaffold

**Prompt**: "Build me an app that serves a catalog of books with search and CRUD."

**Must produce**:
- Recognizes a from-zero project → generates from the BoilerplateBuilder template
- Infers `project_type=fastapi_db` (the app persists data)
- `uv tool run cookiecutter https://github.com/DenysMoskalenko/BoilerplateBuilder --no-input ... project_type=fastapi_db` with `project_type` passed explicitly
- Baseline inputs left at default (Python 3.13, pre-commit + GitHub Actions on, OTEL off)
- After generation: verify the green baseline (`make check` / `make test`), then hand off to `fastapi-service` + `postgres-database`

**Must not produce**:
- Hand-assembling `app/`, `pyproject.toml`, Docker, or CI from scratch
- Asking the user which cookiecutter `project_type` to pick or naming the template at them
- Leaving `project_type` at the template default (`fastapi_db_agent`)

### Eval 2 — Ongoing work: do not scaffold

**Prompt**: "Add a `GET /v1/books/{id}` endpoint to my service."

**Must produce**:
- Does NOT run the template or re-scaffold — the project already exists (ongoing work)
- Routes the work to `fastapi-service` (plus `postgres-database` if DB-backed)

**Must not produce**:
- `cookiecutter` / generating structure into the existing repo
- Treating "add an endpoint" as a greenfield trigger

### Eval 3 — DB + AI inference

**Prompt**: "I want an assistant that answers questions about our orders and remembers past conversations."

**Must produce**:
- Infers `project_type=fastapi_db_agent` (stored data **and** agent behavior)
- Hand-off to `fastapi-service` + `postgres-database` + `ai-agents`

**Must not produce**:
- `fastapi_agent` (drops the persistence the prompt requires) or `fastapi_slim`
- Asking the user to choose the variant by its cookiecutter name

### Eval 4 — Invisible boilerplate, minimal questioning

**Prompt**: "Spin up a tiny webhook receiver service, no database, nothing fancy."

**Must produce**:
- Infers `project_type=fastapi_slim`, passed explicitly in the command
- Uses baseline defaults (Python 3.13, pre-commit + CI on, OTEL off) without quizzing the user about individual prompts

**Must not produce**:
- Interrogating the user about Python version / pre-commit / OTEL after they said "nothing fancy"
- `fastapi_db` / `fastapi_db_agent` for a service that explicitly needs no database
- Exposing cookiecutter mechanics or the template name to the user

### Eval 5 — Generate into the current empty directory

**Prompt**: "I just made an empty folder `orders-svc` and I'm in it — set up a new orders API with a database right here."

**Must produce**:
- Infers `project_type=fastapi_db` and passes it explicitly
- `extract_to_current_dir="Extract Here"` so the project fills the current empty directory rather than nesting a subdir
- `--no-input` invocation

**Must not produce**:
- The default `Create New`, which would nest the project at `orders-svc/orders-svc`
- Generating into a directory that already holds a project
- Asking the user about the `extract_to_current_dir` prompt by name
