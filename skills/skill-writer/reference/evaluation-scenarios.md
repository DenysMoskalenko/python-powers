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

**Prompt**: "I just changed `app/services/author_service.py`. What should I run?"

**Must produce**:
- `make lint` (or `uv run ruff format . && uv run ruff check --fix .`)
- Mention of `make typecheck` and `make test` before PR
- `make check` before opening a PR

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
- Uses `begin_nested()` around writes
- Raises domain exceptions
- `flush()` so returned data is visible inside the outer transaction

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

---

## ai-agents

### Eval 1 — New agent

**Prompt**: "Define a read-only catalog assistant agent with two tools: count_items, list_items."

**Must produce**:
- `@dataclass(frozen=True, slots=True)` for deps
- `build_catalog_assistant_agent(model: Model)` factory
- `Agent[Deps, Output]` fully typed
- Tools registered with `@agent.tool` inside the builder
- Tool inputs as Pydantic `BaseModel` subclasses
- `retries=0`
- System prompt is rule-based ("Use X for Y")

**Must not produce**:
- Tools that import services directly instead of using `ctx.deps`
- System prompt as a description ("You can use…")
- Global/module-level agent instance

### Eval 2 — Agent as FastAPI dependency

**Prompt**: "Wire the catalog assistant into a POST endpoint."

**Must produce**:
- `get_catalog_assistant_agent` depends on request payload + model registry
- Route injects `Agent[...]` via `Depends(get_catalog_assistant_agent)`
- Service method accepts the agent and calls `agent.run(question, deps=...)`

**Must not produce**:
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
