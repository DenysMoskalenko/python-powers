---
name: fastapi-service
description: Use when adding or changing a FastAPI endpoint — thin routes, service classes, Pydantic schemas, query-parameter models, PATCH semantics, status codes, domain exception handlers, pydantic-settings configuration, lifespan, and the app factory. For SQLAlchemy models and queries see `postgres-database`; for pydantic-ai agents see `ai-agents`.
---

# FastAPI Service Patterns

How an HTTP request travels through this house's services: a thin route parses it into a typed schema and calls one service method; the service holds the business logic and its queries, and signals failure by raising a domain exception; an exception handler turns that exception into a status code. There is no repository layer — the service is the layer that owns data access. An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires Python 3.13+, FastAPI, Pydantic, pydantic-settings, fastapi-pagination, uvicorn.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `python-testing`, `postgres-database`, `ai-agents`, `project-scaffolding`.

## Layout

Package by feature. Each folder under `app/domains/` is one vertical slice, so a business change touches one folder; cross-cutting technical code lives outside it, in `app/core/` and `app/infrastructure/`.

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

SQLAlchemy models are the deliberate exception to "everything in the feature folder": they stay in `app/infrastructure/db/models/` so Alembic autogenerates from a single metadata and cross-entity relationships need no cross-domain imports.

Start flat with those three files. Promote a concern to a subpackage once it splits into two or more files — `books/services/` holding `service_books.py` and `service_books_validator.py`. The subpackage's `__init__.py` is then a facade that re-exports the public names through `__all__`, so callers outside write `from app.domains.books.services import BookService` while siblings inside the package import each other directly (`from .service_books import BookService`) to avoid circular imports while the package is still initialising. Keep the descriptive filename prefix (`service_books.py`, not `books.py`) so a file is unambiguous in search results and editor tabs.

This layout is for new services and new slices. In a project that already uses a different layout, add the endpoint where its siblings live and do not migrate the tree; propose the move separately if it is worth doing.

## Routes

A route translates HTTP into one service call and back. Validation, lookups, and branching belong to the service.

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

- `Annotated[BookService, Depends()]` with an empty `Depends()` tells FastAPI to instantiate the service and resolve the service's own constructor dependencies, so the route never names the session.
- The return annotation is the response model. A POST that creates a resource returns 201; a DELETE returns 204, and `response_class=Response` documents that the route has no body model. A delete that matched no row still answers 204 here, because the caller's goal already holds; `postgres-database` owns that default and the `delete_author_by_id` method behind it.

### Query-parameter models

FastAPI expands a `Query()` parameter model into its fields only when it is the route's only query parameter of any kind. Anything else in the same signature that reads the query string stops the expansion, and every request then answers 422, one `Field required` per unexpanded model name — a second `Query()` model does it, and so does a plain scalar such as `limit: int = 10`. Query parameters that arrive through a `Depends()` sub-dependency are the exception: `*ListSorting` and `fastapi_pagination.Params` leave runtime parsing intact and only collapse the model to one opaque parameter in `/docs`.

So give `Query()` to the one model that carries a `list[...]` field, exactly as `list_books` above does, keep every other query-reading model on `Depends()`, and put no bare scalar query parameter beside it. `Depends()` on a model with a `list[...]` field moves that field into a JSON request body, so `?ids=1&ids=2` answers 200 with `ids` set to `None` and the filter is silently dropped. When no field on the filters model is a list, `Depends()` is the better spelling: both parse correctly, but `Depends()` renders each filter as its own parameter in `/docs` while `Query()` collapses them into one opaque `filters` entry. When two models would each need `Query()`, merge them into one filters model.

## Services

A service is a class whose collaborators arrive through `Depends()`. It owns the business logic and its queries; `postgres-database` owns the query patterns themselves — filtering, pagination, loading strategy, and insert-returning writes.

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
        query = select(BookModel).options(joinedload(BookModel.author), joinedload(BookModel.cover))
        book = await self._session.scalar(query.filter(BookModel.id == book_id))
        if book is None:
            raise NotFoundError(f'Book(id={book_id}) not found')
        return BookDetail.model_validate(book)
```

- Services raise domain exceptions; `HTTPException` never appears below the route layer. The same method then works from a worker, a CLI, or a test with no HTTP context, and the status code is decided in one place.
- A request-scoped service does not call `commit()` or `rollback()`; `postgres-database` owns the transaction boundary in `open_db_session`.
- Log at `info` where an operator reading the log later needs the event: a situation the service tolerates (a delete that matched no row, a retry) and a write that creates or destroys something another team will ask about. Give it an f-string message that reads on its own and repeat the identifiers under `extra={'extra': {...}}` — the message is for a human scrolling, the payload is for a query. A top-level `extra` key makes `Logger.makeRecord` raise `KeyError` as soon as it collides with a `LogRecord` attribute (`name`, `module`, `args`, `filename`, and the rest), and the nesting gives JSON formatters one stable key to read the payload from.

```python
_logger.info(
    f'Author(id={author_id}) requested for deletion was not found',
    extra={'extra': {'author_id': author_id}},
)
```

## Schemas

Schemas live in the feature's `schemas.py`. One private base holds the shared fields; the input, patch, and response models derive from it.

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

- `BookPatch` is declared separately with every field optional rather than inherited from `BookCreate`, because inheriting makes each field required again and turns PATCH into a full replacement.
- A patch field whose column is NOT NULL keeps the column's type and takes `default=None` (`title: str`). Pydantic does not validate a default, so an omitted field stays unset for `model_dump(exclude_unset=True)` while a sent `null` is a 422 instead of an `IntegrityError`; `ty` flags the deliberate mismatch, hence the suppression. A field whose column is nullable is `T | None`, and `null` clears it.
- A response model carries `ConfigDict(from_attributes=True)` and is what the service returns; an ORM object never leaves the service.
- Constrain string inputs with `min_length` and `max_length`, and give input fields `examples` so `/docs` is usable; server-owned response fields such as `created_at` need neither. `sort_by` is a `Literal`, so an unknown column is a 422 at the boundary instead of an error inside the query.

`BaseListSorting` is the shared base in `app/core/schemas.py` that each feature narrows; `reference/setup.md` holds it and its `sort_query` helper.

## Exceptions

Domain exceptions live in `app/core/exceptions.py` and know nothing about HTTP.

```python
class BaseServiceError(Exception):
    pass


class NotFoundError(BaseServiceError):
    pass


class AlreadyExistError(BaseServiceError):
    pass
```

Handlers in `app/core/exception_handlers.py` map them to responses and are collected into one `EXCEPTION_HANDLERS` mapping the app factory passes to `FastAPI(exception_handlers=EXCEPTION_HANDLERS)`; `reference/setup.md` holds that module.

- A handler returns the response rather than raising, because that form type-checks as written: no `cast`, no `NoReturn` return type, and `request` is used, so no unused-argument suppression.
- Registration order is irrelevant. `add_exception_handler` and the `exception_handlers=` argument both only fill a dictionary, which Starlette reads when it builds the middleware stack on the first request.
- A mounted sub-application needs the same handlers registered on it. It is a full ASGI app with its own `ServerErrorMiddleware`, which writes a 500 for the escaping domain exception before the parent app's handlers are ever consulted.

## Setup

`reference/setup.md` covers the one-time wiring — the `Settings` class with `lru_cache`d `get_settings`, the `lifespan` context manager, the `exception_handlers` module, `create_router()`, `create_app()`, and `BaseListSorting`. Load it when bootstrapping a service or changing configuration, exception mapping, routing prefixes, startup behaviour, or sorting.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| Validation, a lookup, or branching inside a route | Move it into the service and call one method | The logic becomes reachable only through HTTP and only testable through the client |
| `raise HTTPException(...)` in a service | Raise `NotFoundError` / `AlreadyExistError` and let a handler map it | Keeps the service usable outside HTTP and the status codes in one file |
| A repository or DAO layer between the service and the session | Query from the service | An extra pass-through layer per entity with no behaviour of its own |
| `Depends()` on a filters model that has a `list[...]` field | `Query()` on that one model | The list field silently becomes a request-body field and the query values arrive as `None` |
| Any second query parameter beside a `Query()` model — another `Query()` model, or a bare `limit: int = 10` | One `Query()` model as the route's only query parameter; everything else on `Depends()` | FastAPI stops expanding the model and every request answers 422 |
| `T \| None` on a patch field whose column is NOT NULL | `T` with `default=None` | `{"field": null}` validates, reaches `UPDATE … SET col = NULL`, and answers 500 |
| `BookUpdate(BookCreate)` reused for PATCH | A separate all-optional patch model plus `model_dump(exclude_unset=True)` | Inherited fields are required again, so a partial update erases what the client omitted |
| Registering exception handlers "last" so they wrap routers | `FastAPI(exception_handlers=EXCEPTION_HANDLERS)` | Registration only fills a dict; order changes nothing |
| Returning an ORM object from a route | Return the response schema validated with `from_attributes=True` | Lazy attributes and internal columns leak into the API contract |
| A feature split across top-level `routes/`, `schemas/`, `services/` | One folder `app/domains/<feature>/` | A single behaviour change otherwise edits three trees |

## Gotchas

- A class injected with `Annotated[Service, Depends()]` may take only injectable parameters. A plain default such as `items: tuple[Item, ...] = DEFAULT_ITEMS` becomes a request-body field, which flips the whole endpoint into embedded-body mode and makes every request 422 with `Field required` for the real payload. Keep such constants at module level.
- A `Query()` filters model renders in `/docs` as one opaque parameter as soon as the route has any other query parameter — a paginated route always does, through `page` and `size`. Runtime parsing survives only when that other parameter arrives through a `Depends()` sub-dependency.
- The lifespan does not run under `httpx2.ASGITransport`: migrations and warm-up are skipped in tests unless the fixture enters `app.router.lifespan_context(app)` around the client. `python-testing` owns that fixture.
