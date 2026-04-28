---
name: fastapi-service
description: >
  Use when building or modifying a FastAPI service without a repository
  layer — adding routes, services, Pydantic schemas, exception handlers,
  pydantic-settings configuration, dependency injection, or project
  structure. For SQLAlchemy models and migrations see `postgres-database`;
  for pydantic-ai agents see `ai-agents`.
---

# FastAPI Service Patterns

Patterns for building FastAPI services where services own business logic directly. No repository layer — keep it simple.

> Requires Python 3.13+, FastAPI, Pydantic, pydantic-settings.
> Examples use `app/` as the top-level package. Substitute your package name if different.

**Related**: `python-code-style`, `python-testing`, `postgres-database`, `ai-agents`.

## When to use

Load this skill when:
- Adding a new domain entity with routes, service, and schemas
- Wiring a new FastAPI dependency
- Designing request/response schemas or an exception handler
- Reviewing a route that leaks business logic or HTTP details

For SQLAlchemy models and queries use `postgres-database`. For pydantic-ai agents use `ai-agents`.

## Architecture

```text
Routes (thin HTTP handlers)
  → Services (business logic + queries)
    → Models (ORM or external)
```

Routes parse HTTP requests into typed schemas and delegate to services. Services contain all business logic and raise domain exceptions (never HTTP codes). Exception handlers translate domain errors to HTTP responses.

## Project Structure

```text
app/
  main.py                          # FastAPI app factory
  api/
    v1/
      __init__.py                  # create_v1_router() aggregates domain routers
      <domain>/
        __init__.py
        routes.py                  # Thin route handlers
        schemas.py                 # Request/response Pydantic models
  services/
    <domain>_service.py            # Business logic
  core/
    config.py                      # pydantic-settings configuration
    exceptions.py                  # Domain exception classes
    exception_handlers.py          # Domain → HTTP status translation
    schemas.py                     # Shared schema base classes
    lifespan.py                    # App startup/shutdown
  infrastructure/
    db/                            # Database (see postgres-database skill)
    llms/                          # LLM providers (see ai-agents skill)
```

Each domain gets its own folder under `app/api/v1/` with `routes.py` and `schemas.py`. Services live in `app/services/`.

## Routes

Routes are thin. They inject the service via `Depends()`, call one service method, and return the result. No business logic in routes.

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import Response

router = APIRouter(tags=['Authors'])


@router.post('/authors', status_code=201)
async def add_author(creation: AuthorCreate, service: Annotated[AuthorService, Depends()]) -> Author:
    return await service.create_author(creation)


@router.get('/authors/{author_id}')
async def get_author(author_id: int, service: Annotated[AuthorService, Depends()]) -> Author:
    return await service.get_author_by_id(author_id)


@router.delete('/authors/{author_id}', response_class=Response, status_code=204)
async def delete_author(author_id: int, service: Annotated[AuthorService, Depends()]) -> None:
    await service.delete_author_by_id(author_id)
```

Key patterns:
- `Annotated[Service, Depends()]` — FastAPI auto-instantiates the service with its own dependencies
- Filter/sorting models as `Depends()` — query parameters parsed into typed models
- Return type annotations match the response schema
- POST returns 201, DELETE returns 204 with `response_class=Response`

## Services

Services are classes that accept their dependencies via `Depends()`. They contain all business logic and raise domain exceptions.

```python
from logging import getLogger
from typing import Annotated

from fastapi import Depends

from app.core.exceptions import AlreadyExistError, NotFoundError

_logger = getLogger(__name__)


class AuthorService:
    def __init__(self, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
        self._session = session

    async def get_author_by_id(self, author_id: int) -> Author:
        query = select(AuthorModel).filter(AuthorModel.id == author_id)
        author = await self._session.scalar(query)
        if author is None:
            raise NotFoundError(f'Author(id={author_id}) not found')
        return Author.model_validate(author)

    async def create_author(self, creation: AuthorCreate) -> Author:
        async with self._session.begin_nested():
            await self._validate_author_unique(creation)
            query = insert(AuthorModel).values(**creation.model_dump()).returning(AuthorModel)
            author = await self._session.scalar(query)
        return Author.model_validate(author)

    async def _validate_author_unique(self, creation: AuthorCreate) -> None:
        ...
```

Key patterns:
- Domain exceptions (`NotFoundError`, `AlreadyExistError`) — never `HTTPException` in services
- Public methods first, private methods after (class interface at the top)
- Logging for non-critical situations (e.g., delete of non-existent entity)

## Schemas

Schemas live next to their routes in `<domain>/schemas.py`. Follow this inheritance pattern:

```python
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, computed_field, ConfigDict, Field, field_validator


class _AuthorBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=64, examples=['Jane'])
    last_name: str = Field(min_length=1, max_length=64, examples=['Austen'])
    description: str = Field(min_length=1, max_length=512, examples=['English novelist'])
    birthday: date | None = Field(default=None, examples=[date(year=1775, month=12, day=16)])


class AuthorCreate(_AuthorBase):
    @field_validator('birthday')
    @classmethod
    def validate_birthday(cls, birthday: date | None) -> date | None:
        if birthday is not None and birthday > datetime.now(UTC).date():
            raise ValueError('Author cannot be born in the future')
        return birthday


class AuthorUpdate(AuthorCreate):
    pass


class Author(_AuthorBase):
    id: int = Field(description='Author identifier')
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def name(self) -> str:
        return ' '.join(part for part in [self.first_name, self.last_name] if part)


class AuthorListFilters(BaseModel):
    ids: list[int] | None = Field(default=None, description='Filter by author ids')
    name: str | None = Field(default=None, min_length=1, max_length=193, description='Filter by full name')
    created_from: datetime | None = Field(default=None, description='Filter by created at lower bound')
    created_to: datetime | None = Field(default=None, description='Filter by created at upper bound')


class AuthorListSorting(BaseListSorting):
    sort_by: Literal['name', 'first_name', 'last_name', 'created_at', 'updated_at'] = Field(
        default='created_at', description='Sorting field'
    )
```

Pattern:
- `_EntityBase` — shared schema base class; the leading `_` marks the base class as module-internal, not the fields
- `EntityCreate` — input for creation, inherits base, adds validators
- `EntityUpdate` — input for update (often same as Create)
- `Entity` — response model with `id`, timestamps, `from_attributes=True`
- `EntityListFilters` — query params for filtering
- `EntityListSorting` — inherits `BaseListSorting`, constrains `sort_by` with `Literal`
- Always use `Field()` with `min_length`, `max_length`, `examples`, `description`

## Exceptions

Domain exceptions in `app/core/exceptions.py` — minimal, no HTTP awareness:

```python
class BaseServiceError(Exception):
    pass

class NotFoundError(BaseServiceError):
    pass

class AlreadyExistError(BaseServiceError):
    pass
```

Exception handlers in `app/core/exception_handlers.py` translate to HTTP:

```python
def not_found_exception_handler(request: Request, exc: NotFoundError) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc) or 'Not Found') from exc

def conflict_exception_handler(request: Request, exc: AlreadyExistError) -> None:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or 'Conflict') from exc
```

Register handlers in `create_app()` — keep at the end so they wrap all middleware/routers.

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

## App Factory

```python
def create_app() -> FastAPI:
    settings = get_settings()
    _app = FastAPI(title=settings.PROJECT_NAME, version=settings.PROJECT_VERSION, lifespan=lifespan)
    _app.include_router(create_v1_router())
    add_pagination(_app)
    include_exception_handlers(_app)
    return _app
```

Exception handlers must be registered last to wrap all middleware/routers.

## Red Flags — STOP

These mean the service boundary is drifting. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Put validation, lookup, or branching business logic in a route | Routes — inject the service, call one method, return the result |
| Raise `HTTPException` inside a service | Exceptions — services raise domain exceptions only |
| Add a repository layer "for cleanliness" | Architecture — services own business logic and queries directly |
| Put request/response schemas outside the domain route package | Schemas — colocate schemas with routes in `app/api/v1/<domain>/schemas.py` |
| Use bare `str` for `sort_by` or other constrained query fields | Schemas — use `Literal[...]` for local constrained values |
| Register exception handlers before routers or middleware | App Factory — register handlers last |
| Return ORM models without a response schema | Schemas — response models use `ConfigDict(from_attributes=True)` |

## Gotchas

- Services raise domain exceptions, never `HTTPException` — the exception handler layer does the translation
- Registration order in `create_app()` matters — exception handlers must be last
- `Annotated[Service, Depends()]` with empty `Depends()` triggers FastAPI auto-injection of the service's own dependencies
- Filter/sorting schemas as `Depends()` parameters parse query strings into typed models automatically
