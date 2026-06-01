---
name: fastapi-service
description: Use when building or modifying a FastAPI service without a repository layer — adding routes, services, Pydantic schemas, exception handlers, pydantic-settings configuration, dependency injection, or project structure. For SQLAlchemy models and migrations see `postgres-database`; for pydantic-ai agents see `ai-agents`.
---

# FastAPI Service Patterns

Patterns for building FastAPI services where services own business logic directly. No repository layer — keep it simple.

> Requires Python 3.13+, FastAPI, Pydantic, pydantic-settings.
> Examples use `app/` as the top-level package. Substitute your package name if different.

**Related**: `python-code-style`, `python-testing`, `postgres-database`, `ai-agents`, `project-scaffolding`.

## Architecture

```text
Routes (thin HTTP handlers)
  → Services (business logic + queries)
    → Models (ORM or external)
```

Routes parse HTTP requests into typed schemas and delegate to services. Services contain all business logic and raise domain exceptions (never HTTP codes). Exception handlers translate domain errors to HTTP responses.

## Project Structure

Package-by-feature: each module under `app/modules/` is one self-contained vertical slice — business CRUD, an AI agent, or operational. Cross-cutting technical code lives outside it — `app/core/` (config, exceptions, exception handlers, shared schemas, lifespan) and `app/infrastructure/` (db, llms). A business change touches one module folder; an infra change touches one infra folder.

```text
app/
  main.py                  # create_app() — FastAPI app factory
  router.py                # create_router() — aggregates module routers
  modules/
    <module>/              # one vertical slice per module
      routes.py            # thin HTTP handlers
      schemas.py           # request/response + internal Pydantic models
      service.py           # business logic + queries
  core/                    # config, exceptions, exception_handlers, schemas, lifespan
  infrastructure/
    db/                    # engine, session, models/ (see postgres-database)
    llms/                  # LLM providers + registry (see ai-agents)
```

SQLAlchemy models are the one deliberate exception to "everything in the module folder" — they stay centralized in `app/infrastructure/db/models/` so Alembic autogenerates from one metadata and cross-model relationships need no cross-module imports.

### Module growth

Start flat: a module is three files (`routes.py`, `schemas.py`, `service.py`). Promote a concern to a subpackage **only once it splits into 2+ files** (e.g. `books/services/` holding `service_books.py` + `service_books_validator.py`). When a subpackage appears:

- **Facade `__init__.py`** re-exports public symbols via `__all__`. External callers import from the package root (`from app.modules.books.services import BooksService`), never the deep path.
- **Internal siblings import directly** (`from .service_books import BooksService`), never through their own facade — this avoids circular imports during package init.
- **Keep the descriptive filename prefix** (`service_books.py`, not `books.py`) so files stay unambiguous in search and editor tabs.

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
- Return type annotations match the response schema
- POST returns 201, DELETE returns 204 with `response_class=Response`

## Services

Services are classes that accept their dependencies via `Depends()`. They contain all business logic and raise domain exceptions.

```python
from typing import Annotated

from fastapi import Depends

from app.core.exceptions import AlreadyExistError, NotFoundError


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
        await self._validate_author_unique(creation)
        query = insert(AuthorModel).values(**creation.model_dump()).returning(AuthorModel)
        author = await self._session.scalar(query)
        return Author.model_validate(author)

    async def _validate_author_unique(self, creation: AuthorCreate) -> None:
        ...
```

Key patterns:
- Domain exceptions (`NotFoundError`, `AlreadyExistError`) — never `HTTPException` in services
- Request-scoped services that receive `get_session` do not call `commit()` or `rollback()`; the session provider owns that transaction boundary
- Logging for non-critical situations (e.g., delete of non-existent entity)

## Schemas

Schemas live in the module's `schemas.py`. Follow this inheritance pattern:

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

## Setup

See `reference/setup.md` for one-time project wiring: `pydantic-settings` configuration (`Settings` + `lru_cache`d `get_settings`), the `create_router()` aggregator (business modules under `/v1`, operational endpoints unversioned), and the `create_app()` factory (register exception handlers **last** so they wrap all routers and middleware).

## Red Flags — STOP

These mean the service boundary is drifting. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Put validation, lookup, or branching business logic in a route | Routes — inject the service, call one method, return the result |
| Raise `HTTPException` inside a service | Exceptions — services raise domain exceptions only |
| Add a repository layer "for cleanliness" | Architecture — services own business logic and queries directly |
| Split one feature's routes, schemas, and service across separate top-level layers | Project Structure — each module is one self-contained vertical slice |
| Import a subpackage's internals from outside via its deep path, or route an internal sibling import through its own facade | Module growth — outside callers import the facade; internal siblings import directly |
| Put request/response schemas outside their module | Schemas — colocate schemas in the module's `schemas.py` |
| Use bare `str` for `sort_by` or other constrained query fields | Schemas — use `Literal[...]` for local constrained values |
| Register exception handlers before routers or middleware | Setup — register handlers last |
| Return ORM models without a response schema | Schemas — response models use `ConfigDict(from_attributes=True)` |

## Gotchas

- `Annotated[Service, Depends()]` with empty `Depends()` triggers FastAPI auto-injection of the service's own dependencies
- Filter/sorting schemas as `Depends()` parameters parse query strings into typed models automatically
