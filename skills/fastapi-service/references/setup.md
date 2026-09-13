# FastAPI Service Setup

The one-time wiring of a service: settings, lifespan, the exception-handler module, router aggregation, the app factory, and the shared list-sorting base. Written at bootstrap and rarely touched afterwards. Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules.

## Contents

- Settings
- Lifespan
- Exception handlers
- Router
- App factory
- List sorting

## Settings

`app/core/config.py` holds one `Settings` class for the whole service.

```python
from functools import lru_cache

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = 'Bookstore'
    PROJECT_VERSION: str = '0.1.0'
    DATABASE_URL: PostgresDsn  # DB projects only (postgres-database)
    MIGRATION_ON_STARTUP: bool = True  # DB projects only (postgres-database)

    model_config = SettingsConfigDict(case_sensitive=True, frozen=True, env_file='.env')


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- A field with no default is required, so a missing `DATABASE_URL` fails at startup with a validation error naming the variable rather than at the first query.
- `case_sensitive=True` matches the environment variables exactly as written; `frozen=True` keeps the shared instance from being mutated at runtime.
- `lru_cache` gives one instance per process, and `get_settings` doubles as a FastAPI dependency that tests can override.
- Type secrets as `pydantic.SecretStr` so they do not render in logs or tracebacks. Keep local values in `.env`, commit only a `dist.env` template.
- A service without a database drops `DATABASE_URL`, `MIGRATION_ON_STARTUP`, the `PostgresDsn` import, and the body of `startup` below; otherwise it fails at startup on a variable it has no use for.

## Lifespan

`app/core/lifespan.py` owns everything that happens around the request-serving window.

```python
import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from alembic.command import upgrade  # DB projects only (postgres-database)
from fastapi import FastAPI

from app.core.config import get_settings, Settings
from app.infrastructure.db.database import get_alembic_config  # DB projects only (postgres-database)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    await startup(settings)
    yield
    await shutdown()


async def startup(settings: Settings) -> None:
    if settings.MIGRATION_ON_STARTUP:  # DB projects only (postgres-database)
        alembic_config = get_alembic_config(settings.DATABASE_URL)
        await asyncio.to_thread(upgrade, alembic_config, 'head')


async def shutdown() -> None: ...
```

- `upgrade` is synchronous and holds the interpreter for the length of the migration, so `asyncio.to_thread` keeps it off the event loop. `get_alembic_config` belongs to `postgres-database`.
- Running migrations on startup suits a single-instance deployment. Turn `MIGRATION_ON_STARTUP` off and migrate from a release step where several replicas start at once, since concurrent `upgrade` calls contend on the same lock. Ship `MIGRATION_ON_STARTUP=False` in `dist.env` for anything but the local compose database, so `make run` against a shared `.env` does not migrate it as a side effect.

## Exception handlers

`app/core/exception_handlers.py` maps the domain exceptions from `SKILL.md` to responses and collects them into the mapping `create_app` passes to `FastAPI(exception_handlers=...)`.

```python
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from starlette import status

from app.core.exceptions import AlreadyExistError, NotFoundError

type ExceptionHandlers = dict[int | type[Exception], Callable[[Request, Any], Coroutine[Any, Any, Response]]]


async def not_found_exception_handler(request: Request, exc: NotFoundError) -> Response:
    http_exception = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc) or 'Not Found')
    return await http_exception_handler(request, http_exception)


async def conflict_exception_handler(request: Request, exc: AlreadyExistError) -> Response:
    http_exception = HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or 'Conflict')
    return await http_exception_handler(request, http_exception)


EXCEPTION_HANDLERS: ExceptionHandlers = {
    NotFoundError: not_found_exception_handler,
    AlreadyExistError: conflict_exception_handler,
}
```

- `ExceptionHandlers` is the alias the app factory's argument expects; `Any` for the second handler parameter is the signature Starlette calls with, not a modelling shortcut.
- `SKILL.md` holds the rules that go with this module: why a handler returns rather than raises, why registration order is irrelevant, and what a mounted sub-application needs.

## Router

`app/router.py` aggregates the domain routers. Business routes are versioned; health and readiness endpoints stay outside `/v1`, because a probe URL is not part of the API contract and must survive the next version bump.

```python
from fastapi import APIRouter

from app.domains.books.routes import router as books_router
from app.domains.health_checks.routes import router as health_checks_router


def create_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health_checks_router)

    router_v1 = APIRouter(prefix='/v1')
    router_v1.include_router(books_router)
    router.include_router(router_v1)
    return router
```

## App factory

`app/main.py` builds the application inside a function, so no application state exists at import time and every test gets an isolated app. Uvicorn points at the factory (`app.main:create_app` with `factory=True`), and tests call it directly.

```python
from fastapi import FastAPI
from fastapi_pagination import add_pagination
import uvicorn

from app.core.config import get_settings
from app.core.exception_handlers import EXCEPTION_HANDLERS
from app.core.lifespan import lifespan
from app.router import create_router


def create_app() -> FastAPI:
    settings = get_settings()
    _app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        lifespan=lifespan,
        exception_handlers=EXCEPTION_HANDLERS,
    )
    _app.include_router(create_router())
    add_pagination(_app)
    return _app


if __name__ == '__main__':
    uvicorn.run('app.main:create_app', factory=True, host='0.0.0.0', port=8000)  # noqa: S104
```

- `add_pagination` runs after `include_router` because it walks the routes already registered on the app.
- The `__main__` block is what `python -m app.main` runs; without it the module imports and exits without serving. `# noqa: S104` records that binding all interfaces is intended for a containerised process.

## List sorting

`app/core/schemas.py` holds the sorting base each feature narrows with its own `sort_by` `Literal`, which is what rejects an unknown column with a 422 before `getattr` runs. `SKILL.md` shows the narrowed schema and the route that takes it.

```python
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, Select

from app.infrastructure.db.database import Base

type SortingOrder = Literal['asc', 'desc']


class BaseListSorting(BaseModel):
    sort_by: str = Field(description='Sorting field')
    sort_order: SortingOrder = Field(default='desc', description='Sorting direction')

    def sort_query(self, query: Select, model: type[Base]) -> Select:
        direction = asc if self.sort_order == 'asc' else desc
        order_column = getattr(model, self.sort_by)
        return query.order_by(direction(order_column))
```
