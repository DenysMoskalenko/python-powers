# FastAPI Service Setup

Reference for one-time project wiring — written once at bootstrap, rarely touched afterward. Load this when setting up a service's configuration, router wiring, app factory, lifespan, or health checks.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- `pydantic-settings` configuration (`Settings` + `lru_cache`d `get_settings`)
- `setup_routers()` — includes the module routers into the app
- `create_app()` — the app factory, the global request body limit, and the `lifespan`
- Health checks — liveness and the database readiness probe

## Configuration

Use one `pydantic-settings` class per integration, each with its own `env_prefix`, nested into a root `Settings` and loaded from a `.env` file. Cache with `lru_cache`:

```python
from functools import lru_cache
from importlib.metadata import version

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class _EnvSettings(BaseSettings):
    # Every class receives the whole `.env` as input, so any validation error could print another class's secret.
    model_config = SettingsConfigDict(
        env_file='.env', env_ignore_empty=True, extra='ignore', frozen=True, hide_input_in_errors=True
    )


class OpenAISettings(_EnvSettings):
    model_config = SettingsConfigDict(env_prefix='OPENAI_')

    api_key: SecretStr
    timeout_seconds: float = Field(default=180.0, gt=0)


class Settings(_EnvSettings):
    PROJECT_NAME: str = 'my-service'
    PROJECT_VERSION: str = Field(default_factory=lambda: version('my-service'))

    OPENAI: OpenAISettings = Field(default_factory=OpenAISettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- `PROJECT_VERSION` is read from the installed package metadata, so `pyproject.toml` is the only place to bump it; this needs the project installed (a `[build-system]` table, as the template has), and an env var still overrides it
- Each integration's fields live in its own class, read as `settings.OPENAI.api_key`; the env name stays `OPENAI_API_KEY` through `env_prefix`, and only application-wide fields stay on the root
- `frozen=True` prevents mutation; `extra='ignore'` because every class reads the same `.env`; `env_ignore_empty=True` so a blank `.env` line falls back to the default
- Put the unit in the name and the bound on the field: `timeout_seconds: float = Field(default=10.0, gt=0)`
- `SecretStr` for every credential — `repr` and dumps show `**********`; call `.get_secret_value()` only where the value is consumed, never log or expose it
- Every class inherits `_EnvSettings`: `SecretStr` masks only after validation, and each class also receives the other classes' `.env` keys as input, so without `hide_input_in_errors=True` any `ValidationError` can print a raw secret into logs and AI session transcripts
- Use `dist.env` as the template, never commit `.env`

## Router

`app/router.py` includes every module router into the app directly — business modules under `/v1`, operational endpoints (health checks) unversioned. Never nest routers through an intermediate `APIRouter`: every nested `include_router` level keeps another copy of each route and its `Depends()` tree, so nesting multiplies route memory per worker for an identical OpenAPI schema. Inclusion order is matching order — a router whose literal paths another router's path parameter would match goes first.

```python
from fastapi import FastAPI

from app.domains.authors.routes import router as authors_router
from app.domains.books.routes import router as books_router
from app.domains.health_checks.routes import router as health_checks_router


def setup_routers(app: FastAPI) -> None:
    app.include_router(health_checks_router)  # unversioned — operational, not a v1 API contract
    app.include_router(authors_router, prefix='/v1')
    app.include_router(books_router, prefix='/v1')
```

## App Factory

`create_app()` sets the global request body limit, wires the routers, and registers exception handlers (their order relative to routers and middleware does not matter):

```python
def create_app() -> FastAPI:
    settings = get_settings()
    _app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        max_body_size=1 * 1024 * 1024,
        lifespan=lifespan,
    )
    setup_routers(_app)
    add_pagination(_app)
    include_exception_handlers(_app)
    return _app
```

- Every app sets `max_body_size` (bytes): FastAPI reads a body of any size by default; with the limit, a larger one answers 413
- A route that needs more sets its own — `APIRouter(max_body_size=...)`, `include_router(..., max_body_size=...)`, or the path operation; the app's limit stays small
- Middleware that reads the body runs under the app's limit, whatever the route allows — the one case where the app's limit rises to fit the uploads and every other router sets the small one

`lifespan` builds every `lru_cache`d client at startup and closes them all at shutdown, from a `finally`, so a startup that fails halfway still closes what it built:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, AsyncExitStack

from fastapi import FastAPI

from app.core.config import get_settings, Settings
from app.infrastructure.db.database import async_session_factory, close_database
from app.infrastructure.llms.provider_openai import close_openai_client, get_openai_client


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    try:
        await startup(settings)
        yield
    finally:
        await shutdown()


async def startup(settings: Settings) -> None:
    async_session_factory()
    # FastAPI resolves sync dependencies in threads, where concurrent first requests would each build a client.
    get_openai_client(settings=settings)


async def shutdown() -> None:
    async with AsyncExitStack() as clients:  # every client closes even when an earlier one fails to
        clients.push_async_callback(close_openai_client)
        clients.push_async_callback(close_database)
```

Call a cached dependency by keyword outside FastAPI too: FastAPI calls dependencies with keyword arguments, which `lru_cache` keys apart from positional ones, so `get_openai_client(settings)` would build a second client. Each `close_*` function gets its client the same way (`get_openai_client(settings=get_settings())`), closes it (`await client.close()`, `await engine.dispose()`), and clears the getter's `lru_cache` in a `finally`, so the next startup builds a fresh client instead of reusing a closed one; `close_database` is in `postgres-database`.

## Health checks

`app/domains/health_checks/` serves two unversioned routes. `/health/live` answers a static `UP`. `/health/ready` checks only what every request needs: the database. Never check a provider or auth server that only some routes call (OpenAI, Bedrock, Keycloak): its outage would take all pods out of traffic at once, the routes that never call it included. A service without a database answers a static `READY`.

The readiness route takes `session: Annotated[AsyncSession, Depends(get_session, scope='function')]`, documents its 503 with `responses={status.HTTP_503_SERVICE_UNAVAILABLE: {'model': HealthCheckReadyResponse}}`, and sets `response.status_code` to 503 when the probe in the module's `service.py` returns `DOWN`:

```python
async def check_database_status(session: AsyncSession, timeout_seconds: float) -> LivenessStatus:
    # One line without a traceback, newlines escaped by %r: the kubelet probes every few seconds.
    try:
        async with asyncio.timeout(timeout_seconds):
            await session.execute(text('SELECT 1'))
    except TimeoutError:  # before OSError, its base class
        _logger.warning('Readiness check: the database did not answer within %ss', timeout_seconds)
    except (SQLAlchemyError, OSError) as exc:
        _logger.warning('Readiness check: the database is down: %s: %r', type(exc).__name__, str(exc))
    else:
        return 'UP'
    await session.rollback()  # the probe returns instead of raising, so get_session would otherwise commit
    return 'DOWN'
```

A missed deadline or a `SQLAlchemyError` / `OSError` answers `DOWN`; any other exception is a bug in the probe and should answer 500. The deadline is not a hard bound: on a server that stops answering, psycopg's cancel holds a probe past it. With OpenTelemetry, run the query inside `suppress_instrumentation()` (`opentelemetry.instrumentation.utils`) so probes record no spans.
