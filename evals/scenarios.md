# Skill Evaluation Scenarios

The human-readable specification of what each skill in this repository must drive; the authoring rules it serves live in `skills/skill-writer/SKILL.md`. The runnable counterpart is `evals/cases.json`, executed by `evals/run_evals.py`, and is a subset of this file; a scenario changed here needs the matching case changed there. Read a skill's scenarios before editing it, and use them as QA prompts for a fresh agent session afterwards.

## Contents

[Format](#format) · [How to use](#how-to-use) · [python-code-style](#python-code-style) · [python-tooling](#python-tooling) · [python-testing](#python-testing) · [fastapi-service](#fastapi-service) · [postgres-database](#postgres-database) · [ai-agents](#ai-agents) · [skill-writer](#skill-writer) · [project-scaffolding](#project-scaffolding)

## Format

Every scenario is structured as:

```markdown
### Eval <N> — <short descriptor>

**Prompt**: "<exact question to feed the agent>"

**Must produce**:
- <token or artifact the skill should drive>

**Must not produce**:
- <anti-pattern the skill should prevent>
```

1. **Prompts are verbatim** — copy-pasteable, realistic user wording. `"Add GET /v1/books/{book_id}"` beats `"Implement a book endpoint"`.
2. **Both lists name artifacts**: tokens in written files, code fences, or commands. An expectation phrased as "explains that…", "refuses to…", or "recommends…" grades prose and tests nothing.
3. **Must-produce tokens exist in the owning skill.** When a token is not in the skill text, either the skill or the scenario is wrong.
4. **Must-not-produce names one specific anti-pattern** the skill was written to prevent. How many scenarios a skill carries is set in `skills/skill-writer/SKILL.md` (Creating a skill, step 4): the success path plus the rules added after an agent got them wrong.
5. **Update the scenario and `evals/cases.json` in the same change** when a skill's behaviour changes.

### Triggering blocks

Each skill section starts with a `### Triggering` block that tests discovery — does the right skill load for a prompt? — separate from the behaviour evals, which test what an already-loaded skill drives:

```markdown
### Triggering

**Should load**:
- "<realistic prompt — include casual phrasing and pasted error text>"

**Should not load**:
- "<near-miss prompt>" → `<owning-skill>`
```

1. Should-load prompts (count per `skills/skill-writer/SKILL.md`): at least one with no skill-name keywords, and one pasted error message where the skill owns the diagnosis.
2. Should-not-load prompts (count in the same place), each a plausible near-miss owned by a sibling — always name the owner.
3. Trigger scenarios exercise only the frontmatter `description`; re-check the block whenever a description changes.

## How to use

- Before editing a skill, read its scenarios; after editing, re-read them and run the matching cases: `python3 evals/run_evals.py --only <case-name>`.
- For a new skill, add a `## <skill-name>` section here and its cases in `evals/cases.json` in the same change.

---

## python-code-style

### Triggering

**Should load**:
- "Refactor this service, it's gotten messy" (any Python code change)
- "Review this module for code quality"
- "Is `dict[str, Any]` fine for this payload?"
- "Write a function that merges these two config objects"

**Should not load**:
- "Change the ruff config to 120-char lines" → `python-tooling` (no application code is written)
- "Write the README for this service" → no skill (prose, not Python code)

### Eval 1 — Reject `Any` and raw `dict`

**Prompt**: "Write a function that takes a request payload and returns a response dict."

**Must produce**:
- A pydantic `BaseModel` for the input and one for the output, both named in the signature, with `Field(...)` constraints on the input fields

**Must not produce**:
- `dict[str, Any]` in an annotation, or `Any` anywhere outside an untyped third-party boundary

### Eval 2 — `object` for a pass-through value

**Prompt**: "Add equality to this frozen dataclass, plus a small in-process cache keyed by whatever the caller passes."

**Must produce**:
- `def __eq__(self, other: object) -> bool` narrowing with `isinstance` before use
- `object` for the cache key parameter

**Must not produce**:
- `Any` on either signature
- `object` standing in for a collaborator whose interface is known (that case is a `Protocol` or a type parameter)

### Eval 3 — No `utils.py`

**Prompt**: "Three domains each need to slugify a title. Where does the function live?"

**Must produce**:
- A module named after the concept — `app/core/slug.py`, or the module that owns the type — holding `def slugify(value: str) -> str`

**Must not produce**:
- `utils.py`, `helpers.py`, `common.py`, or `shared.py` anywhere in the path

### Eval 4 — `Literal` vs `StrEnum`

**Prompt**: "I'm adding sorting with `asc`/`desc` values to one endpoint. Type for the field?"

**Must produce**:
- `type SortingOrder = Literal['asc', 'desc']`, because the values are local to one field or alias
- The `StrEnum` case named as the opposite: reused across modules, iterated over, or more than about three values

**Must not produce**:
- A bare `str` with a runtime check
- `StrEnum` for two values used in one place

### Eval 5 — Fail fast

**Prompt**: "This charge function logs and returns `None` when the gateway rejects a card. Fix it."

**Must produce**:
- A `*Error` class subclassing the service's base error, raised where the invariant breaks
- `raise ... from exc` chaining the original exception

**Must not produce**:
- `except Exception: pass`, an except branch that logs and returns `None`, or a bare `ValueError` where callers must tell causes apart

### Eval 6 — Constructor injection in plain Python

**Prompt**: "Write a `ReportService` that renders a report from stored rows and stamps it with the current time. No framework in this module."

**Must produce**:
- Collaborators as `__init__` parameters stored on `self._storage` and `self._clock`
- Body ordered `__init__`, public methods, then private helpers

**Must not produce**:
- `datetime.now()` called inside the method, or any collaborator constructed in `__init__`
- `Depends(` or a FastAPI import in a module the prompt said is framework-free

### Eval 7 — Reuse before creating, no speculative seam

**Prompt**: "Add a reader for our CSV export, plus a `Parser` interface so we can add JSON later."

**Must produce**:
- `import csv` from the standard library and one concrete reader

**Must not produce**:
- A new dependency (`pandas`, `petl`) for reading a CSV
- A `Protocol` or ABC with a single implementation, or a factory for one product

### Eval 8 — Inspect context before patching

**Prompt**: "This line is wrong: `if user is not None:`. Change it to `if user is None:`."

**Must produce**:
- No diff when the branch is already correct in its surroundings
- Otherwise a diff that also covers what the branch feeds — callers and tests included

**Must not produce**:
- An edit to the quoted line alone, made without opening the enclosing function

---

## python-tooling

### Triggering

**Should load**:
- "Add structlog to the project"
- "Remove `requests` from the project"
- "I just changed a service file — what should I run?"
- "pytest prints a `DeprecationWarning` from testcontainers — what do we do with it?"
- "Replace black and isort with ruff"
- "How do I add a Makefile target that runs ty type checking through uv?"

**Should not load**:
- "Create a brand-new FastAPI service with tests and CI" → `project-scaffolding` (greenfield owns the whole baseline)
- "Write tests for the books endpoint" → `python-testing`
- "My test suite needs a Postgres container" → `postgres-database`

### Eval 1 — Adding a dependency

**Prompt**: "Add `structlog` to the project."

**Must produce**:
- `uv add structlog`, which resolves a current compatible version into both `pyproject.toml` and `uv.lock`

**Must not produce**:
- `pip install structlog`, or a hand-typed version such as `structlog==24.1.0`
- A separate `uv sync` afterwards

### Eval 2 — Removing a dependency

**Prompt**: "We deleted the last import of `requests` from the app. Remove the dependency from the project and give me the exact commands to run afterwards."

**Must produce**:
- `uv remove requests` (`uv remove --group dev <pkg>` for a development dependency)
- `uv run ruff format` and `uv run ruff check --fix` on the changed files (or `make lint` where the repository ships the wrapper)

**Must not produce**:
- The line deleted from `pyproject.toml` by hand, or `pip uninstall`
- A follow-up `uv sync`, which `uv remove` has already done

### Eval 3 — What to run after a change

**Prompt**: "I just changed `app/domains/books/service.py`. What should I run?"

**Must produce**:
- `uv run ruff format` then `uv run ruff check --fix` (or `make lint` where a Makefile exists)
- `make check` before the pull request — lint, typecheck, complexitycheck, test-coverage

**Must not produce**:
- A full `pyproject.toml` or `.pre-commit-config.yaml` setup snippet for a one-file change

### Eval 4 — Baseline pytest and hook config

**Prompt**: "Add the baseline pytest configuration and pre-commit config for a new Python service."

**Must produce**:
- `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`, `asyncio_default_test_loop_scope = "session"`, `addopts = "-ra"`, `[tool.coverage.run] concurrency = ["thread", "greenlet"]`, and `[tool.coverage.report] precision = 2`
- `.pre-commit-config.yaml` with `rev: v6.0.0` on the pre-commit-hooks repo and `repo: local` hooks running `uv run ruff check --fix`, `uv run ruff format`, and `uv run ty check` with `pass_filenames: false`; installed with `uv run prek install`

**Must not produce**:
- `repo: https://github.com/astral-sh/ruff-pre-commit`, a remote repo with no `rev:`, or the `pre-commit` package in the dev group

### Eval 5 — Coverage gate that lets 89% through

**Prompt**: "CI printed `FAIL Required test coverage of 90% not reached. Total coverage: 89.62%` and still exited 0. Why?"

**Must produce**:
- `[tool.coverage.report] precision = 2` added, because pytest-cov compares `round(total, precision)` and precision defaults to 0

**Must not produce**:
- `--cov-fail-under` lowered, or a wrapper script that re-parses the coverage output

### Eval 6 — Suppressing a ty diagnostic

**Prompt**: "`# type: ignore[arg-type]` doesn't silence this ty error. Fix it."

**Must produce**:
- `# ty: ignore[invalid-argument-type]` at the end of the reported line (a bare `# type: ignore` also works)
- The stale-comment rule named correctly where one is referenced: `unused-ignore-comment` for `# ty: ignore`, `unused-type-ignore-comment` for `# type: ignore`

**Must not produce**:
- Any mypy code inside `# type: ignore[...]`, which ty ignores while the diagnostic stays
- A `[tool.ty.rules]` block turning the rule off project-wide

### Eval 7 — Treating a warning

**Prompt**: "My test run shows a `DeprecationWarning` from testcontainers. What do I do?"

**Must produce**:
- A `filterwarnings` entry scoped to message, category and module, with the upstream issue link above it

**Must not produce**:
- `filterwarnings = ["ignore::DeprecationWarning"]`
- An entry kept after the upgrade that fixed it upstream

---

## python-testing

### Triggering

**Should load**:
- "Write tests for the new books endpoint"
- "This test fails every third run — make it stable" (flaky)
- "Add a factory for the `BookCreate` schema"
- "How do I override `get_settings` in one test?"

**Should not load**:
- "Set up the testcontainers Postgres fixture" → `postgres-database`
- "Mock the LLM so agent tests don't hit the provider" → `ai-agents`
- "Change the pytest config in `pyproject.toml`" → `python-tooling`
- "Add pytest-cov and wire the 90% coverage gate into `pyproject.toml` and the CI job" → `python-tooling` (the floor is policy here; the gate, the command and the config are there)

### Eval 1 — API test, not unit test

**Prompt**: "Write a test that creates a book and verifies it returns 201."

**Must produce**:
- `from httpx2 import ASGITransport, AsyncClient`, the request driven through the session-scoped `client` fixture, with `session: AsyncSession` in the test signature
- `BookCreateFactory.build(author_id=author.id)`, `json=payload.model_dump(mode='json')`, then the body compared with the payload plus the server-generated `id`, `created_at`, `updated_at`

**Must not produce**:
- `TestClient(`, `from httpx import`, SQLite, or a mocked `BookService`
- `assert Book.model_validate(response.json())` as the whole body check

### Eval 2 — Test naming and deliberately invalid payloads

**Prompt**: "Name and write the test for 'POST /v1/books fails when published_year is 3000'."

**Must produce**:
- `test_fail_unreal_published_year` in a `TestBooksCreate` class next to `test_success`
- The invalid payload built with `BookCreateFactory.build(factory_use_construct=True, published_year=3000)`

**Must not produce**:
- `test_validation`, `test_bad_input`, or `test_case_2`
- `__check_model__ = False`, or a spelled-out `factory_use_construct=False`

### Eval 3 — Data helper overrides

**Prompt**: "In a test I need an author named 'Jane Austen' and one of her books. What are the helper calls?"

**Must produce**:
- `await create_test_author(session, name='Jane Austen')` and `await create_test_book(session, author.id, title='Tehanu')`
- Overrides typed with a `TypedDict` plus `Unpack` signature on the helper

**Must not produce**:
- A hand-built `BookCreate(title=..., published_year=..., author_id=...)` spelling out every field
- A `flush()` after the helper, which `insert(...).returning(...)` has already made unnecessary

### Eval 4 — Override `get_settings` for one test

**Prompt**: "One test needs `PROJECT_VERSION` to be `9.9.9`. How?"

**Must produce**:
- `get_settings().model_copy(update={'PROJECT_VERSION': '9.9.9'})` installed with `temporary_override(app, get_settings, lambda: settings)` around the request

**Must not produce**:
- `monkeypatch.setenv` plus `get_settings.cache_clear()`
- An override installed with no restore, on an app fixture shared by the whole session

### Eval 5 — Missing `session` fixture

**Prompt**: "`await client.post('/v1/books', ...)` raises `RuntimeError: Database access without the 'session' fixture` inside the test. What's wrong?"

**Must produce**:
- `session: AsyncSession` added to the test signature; the `session_fixture_not_requested` sentinel stays installed by `override_app_test_dependencies`

**Must not produce**:
- The sentinel replaced with a placeholder object or a no-op override, or `ASGITransport(app=app, raise_app_exceptions=False)` used to swallow the raise

### Eval 6 — Misspelled factory field

**Prompt**: "Our `BookCreateFactory` sets `titel = 'oops'` and nothing ever fails. Why?"

**Must produce**:
- The field declared through polyfactory — `title = Use(lambda: ...)` — so `__check_model__` raises `ConfigurationException` at import time

**Must not produce**:
- `__check_model__ = False`
- The plain misspelled class attribute left in place

---

## fastapi-service

### Triggering

**Should load**:
- "Add `GET /v1/books/{book_id}` returning 404 when missing"
- "Where does validation for book creation belong?"
- "Add a new setting for the webhook secret"
- "Design request/response schemas for the orders feature"
- "Every request to my list endpoint answers 422 with `Field required`"

**Should not load**:
- "Add a `BookModel` with a foreign key to authors" → `postgres-database`
- "Add a new dependency and tweak the ruff config" → `python-tooling`
- "Start a brand-new orders service" → `project-scaffolding`
- "Our assistant endpoint answers 500 whenever the model provider rate-limits us — what should it return?" → `ai-agents`

### Eval 1 — New CRUD endpoint

**Prompt**: "Add `GET /v1/books/{book_id}` that returns a Book or 404."

**Must produce**:
- Route taking `service: Annotated[BookService, Depends()]` and returning the single service call
- Service raising `NotFoundError(f'Book(id={book_id}) not found')`, and a response schema carrying `ConfigDict(from_attributes=True)`

**Must not produce**:
- `raise HTTPException(` below the route layer
- An ORM object returned from the route or the service

### Eval 2 — Exception handler wiring

**Prompt**: "Wire `NotFoundError` to 404 and `AlreadyExistError` to 409."

**Must produce**:
- Handlers in `app/core/exception_handlers.py` that build an `HTTPException` and `return await http_exception_handler(request, http_exception)`
- Both collected in `EXCEPTION_HANDLERS` and passed as `FastAPI(exception_handlers=EXCEPTION_HANDLERS)`, registered on any mounted sub-application too, since it writes its own 500 otherwise

**Must not produce**:
- `raise HTTPException` inside the handler, which costs a `cast`, a `NoReturn`, and an unused-argument suppression
- Handlers registered "last" so they wrap the routers

### Eval 3 — Schema layering

**Prompt**: "Design the schemas for the books domain: create, patch, response, list filters and sorting."

**Must produce**:
- `_BookBase` with the shared fields (`min_length`, `max_length`, `examples`), `BookCreate(_BookBase)`, an all-optional `BookPatch(BaseModel)`, and `Book(_BookBase)` with `ConfigDict(from_attributes=True)`
- In `BookPatch`, a field on a NOT NULL column keeping the column's type with `default=None` — `title: str = Field(  # ty: ignore[invalid-assignment]` with `default=None, ...` on the next line — and a field on a nullable column as `T | None`
- `BookListFilters` and `BookListSorting(BaseListSorting)` from `app/core/schemas.py`, with a `Literal` `sort_by`

**Must not produce**:
- `BookPatch(BookCreate)` or `BookUpdate(BookCreate)` reused for PATCH
- `title: str | None` on the patch field of a NOT NULL column, which lets `{"title": null}` reach `UPDATE … SET title = NULL`
- A bare `str` for `sort_by`

### Eval 4 — PATCH semantics

**Prompt**: "PATCH /v1/books/{book_id} wipes the fields the client left out. Fix it."

**Must produce**:
- `updates.model_dump(exclude_unset=True)` in the service
- An early return of the current row when nothing was set

**Must not produce**:
- `model_dump()` without `exclude_unset`
- `update(...).values()` issued with an empty mapping

### Eval 5 — Query-parameter models

**Prompt**: "The books list endpoint takes filters (including `ids: list[int]`), a sorting model, and pagination. Write the route."

**Must produce**:
- `filters: Annotated[BookListFilters, Query()]` as the route's only query parameter — the one model carrying the `list[...]` field
- `sorting: Annotated[BookListSorting, Depends()]` and `pagination_params: Annotated[Params, Depends()]`, the sub-dependencies that leave runtime parsing intact
- On a route whose filters model has no `list[...]` field, `Annotated[<Entity>ListFilters, Depends()]` instead, so `/docs` renders each filter as its own parameter

**Must not produce**:
- Any second query parameter beside the `Query()` model — another `Query()` model or a bare scalar such as `limit: int = 10` — which stops the expansion so every request answers 422
- `Depends()` on the model holding the `list[...]` field, which moves it into the body and leaves the query values `None`
- Two list-carrying models on one route instead of one merged filters model

### Eval 6 — Service internals

**Prompt**: "Write `BookService` with `get_book_by_id`, `create_book`, and a private `_validate_book_unique`."

**Must produce**:
- `def __init__(self, session: Annotated[AsyncSession, Depends(get_session)]) -> None`, public methods before private ones
- Domain exceptions raised — `create_book` looks the author up first and raises `NotFoundError(f'Author(id={creation.author_id}) not found')` — and a tolerated case logged as `_logger.info(f'...', extra={'extra': {...}})`

**Must not produce**:
- `await self._session.commit()` or `rollback()` in a request-scoped service
- A repository or DAO layer between the service and the session

### Eval 7 — Feature placement

**Prompt**: "Where do the routes, schemas, and service for a new `reviews` feature go?"

**Must produce**:
- `app/domains/reviews/` holding flat `routes.py`, `schemas.py`, `service.py`
- A subpackage only once a concern splits into two files, with `__init__.py` as the facade and names such as `service_reviews.py`

**Must not produce**:
- The feature split across top-level `routes/`, `schemas/`, `services/`, or the SQLAlchemy model moved out of `app/infrastructure/db/models/`

---

## postgres-database

### Triggering

**Should load**:
- "Add a `BookModel` with `title`, `author_id` FK, timestamps"
- "Generate a migration for the new column"
- "alembic autogenerate produced an empty migration even though I added a new model, why?"
- "I'm getting `sqlalchemy.exc.MissingGreenlet` when the response serializes"
- "`InvalidRequestError: 'BookModel.cover' is not available due to lazy='raise'`"
- "The books list endpoint fires dozens of queries (N+1)"

**Should not load**:
- "Add the route and schemas for books" → `fastapi-service`
- "Write the HTTP-level test for the books list" → `python-testing`
- "Add a polyfactory factory for `BookCreate`" → `python-testing`
- "Rewrite this SQL query to use a window function instead of a subquery" → no skill (plain SQL; no SQLAlchemy model, query, or migration changes)

### Eval 1 — New model

**Prompt**: "Add a `BookModel` with `id`, `title`, `published_year`, an `author_id` FK and timestamps, unique on (title, author_id, published_year)."

**Must produce**:
- `Mapped[...] = mapped_column(...)` for every column, `String(256)` with an explicit length, and `DateTime(timezone=True)` timestamps with `server_default=func.now()` (`onupdate=func.now()` on `updated_at`)
- `UniqueConstraint('title', 'author_id', 'published_year', name='books_title_author_year_key', postgresql_nulls_not_distinct=True)` in `__table_args__`
- `author: Mapped['AuthorModel'] = relationship(back_populates='books', lazy='raise')` with the sibling import under `if TYPE_CHECKING:`

**Must not produce**:
- `Column(`, a `String` with no length, a composite constraint with no `name=`, or a `relationship()` without `lazy='raise'`

### Eval 2 — Cascade delete

**Prompt**: "Deleting an author should delete their books, but `delete_author_by_id` raises `IntegrityError: violates foreign key constraint`."

**Must produce**:
- `ForeignKey('authors.id', ondelete='CASCADE')` on the child, paired with `passive_deletes=True` and `cascade='all, delete-orphan'` on `AuthorModel.books`
- `delete_author_by_id` as a Core `delete(AuthorModel)` with `.returning(AuthorModel.id)` that logs a miss with the id in the message and returns, so the route answers 204
- A migration generated for the constraint change

**Must not produce**:
- `passive_deletes=True` left next to a plain `ForeignKey`
- The children loaded and deleted in the service instead of the Core `delete(AuthorModel)` statement
- `NotFoundError` raised for a delete that matched no row, unless the caller must tell "deleted" from "never existed"

### Eval 3 — Migration

**Prompt**: "I added a `published_year` column to `BookModel`. Generate the migration."

**Must produce**:
- `uv run alembic revision --autogenerate -m "add published year"` (`make migration MSG="..."` where the repository ships the wrapper)
- The generated revision opened and read before it is applied

**Must not produce**:
- `alembic revision -m "..."` without `--autogenerate`, hand-written `op.add_column(...)` in place of running it, or a column rename left as the drop-plus-add autogenerate emits

### Eval 4 — Write transaction boundary

**Prompt**: "Write `BookService.create_author` for a normal POST endpoint."

**Must produce**:
- `insert(AuthorModel).values(**creation.model_dump()).returning(AuthorModel)` executed with `await self._session.scalar(query)`, returning `Author.model_validate(author)`

**Must not produce**:
- `commit()` or `rollback()` in the request-scoped service
- `async with self._session.begin_nested():` around the single statement, or a `flush()` before reading the row back

### Eval 5 — Paginated list with filters

**Prompt**: "Add a paginated `list_books` returning each book with its author, filtered by optional ids, a case-insensitive title substring, and a `created_from` timestamp."

**Must produce**:
- `select(BookModel).options(selectinload(BookModel.author))` with the clauses in `_apply_filters(self, query: Select, filters: BookListFilters) -> Select`
- `BookModel.title.icontains(filters.title, autoescape=True)` and `BookModel.created_at >= filters.created_from` against the `DateTime(timezone=True)` column
- `apaginate(self._session, query, params=pagination_params, transformer=...)` with a class-level `TypeAdapter[list[BookWithAuthor]]` built once per process

**Must not produce**:
- `joinedload(BookModel.author)` inside a list query, or hand-rolled `limit` / `offset` arithmetic
- `ilike(f'%{value}%')` assembled by hand, or a normalizer that strips or attaches `tzinfo` before comparing

### Eval 6 — Diagnose `lazy='raise'`

**Prompt**: "`sqlalchemy.exc.InvalidRequestError: 'BookModel.cover' is not available due to lazy='raise'` when the response serializes a book."

**Must produce**:
- `.options(joinedload(BookModel.cover))` added to the `select(BookModel)` that fetched the row — a to-one on a single-object fetch

**Must not produce**:
- The model changed to `lazy='select'`, `'raise_on_sql'`, `'joined'`, or `'selectin'`
- The `InvalidRequestError` caught and worked around while the query stays unchanged

### Eval 7 — Keep `lazy='raise'` and fix the query

**Prompt**: "Can we just drop `lazy='raise'` from the relationships? Adding `.options(...)` every time is annoying."

**Must produce**:
- Model files unchanged, `lazy='raise'` still on every `relationship()`. The one exception: when the user explicitly asks to declare eager loading on a relationship every query needs, that `relationship()` gets `lazy='selectin'` (or `'joined'`) with a comment saying why, and `lazy='raise'` stays on the rest
- A diff that adds the missing `.options(selectinload(...))` / `.options(joinedload(...))` to the queries that were failing

**Must not produce**:
- The model silently switched to an eager `lazy=` to hide a `MissingGreenlet` / `InvalidRequestError` raised by one query
- A helper that re-fetches objects on attribute access

### Eval 8 — Single-object to-one fetch

**Prompt**: "Add `get_book_by_id` returning the book with its author and its cover."

**Must produce**:
- `.options(joinedload(BookModel.author), joinedload(BookModel.cover))` with `.filter(BookModel.id == book_id)` and `await self._session.scalar(query)`

**Must not produce**:
- `selectinload` for a to-one on a single-object fetch, which only adds a round trip
- `.unique()`, which a `joinedload` needs only when it targets a collection

### Eval 9 — Alembic in the engine fixture

**Prompt**: "Our session-scoped `_engine` fixture hangs at teardown, in the Alembic downgrade."

**Must produce**:
- `alembic_config.attributes['connection'] = connection` inside the callback passed to `connection.run_sync(...)`, so Alembic runs on the caller's connection instead of a second one that commits outside the fixture's transaction and then deadlocks against the locks that transaction holds

**Must not produce**:
- `Base.metadata.create_all()` as the test schema
- A downgrade to `base` before the first upgrade

---

## ai-agents

### Triggering

**Should load**:
- "Add an AI assistant endpoint that answers questions about our catalog"
- "The agent's tool needs access to the orders service"
- "Test the assistant endpoint without calling the real model"
- "Provider throttling should come back as HTTP 429"
- "Stream the assistant's answer to the client"

**Should not load**:
- "Add a plain CRUD endpoint for authors" → `fastapi-service`
- "Paginate the books list" → `postgres-database`
- "Write the factory for the request schema" → `python-testing`
- "Add an endpoint that calls the OpenAI SDK directly; we don't use pydantic-ai" → `fastapi-service` (this skill is pydantic-ai only and does not convert the project)
- "Mock the `BookModel` in the books tests" → `python-testing` (a database model, not an LLM; the answer there is the real container)

### Eval 1 — New agent

**Prompt**: "Define a read-only catalog assistant agent with two tools: count_items and list_items."

**Must produce**:
- One slice `app/domains/catalog_assistant/` with `agents.py`, `prompts.py`, `service.py`, `routes.py`, `schemas/`, and deps as `@dataclass(frozen=True, slots=True, kw_only=True)` in `schemas/schemas_agent.py`
- `build_catalog_assistant_agent(model: Model) -> Agent[CatalogAssistantDeps, CatalogAssistantResponse]` with `@agent.tool` registrations inside it reaching services through `ctx.deps`, `instructions=` written as rules ("Use `count_items` for counts"), and agent-level `ModelSettings(max_tokens=..., thinking=...)`

**Must not produce**:
- `system_prompt=`, `retries=0`, `temperature` in the agent's `ModelSettings`, or a tool importing a service module instead of taking it from `ctx.deps`

### Eval 2 — Tool schema the model can read

**Prompt**: "The model keeps calling `list_items` with a limit of 500. Fix the tool definition."

**Must produce**:
- `limit: int = Field(default=20, ge=1, le=100, description='Maximum number of items to return.')` on the tool's `BaseModel` input, and a one-line docstring summary on the tool
- A test asserting on `TestModel.last_model_request_parameters` where the change is covered

**Must not produce**:
- An `Args:` entry for the single flattened `BaseModel` parameter, whose name the model never sees
- The bound asked for in prose instead of `ge` / `le`

### Eval 3 — Agent as a FastAPI dependency

**Prompt**: "Wire the catalog assistant into a POST endpoint with per-request model choice."

**Must produce**:
- `async def get_catalog_assistant_agent(payload, model_registry: Annotated[ModelRegistry, Depends(get_model_registry)])` beside the builder in `agents.py`, returning `build_catalog_assistant_agent(model_registry[payload.model])`
- Route injecting `Annotated[Agent[...], Depends(get_catalog_assistant_agent)]` and calling `service.answer(payload, agent)`, which runs `agent.run(payload.question, deps=..., usage_limits=CATALOG_ASSISTANT_USAGE_LIMITS)`

**Must not produce**:
- The agent constructed inside the route, or held as a service attribute
- A synchronous `def` dependency, or `agent.run(...)` with no `usage_limits`

### Eval 4 — Model registry and failover

**Prompt**: "Callers should be able to ask for a fast model, and the default should fail over to it when the primary provider is down."

**Must produce**:
- `AssistantModelName.DEFAULT` / `AssistantModelName.FAST` in `app/core/enums.py`, model ids as plain `str` settings, and `FallbackModel(default_model, fast_model)` for `DEFAULT` in `app/infrastructure/llms/registry.py`
- Provider knobs passed as `settings=` on the `Model`, as in `OpenAIResponsesModel(..., settings=OpenAIResponsesModelSettings(...))`

**Must not produce**:
- `isinstance(model, BedrockConverseModel)` or any provider branch in the builder
- Provider model ids as `Literal[...]` in `Settings`, or hardcoded in the domain

### Eval 5 — Happy-path test

**Prompt**: "Write a happy-path test for the catalog assistant endpoint."

**Must produce**:
- `pytest_configure` setting `ALLOW_MODEL_REQUESTS = False`, which is read per request, so constructing a real model in a test stays fine
- A fixture from `generate_test_agent(app, get_catalog_assistant_agent, build_catalog_assistant_agent)`, and `TestModel(custom_output_args=CatalogAssistantResponse(answer=answer).model_dump(mode='json'), call_tools=[])` inside `agent.override(model=...)`

**Must not produce**:
- A hand-rolled `ModelResponse` matching an output tool by name or index
- A test that reaches a real provider

### Eval 6 — Provider error mapping

**Prompt**: "What should the endpoint return when the provider throttles us?"

**Must produce**:
- `model_http_error_handler` (429 → 429, every other status → 502), `model_api_error_handler` (→ 503) and `fallback_exception_group_handler` (→ 503; `FallbackExceptionGroup` is an `ExceptionGroup` the `ModelAPIError` handler never sees) in `app/core/exception_handlers.py`, all in `EXCEPTION_HANDLERS`
- A parametrized test driving the endpoint with `build_raising_model(ModelHTTPError(status_code=429, model_name='test'))`

**Must not produce**:
- `openai.RateLimitError`, `botocore.exceptions.ClientError`, or any provider SDK exception in a handler or a test; patched pydantic-ai internals; 500 as the catch-all for provider failures

### Eval 7 — Usage limits

**Prompt**: "A model that keeps calling the same tool should not loop forever. What happens when it hits the cap?"

**Must produce**:
- `UsageLimits(request_limit=5)` passed to `agent.run(...)`, and `UsageLimitExceeded` mapped to 503 in `app/core/exception_handlers.py`
- A test whose `FunctionModel` callback returns a `ToolCallPart` on every turn

**Must not produce**:
- A 4xx for a request that was well formed
- `retries=0` used as the loop guard

### Eval 8 — Streaming

**Prompt**: "Stream the assistant's answer to the client as plain text."

**Must produce**:
- `async with agent.run_stream(payload.question, deps=..., output_type=str, usage_limits=...) as result:` yielding `result.stream_text(delta=True)` into a `StreamingResponse`

**Must not produce**:
- `output_type` passed to `agent.override(...)`, which does not accept it
- `stream_text()` without `delta=True`, or anything that can fail moved after the first chunk

---

## skill-writer

### Triggering

Not applicable — `skill-writer` sets `disable-model-invocation: true` (and `allow_implicit_invocation: false` for Codex), so its description is never used for routing. Agents reach it through the explicit `AGENTS.md` instruction or direct user invocation. It also covers only `skills/` in this repository: a request to author a skill under `~/.cursor/skills/` or another skill system writes no file here. Its behaviour scenarios below are manual-only for now: none of them is in `evals/cases.json`.

### Eval 1 — Too-narrow new skill

**Prompt**: "Add a skill for setting up pytest-asyncio correctly."

**Must produce**:
- The edit landing in `skills/python-tooling/SKILL.md` (pytest section) or `skills/python-testing/SKILL.md`

**Must not produce**:
- A new `skills/pytest-asyncio-setup/SKILL.md`, which has fewer than three distinct recurring triggers

### Eval 2 — Description that summarizes the workflow

**Prompt**: "Write a description for a new redis-caching skill: 'Use to set up Redis caching by declaring a RedisClient dependency, adding a get_cache/set_cache pattern, and wiring expiration policies.'"

**Must produce**:
- A rewritten `description:` of 30-60 words and under 400 characters: triggers first ("Use when adding a cache layer, …"), then concrete keywords (TTL, invalidation, eviction), no ordered steps
- A sibling pointer only where a real prompt could land on the wrong skill, in the form `python-code-style` uses: "For ruff and formatter configuration see `python-tooling`"

**Must not produce**:
- The workflow-summary form kept, or a `compatibility:` key added in the rewrite
- A blanket exclusion sentence ("Does not cover sessions, queues, …") for what the skill name already implies, paid on every discovery decision

### Eval 3 — Oversized SKILL.md

**Prompt**: "The new ai-agents SKILL.md is 420 lines. What should I do?"

**Must produce**:
- The largest cohesive block moved to `skills/ai-agents/reference/<topic>.md`, with a one-line "load when …" pointer from `SKILL.md`, back under the 300-line target
- `reference/anthropic-best-practices.md` consulted for which limits are upstream (500 lines, 1,024-character description) and which are house rules

**Must not produce**:
- Content compressed in place to stay under the limit, or a second `SKILL.md` in a subfolder
- A reference file nothing links to

### Eval 4 — Frontmatter allowlist

**Prompt**: "Add `tags: [python, redis]` and an `argument-hint` to this skill's frontmatter so it gets found more often."

**Must produce**:
- Frontmatter limited to `name`, `description`, `disable-model-invocation`, `paths`, `when_to_use`, `metadata`, with extra triggers moved into `when_to_use` and version facts into the body's `> Requires` line

**Must not produce**:
- A host-specific key added to `SKILL.md`, which the other hosts ignore or reject

### Eval 5 — Verify quoted text in context

**Prompt**: "`| Put private methods before public methods | Class Layout |` is wrong. Public methods must be first. Fix it."

**Must produce**:
- The whole `## Common mistakes` table read, header included, and no diff when the row is a mistake description rather than a prescription

**Must not produce**:
- The row rewritten from the quoted fragment alone, or a `Mistake` column entry treated as a rule to follow

### Eval 6 — Invocation-control metadata

**Prompt**: "Make `skills/skill-writer` explicit-only when packaged for Claude Code, Cursor, and Codex."

**Must produce**:
- `disable-model-invocation: true` in `skills/skill-writer/SKILL.md` and `policy.allow_implicit_invocation: false` in `skills/skill-writer/agents/openai.yaml`, kept in sync, with docs referencing the skill by file path

**Must not produce**:
- Codex-only fields added to `.codex-plugin/plugin.json`, or the user's ability to invoke the skill explicitly removed

### Eval 7 — Adding a gotcha

**Prompt**: "Add a gotcha to `python-tooling`: the coverage gate passes below the threshold."

**Must produce**:
- An entry under `## Gotchas` naming the observed behaviour, its reason and the fix — `--cov-fail-under=90` passing at 89.62% because pytest-cov rounds to `[tool.coverage.report] precision`, which defaults to 0
- A case in `evals/cases.json` that fails without the new rule

**Must not produce**:
- A rule ending in "see `<sibling>` for the full pattern", or the same rule repeated in a second skill
- A claim no run produced

### Eval 8 — Redundant `## When to use`

**Prompt**: "My new `redis-cache` draft has a `## When to use` section listing the same triggers as its description. Review it."

**Must produce**:
- The section dropped, the description left as the single trigger surface, and any sub-trigger it cannot fit moved to `when_to_use` in the frontmatter

**Must not produce**:
- The bullet list kept or expanded, or `## When to use` treated as part of the body skeleton

---

## project-scaffolding

### Triggering

**Should load**:
- "Create an app that serves a catalog of books" (no existing project)
- "Spin up a tiny webhook receiver service, nothing fancy"
- "Bootstrap a fresh repo for the analytics API"

**Should not load**:
- "Add `GET /v1/books/{book_id}` to my service" → `fastapi-service`
- "Add CI to this existing project" → `python-tooling`
- "Add the Postgres testcontainer fixture" → `postgres-database`
- "Create an app that renames photos by their EXIF date" → no skill (a script or CLI, not an HTTP service)

### Eval 1 — Greenfield: infer and scaffold

**Prompt**: "Build me an app called 'Book Catalog API' that serves books with search and CRUD."

**Must produce**:
- `uv tool run cookiecutter https://github.com/DenysMoskalenko/BoilerplateBuilder --checkout 492fc9b1e752a761e6a65182626502b8569e8143 --no-input` with `project_type=fastapi_db` passed explicitly
- `project_name="book-catalog-api"`, `project_description` from the conversation, `author_name` / `author_email` from `git config`, the template and pinned revision named before the run, and the revision plus the `make check` result reported after it

**Must not produce**:
- Hand-assembled `app/`, `pyproject.toml`, Docker, or CI
- `project_name="Book Catalog API"` (a space breaks `uv lock` inside the hook), an omitted `project_type` (the template default is `fastapi_db_agent`), or a retired input such as `use_pre_commit`

### Eval 2 — Existing project: do not scaffold

**Prompt**: "This repo already has `app/` and `pyproject.toml`. Add `GET /v1/books/{book_id}`, and while you're at it give us the standard baseline."

**Must produce**:
- The endpoint handed to `fastapi-service` (plus `postgres-database` when DB-backed), and any tooling gap closed with `python-tooling`
- Generation only into a fresh empty directory (`-o ../<name>`) if the user insists on the template baseline

**Must not produce**:
- A `cookiecutter` invocation in a directory that already holds a project
- `Extract Here` over an existing `README.md` or `.gitignore`, which it overwrites

### Eval 3 — DB + agent inference

**Prompt**: "I want an assistant that answers questions about our orders and remembers past conversations."

**Must produce**:
- `project_type=fastapi_db_agent` passed explicitly, then hand-off to `fastapi-service` + `postgres-database` + `ai-agents`

**Must not produce**:
- `fastapi_agent`, which drops the persistence the prompt requires, or `fastapi_slim`
- A question asking the user to choose the variant by its template name

### Eval 4 — Slim service, minimal questioning

**Prompt**: "Spin up a tiny webhook receiver service, no database, nothing fancy."

**Must produce**:
- `project_type=fastapi_slim` passed explicitly, with the baseline inputs (`python_version=3.13`, `use_github_actions=yes`, OTEL off) left at their defaults

**Must not produce**:
- The user interrogated about Python version, hooks, or OTEL after "nothing fancy"; `fastapi_db` / `fastapi_db_agent`; `generate_local_otel_stack=yes` without `use_otel_observability=yes`

### Eval 5 — Empty `.git`-only target

**Prompt**: "I ran `git init` in an empty folder `orders-svc` and I'm in it — set up a new orders API with a database right here."

**Must produce**:
- `extract_to_current_dir="Extract Here"` and `initialize_git=no` alongside `project_type=fastapi_db` and `--no-input`

**Must not produce**:
- The `Create New` default, which nests the project at `orders-svc/orders-svc`
- `initialize_git=yes` in a directory that already carries `.git`

### Eval 6 — After generation

**Prompt**: "The generator finished. What now?"

**Must produce**:
- `make check` in the project root, and the revision used reported alongside its result
- The sample domains replaced: delete `app/domains/examples` (or `examples_agent`) and the shipped `add_example_model` revision under `migrations/versions/`, then `uv run alembic revision --autogenerate` for a fresh initial migration; `app/domains/health_checks` stays

**Must not produce**:
- First-time setup from `python-tooling` redone — `.env`, `uv lock && uv sync`, ruff, the initial commit and `prek install` already ran in the hook
- Feature code written while `make check` is red
