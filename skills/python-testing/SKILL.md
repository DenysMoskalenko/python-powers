---
name: python-testing
description: Use when writing, reviewing, or planning tests for a FastAPI service — API-level test philosophy, polyfactory data generation, test organization, helper patterns, assertion patterns, FastAPI dependency overrides, and coverage requirements. For PostgreSQL container/fixture setup see `postgres-database`; for pydantic-ai test mocking see `ai-agents`.
---

# Python FastAPI Testing Patterns

Testing patterns for FastAPI services. Scoped to HTTP/API testing, shared test fixtures, and FastAPI dependency overrides. Technology-specific infrastructure (database isolation, AI agent mocking) lives in dedicated skills.

> Requires Python 3.13+, pytest, pytest-asyncio, polyfactory, httpx.
> Examples use `app/` as the top-level package. Substitute your package name if different.

**Related**: `python-code-style`, `python-tooling`, `postgres-database`, `ai-agents`.

## Test Philosophy

Prefer API-level tests over isolated unit tests. Test through HTTP endpoints using `AsyncClient` — this exercises the full stack (routes, DI, serialization, validation, error handling) in one shot.

Mock only what you cannot control: external services (LLMs, third-party APIs, cloud providers). Prefer real infrastructure (testcontainers) over in-memory fakes for databases and message brokers.

## Test Data Factories

Use `polyfactory` `ModelFactory` subclasses for each `*Create` schema. Factories generate valid, randomized test data using faker:

```python
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use


class AuthorCreateFactory(ModelFactory[AuthorCreate]):
    __model__ = AuthorCreate
    __check_model__ = False

    first_name = Use(lambda: AuthorCreateFactory.__faker__.first_name())
    last_name = Use(lambda: AuthorCreateFactory.__faker__.last_name())
    birthday = Use(lambda: AuthorCreateFactory.__faker__.date_of_birth())
    description = Use(lambda: AuthorCreateFactory.__faker__.text())
```

- `__check_model__ = False` — skip model validation at factory class definition
- `Use(lambda: ...)` with faker — produce realistic domain values instead of random strings
- One factory per `*Create` schema, all in `tests/factories.py`
- Build instances: `AuthorCreateFactory.build()` or with `factory_use_construct=False` when validators must run

## Test Organization

### File Structure

```text
tests/
  conftest.py          # Shared fixtures (app, client, session, containers)
  dependencies.py      # Dependency override utilities
  factories.py         # Polyfactory factories
  api/
    test_authors.py    # One file per domain entity
    test_books.py
```

### Grouping by Behavior

Group test cases into classes by operation:

```python
class TestAuthorsCreate:
    async def test_success(self, session: AsyncSession, client: AsyncClient) -> None: ...
    async def test_fail_duplicate_identity(self, session: AsyncSession, client: AsyncClient) -> None: ...
    async def test_fail_unreal_birthday(self, session: AsyncSession, client: AsyncClient) -> None: ...

class TestAuthorsList:
    async def test_list_empty(self, session: AsyncSession, client: AsyncClient) -> None: ...
    async def test_list_paginates(self, session: AsyncSession, client: AsyncClient) -> None: ...

class TestAuthorsGet:
    async def test_success(self, ...) -> None: ...
    async def test_fail_not_found(self, ...) -> None: ...
```

Naming: `test_success` for happy path, `test_fail_<reason>` for error cases. Files: `test_<feature>.py`.

## Test Helper Pattern

Create helpers for test data setup that call the service directly, then test behavior through the API:

```python
from datetime import date
from typing import TypedDict, Unpack


class AuthorCreateOverrides(TypedDict, total=False):
    first_name: str
    last_name: str
    birthday: date | None
    description: str


async def create_test_author(session: AsyncSession, **overrides: Unpack[AuthorCreateOverrides]) -> Author:
    payload = AuthorCreateFactory.build(factory_use_construct=False, **overrides)
    author = await AuthorService(session).create_author(payload)
    return author
```

- Accept overrides as kwargs — callers pass only what the test cares about
- Use factory defaults for everything else
- Call service directly (not HTTP) for setup — test the actual endpoint separately
- `flush()` after service call so the data is visible within the transaction

Usage: `await create_test_author(session, first_name='Jane')` — only specify what matters.

## Writing Test Cases

### Success Cases

Validate the full response — status code, then body:

```python
async def test_success(self, session: AsyncSession, client: AsyncClient) -> None:
    payload = AuthorCreateFactory.build()

    response = await client.post('/v1/authors', json=payload.model_dump(mode='json'))
    assert response.status_code == 201

    actual = response.json()
    assert Author.model_validate(actual)
    expected = payload.model_dump(mode='json') | {
        'id': actual['id'],
        'created_at': actual['created_at'],
        'updated_at': actual['updated_at'],
    }
    assert actual == expected
```

- `model_dump(mode='json')` for JSON-serializable dict (handles dates, UUIDs)
- Merge payload with server-generated fields (`id`, timestamps) for full comparison
- `model_validate` to confirm the response matches the expected schema

### Error Cases

Assert both status code and error message:

```python
async def test_fail_not_found(self, session: AsyncSession, client: AsyncClient) -> None:
    unreal_id = -9999999
    response = await client.get(f'/v1/authors/{unreal_id}')
    assert response.status_code == 404
    assert response.json()['detail'] == f'Author(id={unreal_id}) not found'
```

### DRY Relaxation

In tests, explicitness is more valuable than brevity. Repeat setup code when it makes the test's intent clearer. Tests are documentation — a reader should understand what's being tested without jumping to shared helpers.

Don't abstract test assertions into helper functions unless the same multi-step assertion appears 5+ times.

## Dependency Override Utilities

Shared utilities for test-scoped dependency swaps. Used by ALL technology-specific test setups (DB session overrides, agent overrides, etc.):

```python
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass

from fastapi import FastAPI
from starlette.routing import Mount


@dataclass(frozen=True, kw_only=True, slots=True)
class DepOverride:
    dependency: Callable
    override: Callable


def override_dependency(app: FastAPI, dependency: Callable, override: Callable) -> None:
    app.dependency_overrides[dependency] = override
    for route in app.router.routes:
        if isinstance(route, Mount) and isinstance(route.app, FastAPI):
            route.app.dependency_overrides[dependency] = override


@contextmanager
def temporary_override(app: FastAPI, dependency: Callable, override: Callable) -> Generator[None, None, None]:
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
def temporary_overrides(app: FastAPI, overrides: Sequence[DepOverride]) -> Generator[None, None, None]:
    with ExitStack() as stack:
        for dep in overrides:
            stack.enter_context(temporary_override(app, dep.dependency, dep.override))
        yield
```

- `override_dependency` — propagates overrides to mounted sub-applications
- `temporary_override` — restores original dependency when the block exits
- `temporary_overrides` — batch version for multiple overrides

### Sentinel Pattern

Override default dependencies with a sentinel that fails loudly if the proper fixture wasn't loaded:

```python
class SessionFixtureDoesNotSetExplicitly: ...

def override_app_test_dependencies(app: FastAPI) -> None:
    deps = [DepOverride(dependency=get_session, override=lambda: SessionFixtureDoesNotSetExplicitly)]
    for dep in deps:
        override_dependency(app, dep.dependency, dep.override)
```

This catches missing fixture bugs early — if a test forgets to include the `session` fixture, it gets a clear error.

## App and Client Fixtures

```python
@pytest.fixture(scope='session')
async def app(_engine: AsyncEngine) -> AsyncGenerator[FastAPI, None]:
    from app.main import create_app
    _app = create_app()
    override_app_test_dependencies(_app)
    yield _app


@pytest.fixture(scope='session')
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client
```

Session-scoped — one app and client per test session. The `_engine` dependency comes from the database skill's fixtures.

## Coverage

Minimum 90% coverage enforced:

```bash
make test-coverage
# uv run pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
```

Run before opening PRs.

## Red Flags — STOP

These mean the test strategy is wrong. Stop and reconsider:

| About to… | Fix |
|---|---|
| Mock `AuthorService` in an API test | Use real service; mock only external I/O (LLMs, third-party APIs) |
| Use an in-memory SQLite fake instead of testcontainers Postgres | See `postgres-database` skill |
| Extract an assertion helper after seeing duplication twice | Wait for the 5th repetition; tests benefit from being explicit |
| Forget `model_dump(mode='json')` on a payload with dates/UUIDs | Serialization fails silently; always use `mode='json'` for HTTP |
| Share mutable state across tests via module-level fixtures | Fixtures must be function-scoped or produce fresh state |
| Call a real LLM from a test | Block with `ALLOW_MODEL_REQUESTS = False`; see `ai-agents` |
| Write `test_stuff()` without `test_success` / `test_fail_<reason>` | Rename — the test name is documentation |

## Gotchas

- `factory_use_construct=False` is needed when you want pydantic validators to run on factory-built objects
- The default `get_session` override raises a sentinel if the `session` fixture wasn't loaded — this catches missing fixture bugs early
- Session-scoped `app` and `client` fixtures mean the FastAPI app is created once and shared across all tests
- `model_dump(mode='json')` is required for proper serialization of dates, UUIDs, and enums in test assertions
