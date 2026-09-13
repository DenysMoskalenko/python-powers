---
name: python-testing
description: Use when writing, reviewing, or stabilizing tests for a FastAPI service, or editing `conftest.py` — API-level tests over `httpx2.AsyncClient`, polyfactory factories, layout and naming, data helpers, assertions, dependency overrides, flaky-test triage, and coverage. For Postgres container and session fixtures see `postgres-database`; for LLM mocking (`TestModel`, `FunctionModel`) see `ai-agents`.
---

# FastAPI Test Patterns

This skill owns how a FastAPI service is tested: what to drive through HTTP, the shared `app` and `client` fixtures, the dependency-override utilities, polyfactory factories and data helpers, layout, naming, assertions, flaky-test triage, and coverage. An explicit user or project instruction (`AGENTS.md`, `pyproject.toml`, existing code) overrides a house default here; keep the invariants that still apply and name the default you departed from.

> Requires Python 3.13+, pytest, pytest-asyncio, polyfactory, httpx2.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` (load it alongside), `python-tooling`, `fastapi-service`, `postgres-database` (container, engine and `session` fixtures), `ai-agents` (LLM mocking), `project-scaffolding`.

## What to test, and with what

Prefer API-level tests to isolated unit tests: one request through `AsyncClient` exercises routing, dependency injection, validation, the service, serialization and the exception handlers together, which is the combination that actually breaks. `tests/unit/` is for behaviour with no HTTP surface: a factory, a sorting helper, a model constraint. Mock only what you cannot run locally — LLM providers, third-party HTTP APIs, cloud services. Databases and brokers run for real; the house default is the Postgres testcontainer from `postgres-database`. Without a Docker daemon, ask for one — the fixtures start their own container and downgrade it to `base` at teardown — rather than falling back to SQLite or a mocked session.

## Layout and naming

```text
tests/
  conftest.py              # app and client fixtures, pytest_configure
  dependencies.py          # override utilities and the missing-fixture sentinel
  factories.py             # one polyfactory factory per *Create schema
  api/test_books.py        # one file per feature: setup helpers, then a class per operation
  unit/test_factories.py
```

Inside a feature file the helpers come first, then one class per operation — `TestBooksCreate`, `TestBooksGet`, `TestBooksList`, `TestBooksPatch` — each holding `test_success` and `test_fail_<reason>` per error path, with a suffix when a class has several of either (`test_success_filters_by_title_and_author`). The name carries the documentation.

## Run configuration

`pytest_configure` runs before the first test module is imported, so switches that must be set before `create_app()` go there:

```python
import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    os.environ['MIGRATION_ON_STARTUP'] = 'False'
```

Take only the lines the skills the service uses contribute: `MIGRATION_ON_STARTUP` from `postgres-database`, `pydantic_ai_models.ALLOW_MODEL_REQUESTS = False` from `ai-agents`.

## App and client fixtures

```python
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
import pytest

from tests.dependencies import override_app_test_dependencies


@pytest.fixture(scope='session')
def app() -> FastAPI:
    from app.main import create_app

    _app = create_app()
    override_app_test_dependencies(_app)
    return _app


@pytest.fixture(scope='session')
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client
```

`app` is a plain synchronous `def` with no engine or container parameter; the autouse container fixture in `postgres-database` guarantees ordering. The `create_app` import stays inside the body so nothing in `app.main`'s import graph runs before `DATABASE_URL` is set. Both fixtures are session-scoped: anything one test needs to change goes in as a dependency override installed for that test and removed afterwards, never as a mutated attribute on the shared app.

`ASGITransport` does not run the app's lifespan; a fixture that needs startup code wraps the client:

```python
@pytest.fixture
async def started_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as started_client:
            yield started_client
```

The rollback `session` fixture lives in `postgres-database`; it installs its `get_session` override through `temporary_override`, so the sentinel below is back in place before the next test.

## Dependency overrides

`tests/dependencies.py` is the toolkit the sibling skills' database and agent fixtures build on.

```python
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from typing import NoReturn

from fastapi import FastAPI
from starlette.routing import Mount

from app.infrastructure.db.database import get_session


@dataclass(frozen=True, kw_only=True, slots=True)
class DepOverride:
    dependency: Callable
    override: Callable


def override_dependency(app: FastAPI, dependency: Callable, override: Callable) -> None:
    app.dependency_overrides[dependency] = override
    for route in app.router.routes:
        if isinstance(route, Mount) and isinstance(route.app, FastAPI):
            route.app.dependency_overrides[dependency] = override


def _remove_override(app: FastAPI, dependency: Callable) -> None:
    app.dependency_overrides.pop(dependency, None)
    for route in app.router.routes:
        if isinstance(route, Mount) and isinstance(route.app, FastAPI):
            route.app.dependency_overrides.pop(dependency, None)


@contextmanager
def temporary_override(app: FastAPI, dependency: Callable, override: Callable) -> Generator[None]:
    previous = app.dependency_overrides.get(dependency)
    override_dependency(app, dependency, override)
    try:
        yield
    finally:
        if previous is not None:
            override_dependency(app, dependency, previous)
        else:
            _remove_override(app, dependency)


@contextmanager
def temporary_overrides(app: FastAPI, overrides: Sequence[DepOverride]) -> Generator[None]:
    with ExitStack() as stack:
        for dep in overrides:
            stack.enter_context(temporary_override(app, dep.dependency, dep.override))
        yield


def session_fixture_not_requested() -> NoReturn:
    raise RuntimeError(
        'Database access without the `session` fixture: add `session: AsyncSession` to the test signature.'
    )


def override_app_test_dependencies(app: FastAPI) -> None:
    override_dependency(app, get_session, session_fixture_not_requested)
```

A mounted `FastAPI` sub-application keeps its own `dependency_overrides`, which is why the helpers walk the mounts. `temporary_override` restores whatever was installed before the block — the sentinel, or an outer override — instead of clearing the entry. Any other dependency a test must not reach by accident joins `get_session` in `override_app_test_dependencies`; a service without a database keeps the function, empty, so the `app` fixture is unchanged.

The sentinel raises rather than returning a placeholder: a placeholder fails much later with an obscure `AttributeError`, or passes silently if the endpoint never touched the database.

### Overriding get_settings for one test

```python
async def test_success_reports_the_configured_version(app: FastAPI, client: AsyncClient) -> None:
    settings = get_settings().model_copy(update={'PROJECT_VERSION': '9.9.9'})

    with temporary_override(app, get_settings, lambda: settings):
        response = await client.get('/health/live')

    assert response.status_code == 200
    assert response.json()['version'] == '9.9.9'
```

`get_settings` is the `lru_cache`d provider from `fastapi-service`. Prefer this to setting an environment variable and clearing the cache: the swap is scoped to the block. It reaches only injected values — `Annotated[Settings, Depends(get_settings)]` — because a direct `get_settings()` call never consults `dependency_overrides`.

## Factories

```python
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use

from app.domains.books.schemas import AuthorCreate, BookCreate


class AuthorCreateFactory(ModelFactory[AuthorCreate]):
    name = Use(lambda: AuthorCreateFactory.__faker__.name())


class BookCreateFactory(ModelFactory[BookCreate]):
    title = Use(lambda: BookCreateFactory.__faker__.sentence(nb_words=4).rstrip('.'))
    published_year = Use(lambda: BookCreateFactory.__faker__.random_int(min=1900, max=2020))
```

- One factory per `*Create` schema, all in `tests/factories.py`.
- The model comes from the generic parameter (`__model__` is inferred) and `__check_model__` stays at its default, which turns a factory field the schema no longer has into a `ConfigurationException` at import time.
- `.build()` runs the model's validators, so a factory cannot produce a payload the API would reject; `factory_use_construct=True` is only for a test that deliberately needs an invalid object.
- `Use(lambda: ...)` with faker where the shape of the value carries meaning — a name, a plausible year — and the rest left to polyfactory.

## Data helpers

```python
from typing import TypedDict, Unpack

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.books.schemas import Author, Book
from app.domains.books.service import BookService
from tests.factories import AuthorCreateFactory, BookCreateFactory


class AuthorCreateOverrides(TypedDict, total=False):
    name: str


class BookCreateOverrides(TypedDict, total=False):
    title: str
    published_year: int | None


async def create_test_author(session: AsyncSession, **overrides: Unpack[AuthorCreateOverrides]) -> Author:
    payload = AuthorCreateFactory.build(**overrides)
    return await BookService(session).create_author(payload)


async def create_test_book(session: AsyncSession, author_id: int, **overrides: Unpack[BookCreateOverrides]) -> Book:
    payload = BookCreateFactory.build(author_id=author_id, **overrides)
    return await BookService(session).create_book(payload)
```

Set data up through the service and assert through the API; the helpers live at the top of the feature file, and a caller names only what the test is about: `await create_test_book(session, author.id, title='Tehanu')`. `BookService` is in `postgres-database`.

`Unpack[...Overrides]` turns a misspelled override into a type error and keeps polyfactory's build switches out of the helper; a test that needs an invalid object calls the factory directly. No `flush()` is needed: the service's `insert(...).returning(...)` executes at `session.scalar()` (`postgres-database` explains why).

## Assertions

Assert the status code, then the body in full: the fields the client sent plus the fields the server generated.

```python
from datetime import datetime


class TestBooksCreate:
    async def test_success(self, session: AsyncSession, client: AsyncClient) -> None:
        author = await create_test_author(session)
        payload = BookCreateFactory.build(author_id=author.id)

        response = await client.post('/v1/books', json=payload.model_dump(mode='json'))
        assert response.status_code == 201

        actual = response.json()
        assert actual['id'] > 0
        assert datetime.fromisoformat(actual['created_at']).tzinfo is not None
        assert actual == payload.model_dump(mode='json') | {
            'id': actual['id'],
            'created_at': actual['created_at'],
            'updated_at': actual['updated_at'],
        }

    async def test_fail_unknown_author(self, session: AsyncSession, client: AsyncClient) -> None:
        unreal_id = -9999999
        payload = BookCreateFactory.build(author_id=unreal_id)

        response = await client.post('/v1/books', json=payload.model_dump(mode='json'))

        assert response.status_code == 404
        assert response.json()['detail'] == f'Author(id={unreal_id}) not found'
```

`model_dump(mode='json')` both sends the payload and builds the expected body, so dates, UUIDs and enums are compared as the API returns them. Copying the generated fields into the expected dict is only sound because the two lines above pin `id` and the format of `created_at`. Error cases assert the status code and the handler's `detail`. Explicitness beats brevity in tests, because a reader should follow a test without opening a helper: the DRY threshold here is about five repetitions of a multi-step check, not three.

## Flaky tests

- **An override that was not restored.** Install every swap with `temporary_override`; a bare `override_dependency` in a fixture outlives its test, and the next test reuses a closed session or a stale agent.
- **Unseeded random data** colliding with a unique constraint or a validator. Reproduce with `BookCreateFactory.seed_random(0)`, then narrow the offending field with `Use(...)`; the seed is the diagnostic, not the fix.
- **A real clock.** Freeze it with freezegun's `freeze_time(...)` for values the application computes; `created_at` and `updated_at` come from the database clock, which freezegun does not reach, so assert their tz-awareness or ordering.
- **Order dependence.** Run the file alone, then the suite with the order changed; `pytest-randomly` does that on every run (adding packages goes through `python-tooling`).
- **Background work.** Assert on an observable effect and give the task a handle the test can await instead of sleeping.

## Coverage

The floor is 90% line coverage; `python-tooling` owns the command, the gate and the configuration. A test that raises the number without naming a production break it would catch is not worth maintaining.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| Spelling out `__model__` or `factory_use_construct=False` | `ModelFactory[BookCreate]` and a plain `.build()` | Both are the defaults, so writing them suggests they change something |
| `json=payload.model_dump()` | `json=payload.model_dump(mode='json')` | Dates, UUIDs and enums stay Python objects and the client raises `TypeError` |
| `assert Model.model_validate(response.json())` as the body check | Compare the body with the payload plus the server-generated fields | Validation passes for any well-formed response, including a wrong one |

## Gotchas

- A session-scoped async fixture and a function-scoped test run on different event loops unless `asyncio_default_test_loop_scope` is `"session"`; `asyncio_default_fixture_loop_scope` alone does not fix it, and `python-tooling` sets both. psycopg tolerates the mismatch; a loop-bound driver such as asyncpg fails with `attached to a different loop`.
- `__check_model__` only sees polyfactory field declarations (`Use`, `Ignore`, `Require`, `PostGenerated`, callables); a misspelled plain class attribute such as `titel = 'oops'` is accepted silently.
- `ASGITransport` re-raises app exceptions instead of answering 500, which is how a missing `session` fixture surfaces as the sentinel `RuntimeError` inside `await client.get(...)`. To assert on a 500 body, pass `raise_app_exceptions=False`.
- Timestamps come back as strings; `datetime.fromisoformat(actual['created_at']).tzinfo is not None` catches a column that silently reverted to naive.
