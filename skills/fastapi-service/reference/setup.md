# FastAPI Service Setup

Reference for one-time project wiring — written once at bootstrap, rarely touched afterward. Load this when setting up a service's configuration, router aggregation, or app factory.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- `pydantic-settings` configuration (`Settings` + `lru_cache`d `get_settings`)
- `create_router()` — aggregates the module routers
- `create_app()` — the app factory

## Configuration

Use `pydantic-settings` with `.env` file. Cache with `lru_cache`:

```python
from functools import lru_cache

from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: PostgresDsn
    OPENAI_API_KEY: SecretStr

    model_config = SettingsConfigDict(case_sensitive=True, frozen=True, env_file='.env')


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- `frozen=True` prevents mutation
- `SecretStr` for sensitive values — never log or expose
- Use `dist.env` as the template, never commit `.env`

## Router

`app/router.py` aggregates the module routers — business modules under `/v1`, operational endpoints (health checks) unversioned:

```python
from fastapi import APIRouter

from app.modules.authors.routes import router as authors_router
from app.modules.books.routes import router as books_router
from app.modules.health_checks.routes import router as health_checks_router


def create_router() -> APIRouter:
    router_v1 = APIRouter(prefix='/v1')
    router_v1.include_router(authors_router)
    router_v1.include_router(books_router)

    router = APIRouter()
    router.include_router(health_checks_router)  # unversioned — operational, not a v1 API contract
    router.include_router(router_v1)
    return router
```

## App Factory

`create_app()` mounts the aggregated router, then registers exception handlers **last** so they wrap all middleware and routers:

```python
def create_app() -> FastAPI:
    settings = get_settings()
    _app = FastAPI(title=settings.PROJECT_NAME, version=settings.PROJECT_VERSION, lifespan=lifespan)
    _app.include_router(create_router())
    add_pagination(_app)
    include_exception_handlers(_app)
    return _app
```
