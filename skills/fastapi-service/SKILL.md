---
name: fastapi-service
description: Use when adding or changing a FastAPI endpoint (`routes.py`, `service.py`, `schemas.py`) — thin routes, service classes, Pydantic schemas, query-parameter models, PATCH semantics, status codes, domain exception handlers, pydantic-settings configuration, lifespan, and the app factory. For SQLAlchemy models and queries see `postgres-database`; for pydantic-ai agents see `ai-agents`.
---

# FastAPI Service Patterns

How an HTTP request travels through this house's services: a thin route parses it into a typed schema and calls one service method; the service holds the business logic and its queries and signals failure by raising a domain exception; an exception handler turns that into a status code. There is no repository layer — the service owns data access. An explicit user or project instruction (`AGENTS.md`, `pyproject.toml`, existing code) overrides a house default here; keep the invariants that still apply and name the default you departed from.

> Requires Python 3.13+, FastAPI, Pydantic, pydantic-settings, fastapi-pagination, uvicorn.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `python-testing`, `postgres-database`, `ai-agents`, `project-scaffolding`.

## Layout

Package by feature: each folder under `app/domains/` is one vertical slice, so a business change touches one folder; cross-cutting technical code lives in `app/core/` and `app/infrastructure/`.

```text
app/
  main.py                  # create_app() — the app factory
  router.py                # create_router() — aggregates the domain routers
  domains/
    <feature>/
      routes.py            # thin HTTP handlers
      schemas.py           # request, response and internal Pydantic models
      service.py           # business logic and queries
  core/                    # config, exceptions, exception_handlers, schemas, enums, lifespan
  infrastructure/
    db/                    # engine, session providers, models/ (see postgres-database)
    llms/                  # providers and model registry (see ai-agents)
```

SQLAlchemy models are the deliberate exception: they stay in `app/infrastructure/db/models/` so Alembic autogenerates from a single metadata and cross-entity relationships need no cross-domain imports.

Start flat with those three files. Promote a concern to a subpackage once it splits into two or more files — `books/services/` holding `service_books.py` and `service_books_validator.py` — with an `__init__.py` facade re-exporting the public names through `__all__`, so outside callers import from the package root (`from app.domains.books.services import BookService`). Siblings inside the package import each other directly (`from .service_books import BookService`) to avoid circular imports. Keep the descriptive filename prefix so a file is unambiguous in search results.

In a project that already uses a different layout, add the endpoint where its siblings live and do not migrate the tree; propose the move separately.

## Routes

A route translates HTTP into one service call and back; validation, lookups, and branching belong to the service.

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi_pagination import Page, Params

from app.domains.books.schemas import (
    Book,
    BookCreate,
    BookDetail,
    BookListFilters,
    BookListSorting,
    BookPatch,
    BookWithAuthor,
)
from app.domains.books.service import BookService

router = APIRouter(tags=['Books'])


@router.post('/books', status_code=201)
async def add_book(creation: BookCreate, service: Annotated[BookService, Depends()]) -> Book:
    return await service.create_book(creation)


@router.get('/books')
async def list_books(
    filters: Annotated[BookListFilters, Query()],
    sorting: Annotated[BookListSorting, Depends()],
    pagination_params: Annotated[Params, Depends()],
    service: Annotated[BookService, Depends()],
) -> Page[BookWithAuthor]:
    return await service.list_books(filters, sorting, pagination_params)


@router.get('/books/{book_id}')
async def get_book(book_id: int, service: Annotated[BookService, Depends()]) -> BookDetail:
    return await service.get_book_by_id(book_id)


@router.patch('/books/{book_id}')
async def change_book(book_id: int, updates: BookPatch, service: Annotated[BookService, Depends()]) -> Book:
    return await service.patch_book(book_id, updates)


@router.delete('/authors/{author_id}', response_class=Response, status_code=204)
async def delete_author(author_id: int, service: Annotated[BookService, Depends()]) -> None:
    await service.delete_author_by_id(author_id)
```

- `Annotated[BookService, Depends()]` with an empty `Depends()` instantiates the service and resolves its constructor dependencies, so the route never names the session.
- The return annotation is the response model. A POST that creates returns 201; a DELETE returns 204 with `response_class=Response` to document that there is no body model. A delete that matched no row still answers 204, because the caller's goal already holds; `postgres-database` owns that default.

### Query-parameter models

FastAPI expands a `Query()` parameter model into its fields only when it is the route's only direct query parameter. A second `Query()` model or a bare scalar such as `limit: int = 10` beside it stops the expansion, and every request answers 422 with `Field required` per unexpanded model. Query parameters arriving through a `Depends()` sub-dependency (`*ListSorting`, `fastapi_pagination.Params`) are the exception: parsing stays intact, and the only cost is that the `Query()` model shows in `/docs` as one opaque parameter beside them — which a paginated route always pays, through `page` and `size`.

So give `Query()` to the one model that carries a `list[...]` field, as `list_books` does, and keep every other query-reading model on `Depends()`. `Depends()` on a model with a `list[...]` field moves that field into the JSON body, so `?ids=1&ids=2` answers 200 with `ids` set to `None`. When no field is a list, `Depends()` is the better spelling: both parse, but `Depends()` renders each filter as its own parameter in `/docs`. Two models that each need `Query()` merge into one filters model.

## Services

A service is a class whose collaborators arrive through `Depends()`. It owns the business logic and its queries; `postgres-database` owns the query patterns — filtering, pagination, loading strategy, insert-returning writes.

```python
from logging import getLogger
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import NotFoundError
from app.domains.books.schemas import BookDetail
from app.infrastructure.db.database import get_session
from app.infrastructure.db.models.book import BookModel

_logger = getLogger(__name__)


class BookService:
    def __init__(self, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
        self._session = session

    async def get_book_by_id(self, book_id: int) -> BookDetail:
        query = (
            select(BookModel)
            .options(joinedload(BookModel.author), joinedload(BookModel.cover))
            .filter(BookModel.id == book_id)
        )
        book = await self._session.scalar(query)
        if book is None:
            raise NotFoundError(f'Book(id={book_id}) not found')
        return BookDetail.model_validate(book)
```

- Services raise domain exceptions; `HTTPException` never appears below the route layer, so the same method works from a worker, a CLI, or a test, and the status code is decided in one place.
- A request-scoped service does not call `commit()` or `rollback()`; `postgres-database` owns the transaction boundary in `open_db_session`.
- Log at `info` where an operator needs the event later: a situation the service tolerates (a delete that matched no row, a retry) and a write that creates or destroys something. Give it an f-string message that reads on its own and repeat the identifiers under `extra={'extra': {...}}`: a top-level `extra` key makes `Logger.makeRecord` raise `KeyError` as soon as it collides with a `LogRecord` attribute (`name`, `module`, `args`, `filename`, and the rest), and the nesting gives JSON formatters one stable key.

```python
_logger.info(
    f'Author(id={author_id}) requested for deletion was not found',
    extra={'extra': {'author_id': author_id}},
)
```

## Schemas

Schemas live in the feature's `schemas.py`; one private base holds the shared fields and the create and response models derive from it.

```python
from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import BaseListSorting


class _BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=256, examples=['A Wizard of Earthsea'])
    published_year: int | None = Field(default=None, ge=1450, le=2200, examples=[1968])


class BookCreate(_BookBase):
    author_id: int = Field(description='Owning author identifier')


class BookPatch(BaseModel):
    title: str = Field(  # ty: ignore[invalid-assignment]
        default=None, min_length=1, max_length=256, examples=['A Wizard of Earthsea']
    )
    published_year: int | None = Field(default=None, ge=1450, le=2200, examples=[1968])


class Book(_BookBase):
    id: int = Field(description='Book identifier')
    author_id: int = Field(description='Owning author identifier')
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class _AuthorBase(BaseModel):
    name: str = Field(min_length=1, max_length=128, examples=['Ursula K. Le Guin'])


class AuthorCreate(_AuthorBase):
    pass


class Author(_AuthorBase):
    id: int = Field(description='Author identifier')
    model_config = ConfigDict(from_attributes=True)


class Cover(BaseModel):
    id: uuid.UUID = Field(description='Cover identifier')
    image_url: str = Field(min_length=1, max_length=512, examples=['https://example.test/earthsea.png'])
    model_config = ConfigDict(from_attributes=True)


class BookWithAuthor(Book):
    author: Author


class BookDetail(BookWithAuthor):
    cover: Cover | None = Field(default=None)


class BookListFilters(BaseModel):
    ids: list[int] | None = Field(default=None, description='Filter by book ids')
    title: str | None = Field(default=None, min_length=1, max_length=256, description='Filter by title')
    author_id: int | None = Field(default=None, description='Filter by owning author id')
    created_from: datetime | None = Field(default=None, description='Filter by created at lower bound')


class BookListSorting(BaseListSorting):
    sort_by: Literal['title', 'published_year', 'created_at', 'updated_at'] = Field(
        default='created_at', description='Sorting field'
    )
```

- `BookPatch` is declared separately with every field optional rather than inherited from `BookCreate`: inheriting keeps each field required and turns PATCH into a full replacement.
- A patch field whose column is NOT NULL keeps the column's type and takes `default=None` (`title: str`): pydantic does not validate a default, so an omitted field stays unset for `model_dump(exclude_unset=True)` while a sent `null` is a 422 instead of an `IntegrityError`; `ty` flags the mismatch, hence the suppression. A nullable column's field is `T | None`.
- A response model carries `ConfigDict(from_attributes=True)` and is what the service returns; an ORM object never leaves the service.
- Constrain string inputs with `min_length` and `max_length` and give input fields `examples` so `/docs` is usable; server-owned response fields need neither. `sort_by` is a `Literal`, so an unknown column is a 422 at the boundary.

`BaseListSorting` is the shared base in `app/core/schemas.py` that each feature narrows; `references/setup.md` holds it and `sort_query`.

## Exceptions

Domain exceptions live in `app/core/exceptions.py` and know nothing about HTTP:

```python
class BaseServiceError(Exception):
    pass


class NotFoundError(BaseServiceError):
    pass


class AlreadyExistError(BaseServiceError):
    pass
```

Handlers in `app/core/exception_handlers.py` map them to responses and are collected into one `EXCEPTION_HANDLERS` mapping passed to `FastAPI(exception_handlers=EXCEPTION_HANDLERS)`; `references/setup.md` holds that module.

- A handler returns the response rather than raising; that form type-checks as written, with no `cast` or `NoReturn`.
- Registration order is irrelevant: `add_exception_handler` and `exception_handlers=` both only fill a dictionary Starlette reads on the first request, so "register last to wrap the routers" changes nothing.
- A mounted sub-application needs the same handlers registered on it: it is a full ASGI app with its own `ServerErrorMiddleware`, which writes a 500 before the parent's handlers are consulted.

## Setup

`references/setup.md` covers the one-time wiring — `Settings` with `lru_cache`d `get_settings`, `lifespan`, the `exception_handlers` module, `create_router()`, `create_app()`, and `BaseListSorting`. Load it when bootstrapping a service or changing configuration, exception mapping, routing prefixes, startup, or sorting.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| `raise HTTPException(...)` in a service | Raise `NotFoundError` / `AlreadyExistError` and let a handler map it | Keeps the service usable outside HTTP and the status codes in one file |
| A repository or DAO layer between the service and the session | Query from the service | A pass-through layer per entity with no behaviour of its own |
| `T \| None` on a patch field whose column is NOT NULL | `T` with `default=None` | `{"field": null}` validates, reaches `UPDATE … SET col = NULL`, and answers 500 |
| Returning an ORM object from a route | Return the response schema validated with `from_attributes=True` | Lazy attributes and internal columns leak into the API contract |
| A feature split across top-level `routes/`, `schemas/`, `services/` | One folder `app/domains/<feature>/` | A single behaviour change otherwise edits three trees |

## Gotchas

- A class injected with `Annotated[Service, Depends()]` may take only injectable parameters. A plain default such as `items: tuple[Item, ...] = DEFAULT_ITEMS` becomes a request-body field, flips the endpoint into embedded-body mode, and every request answers 422 with `Field required` for the real payload. Keep such constants at module level.
- The lifespan does not run under `httpx2.ASGITransport`, so migrations and warm-up are skipped in tests unless the fixture enters `app.router.lifespan_context(app)`; `python-testing` owns that `started_client` fixture.
