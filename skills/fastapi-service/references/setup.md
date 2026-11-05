# FastAPI Service Setup

Reference for one-time project wiring — written once at bootstrap, rarely touched afterward. Load this when setting up a service's configuration, router wiring, or app factory.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- `pydantic-settings` configuration (`Settings` + `lru_cache`d `get_settings`)
- `setup_routers()` — includes the module routers into the app
- `create_app()` — the app factory

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
- Bound each `/health/ready` dependency check with `asyncio.timeout()` so a dead dependency answers 503
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

`create_app()` wires the routers and registers exception handlers (their order relative to routers and middleware does not matter):

```python
def create_app() -> FastAPI:
    settings = get_settings()
    _app = FastAPI(title=settings.PROJECT_NAME, version=settings.PROJECT_VERSION, lifespan=lifespan)
    setup_routers(_app)
    add_pagination(_app)
    include_exception_handlers(_app)
    return _app
```
