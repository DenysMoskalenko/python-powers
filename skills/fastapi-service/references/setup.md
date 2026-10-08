# FastAPI Service Setup

Reference for one-time project wiring — written once at bootstrap, rarely touched afterward. Load this when setting up a service's configuration, router wiring, or app factory.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- `pydantic-settings` configuration (`Settings` + `lru_cache`d `get_settings`)
- `setup_routers()` — includes the module routers into the app
- `create_app()` — the app factory

## Configuration

Use `pydantic-settings` with `.env` file. Cache with `lru_cache`:

```python
from functools import lru_cache
from importlib.metadata import version

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = 'my-service'
    PROJECT_VERSION: str = Field(default_factory=lambda: version('my-service'))
    DATABASE_URL: PostgresDsn
    OPENAI_API_KEY: SecretStr

    model_config = SettingsConfigDict(case_sensitive=True, frozen=True, env_file='.env')


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- `PROJECT_VERSION` is read from the installed package metadata, so `pyproject.toml` is the only place to bump it; this needs the project installed (a `[build-system]` table, as the template has), and an env var still overrides it
- `frozen=True` prevents mutation
- `SecretStr` for sensitive values — never log or expose
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
