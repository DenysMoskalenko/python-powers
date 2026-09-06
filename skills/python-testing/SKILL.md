---
name: python-testing
description: Use when writing, reviewing, or stabilizing tests for a FastAPI service — API-level tests over `httpx2.AsyncClient`, polyfactory factories, test layout and naming, data helpers, assertions, dependency overrides, flaky-test triage, and coverage policy. For Postgres container and session fixtures see `postgres-database`; for LLM mocking (`TestModel`, `FunctionModel`) see `ai-agents`.
---

# FastAPI Test Patterns

This skill owns how a FastAPI service is tested: what to drive through HTTP, how the shared `app` and `client` fixtures are built, the dependency-override utilities the other test setups build on, polyfactory factories and data helpers, file layout, naming, assertions, flaky-test triage, and the coverage policy. An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires Python 3.13+, pytest, pytest-asyncio, polyfactory, httpx2.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `python-tooling`, `fastapi-service`, `postgres-database`, `ai-agents`, `project-scaffolding`.
For the Postgres container, engine and `session` fixtures use `postgres-database`; for pydantic-ai LLM mocking use `ai-agents`.

## What to test, and with what

Prefer API-level tests to isolated unit tests. One request through `AsyncClient` exercises routing, dependency injection, request validation, the service, serialization and the exception handlers together, which is the combination that actually breaks. Keep `tests/unit/` for behaviour with no HTTP surface: a factory, a sorting helper, a model constraint. Mock only what you cannot run locally — LLM providers, third-party HTTP APIs, cloud services. Databases and brokers run for real; the house default is the Postgres testcontainer from `postgres-database`, which owns the reason. When no Docker daemon is reachable, ask for a reachable PostgreSQL to point `DATABASE_URL` at; do not fall back to SQLite or a mocked session.

## Layout and naming

```text
tests/
  conftest.py              # app and client fixtures, pytest_configure
  dependencies.py          # override utilities and the missing-fixture sentinel
  factories.py             # one polyfactory factory per *Create schema
  api/test_books.py        # one file per feature: setup helpers, then a class per operation
  unit/test_factories.py
```

Inside a feature file the helpers come first, then one class per operation — `TestBooksCreate`, `TestBooksGet`, `TestBooksList`, `TestBooksPatch` — each holding `test_success` for the happy path and `test_fail_<reason>` for every error path, with a suffix when a class has several of either (`test_success_filters_by_title_and_author`, `test_fail_unknown_author`). The name carries the documentation, which is what `test_validation` and `test_case_2` fail to do.

## Run configuration

`pytest_configure` runs before the first test module is imported, which is where the switches that have to be set before `create_app()` belong:

```python
import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    os.environ['MIGRATION_ON_STARTUP'] = 'False'
```

Take the line each skill the service uses contributes, and no others. `MIGRATION_ON_STARTUP` above belongs to `postgres-database`, where the engine fixture owns schema creation and the app's lifespan must not race it for the same tables; `ai-agents` contributes `ALLOW_MODEL_REQUESTS = False` and gives the reason there.

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

`app` is a plain synchronous `def` and takes no engine or container parameter: ordering is guaranteed by the autouse container fixture in `postgres-database`. The `create_app` import stays inside the fixture body so nothing in `app.main`'s import graph runs before that fixture has set `DATABASE_URL`. Both fixtures are session-scoped — one app and one client for the whole run, so treat that app object as immutable infrastructure: anything a single test needs to change goes in as a dependency override installed for the duration of that test and removed afterwards, never as a mutated attribute on the shared app.

`ASGITransport` does not run the app's lifespan, so startup code has not executed in an ordinary test. A fixture that needs it wraps the client:

```python
@pytest.fixture
async def started_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as started_client:
            yield started_client
```

The `session` fixture — a connection-bound `AsyncSession` inside a transaction that is rolled back after each test — lives in `postgres-database`. It installs its `get_session` override through `temporary_override`, so the sentinel below is back in place before the next test starts.

## Dependency overrides

`tests/dependencies.py` is the shared toolkit; the database and agent fixtures in the sibling skills build on it.

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

A mounted `FastAPI` sub-application keeps its own `dependency_overrides` dict and ignores the parent's, which is why `override_dependency` and `_remove_override` walk the mounts. `temporary_override` puts back whatever was installed before the block — the sentinel, or an outer override — instead of clearing the entry, and `temporary_overrides` does the same for several dependencies at once. Any other dependency a test must not reach by accident joins `get_session` in `override_app_test_dependencies`. In a service without a database, drop the `get_session` import and the sentinel and leave `override_app_test_dependencies` empty, so the agent fixtures still have their hook.

The sentinel is a function that raises, not a placeholder class or object. An override returning a placeholder is injected happily and the test then dies much later with an obscure `AttributeError` inside the service, or passes silently if that endpoint never touched the database. Raising names the missing fixture at the point of use.

### Overriding get_settings for one test

```python
async def test_success_reports_the_configured_version(app: FastAPI, client: AsyncClient) -> None:
    settings = get_settings().model_copy(update={'PROJECT_VERSION': '9.9.9'})

    with temporary_override(app, get_settings, lambda: settings):
        response = await client.get('/health/live')

    assert response.status_code == 200
    assert response.json()['version'] == '9.9.9'
```

`get_settings` is the `lru_cache`d settings provider in `app/core/config.py`, owned by `fastapi-service`; `temporary_override` is the helper above. Prefer this to setting an environment variable and clearing the cache: the swap is scoped to the block and cannot leak into the next test. It reaches only injected values — `Annotated[Settings, Depends(get_settings)]` in a route or service — because a module-level `get_settings()` call has already run.

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
- The model comes from the generic parameter, so `__model__` is inferred, and `__check_model__` stays at its default. That check verifies that every polyfactory field declared on the factory exists on the model, so renaming a schema field turns a stale factory into a `ConfigurationException` at import time instead of a puzzling test failure.
- `.build()` runs the model's validators, so a factory cannot produce a payload the API would reject. Add `factory_use_construct=True` only for a test that deliberately needs an invalid object: `BookCreateFactory.build(factory_use_construct=True, author_id=1, published_year=1000)`.
- Use `Use(lambda: ...)` with faker where the shape of the value carries meaning — a name, a title, a plausible year — and leave the rest to polyfactory.

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

Set data up through the service and assert through the API; the helpers live at the top of the feature file that uses them, and a caller names only what the test is about: `await create_test_book(session, author.id, title='Tehanu')`. The `TypedDict` and `Unpack` signature turns a misspelled override into a type error instead of a silently ignored keyword. No `flush()` is needed — the service's `insert(...).returning(...)` is executed by `session.scalar()` at that line, so the row is visible to the request that follows. `BookService.create_author` is defined in `postgres-database` alongside `create_book`. The `Unpack[...Overrides]` signature accepts only model fields, so polyfactory's own build switches cannot travel through the helper: a test that needs an invalid object calls the factory directly — `BookCreateFactory.build(factory_use_construct=True, author_id=author.id, published_year=1000)` — and passes the result to the service itself.

## Assertions

Assert the status code, then the body in full: the fields the client sent, plus the fields the server generated.

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

`model_dump(mode='json')` both sends the payload and builds the expected body, so dates, UUIDs and enums are compared in the form the API returns them. Copying the generated fields into the expected dict is only sound because the two lines above pin `id` and the timestamp format independently; without them the comparison would say nothing about the server's half of the response. Error cases assert the status code and the `detail` the handler produced. Explicitness beats brevity in tests: repeating three lines of setup across five tests reads better than a helper the reader has to open, so the DRY threshold from `python-code-style` is deliberately higher here — about five repetitions of a multi-step check.

## Flaky tests

- **An override that was not restored.** Install every swap with `temporary_override`; a bare `override_dependency` in a fixture outlives its test, and the next test reuses a closed session or a stale agent.
- **Unseeded random data** that occasionally collides with a unique constraint or trips a validator. Reproduce with `BookCreateFactory.seed_random(0)` (or `__random_seed__ = 0` on the factory), then narrow the offending field with `Use(...)`; a pinned seed is the diagnostic, not the fix.
- **A real clock.** Freeze it with `freeze_time('2024-01-02T03:04:05Z')` from freezegun for values the application computes, rather than asserting on `datetime.now()` within a tolerance; adding the package goes through `python-tooling`. `created_at` and `updated_at` come from the database clock, which freezegun does not reach, so assert their tz-awareness or their ordering instead of their value.
- **Order dependence.** Run the file on its own, then the suite with the order changed. `pytest-randomly` does that on every run; adding it goes through `python-tooling`.
- **Background work.** A task the endpoint started may still be running when the test asserts. Assert on an observable effect and give the task a handle the test can await instead of sleeping.

## Coverage

The floor is 90% line coverage for the suite; `python-tooling` owns the command, the gate and the configuration. Treat it as a floor and not a target: a test that raises the number without naming a production break it would catch is not worth maintaining.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| Mocking the service in an API test | Drive the endpoint and let the real service run | The mock passes while routing, validation and the query stay untested |
| `override_dependency` in a fixture with no restore | `temporary_override`, or `temporary_overrides` for several | The override outlives the test and the next one silently reuses it |
| A sentinel override that returns a placeholder object | A `NoReturn` function that raises and names the fixture | An injected placeholder fails later with an obscure `AttributeError`, or not at all |
| `__check_model__ = False` on a factory | Leave the default | It switches off the check that catches a factory field the schema no longer has |
| Spelling out `__model__` or `factory_use_construct=False` | `ModelFactory[BookCreate]` and a plain `.build()` | Both are the defaults, so writing them suggests they change something |
| `json=payload.model_dump()` | `json=payload.model_dump(mode='json')` | Dates, UUIDs and enums stay as Python objects and the client raises `TypeError` |
| `assert Model.model_validate(response.json())` as the body check | Compare the body with the payload plus the server-generated fields | Validation passes for any well-formed response, including a wrong one |

## Gotchas

- A session-scoped async fixture and a function-scoped test run on different event loops unless `asyncio_default_test_loop_scope` is `"session"`; `asyncio_default_fixture_loop_scope` alone does not fix it, and `python-tooling` sets both so neither half drifts. SQLAlchemy over psycopg tolerates the mismatch because it binds no loop to the connection; a loop-bound driver such as asyncpg fails with `attached to a different loop`.
- `__check_model__` only sees polyfactory field declarations (`Use`, `Ignore`, `Require`, `PostGenerated`, callables). A misspelled plain class attribute such as `titel = 'oops'` is accepted silently and does nothing.
- `ASGITransport` re-raises exceptions from the app instead of turning them into a 500 response, which is how a missing `session` fixture surfaces as the sentinel `RuntimeError` inside `await client.get(...)`. To assert on a 500 response body instead, build the transport with `ASGITransport(app=app, raise_app_exceptions=False)`.
- Timestamps come back as strings, so `datetime.fromisoformat(actual['created_at']).tzinfo is not None` is what catches a column that silently reverted to naive; comparing the strings alone does not.
