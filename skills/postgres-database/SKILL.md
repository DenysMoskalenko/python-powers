---
name: postgres-database
description: Use when working with PostgreSQL via SQLAlchemy 2.0 async and Alembic — defining models, writing service queries (CRUD, pagination, filtering), generating or debugging migrations, or setting up testcontainers-based database isolation in tests.
---

# PostgreSQL Database Patterns

SQLAlchemy 2.0 async patterns for PostgreSQL. Services own queries directly — no repository layer.

> Requires Python 3.13+, SQLAlchemy 2.0+, Alembic, PostgreSQL, testcontainers, psycopg.
> Examples use `app/` as the top-level package. Substitute your package name if different.

**Related**: `python-code-style`, `python-testing`, `python-tooling`, `fastapi-service`.

For HTTP routes and Pydantic schemas use `fastapi-service`. For shared test fixtures and assertion patterns use `python-testing`.

## Setup

### DeclarativeBase

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

POSTGRES_INDEXES_NAMING_CONVENTION = {
    'ix': '%(column_0_label)s_idx',
    'uq': '%(table_name)s_%(column_0_name)s_key',
    'ck': '%(table_name)s_%(constraint_name)s_check',
    'fk': '%(table_name)s_%(column_0_name)s_fkey',
    'pk': '%(table_name)s_pkey',
}


class Base(DeclarativeBase):
    __abstract__ = True
    metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)
```

The naming convention ensures Alembic generates stable, predictable constraint names across migrations.

### Engine and Session Factory

```python
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@lru_cache
def async_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.DATABASE_URL.unicode_string(), pool_pre_ping=True)


@lru_cache
def async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=async_engine(), autoflush=False, expire_on_commit=False)


async def get_session() -> AsyncIterable[AsyncSession]:
    async with open_db_session() as session:
        yield session


@asynccontextmanager
async def open_db_session() -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = async_session_factory()()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    else:
        await session.commit()
    finally:
        await session.close()
```

- `get_session` — async generator for FastAPI `Depends()`, one session per request
- `open_db_session` — context manager for non-FastAPI use (scripts, agents, CLI)
- `lru_cache` on engine and factory — singleton per process, clearable in tests

### Models

Models live in `app/infrastructure/db/models/<entity>.py`. Naming: `<Entity>Model`.

```python
from datetime import date, datetime

from sqlalchemy import Date, DateTime, func, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


class AuthorModel(Base):
    __tablename__ = 'authors'
    __table_args__ = (
        UniqueConstraint(
            'first_name', 'last_name', 'birthday',
            name='uq_authors_full_name_birthday',
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(64), index=True)
    last_name: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(String(512))
    birthday: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    books: Mapped[list['BookModel']] = relationship(
        back_populates='author',
        cascade='all, delete-orphan',
        passive_deletes=True,
        lazy='raise',
    )
```

Key rules:
- `Mapped[]` for all columns — modern SQLAlchemy 2.0 style
- `server_default=func.now()` for timestamps — DB generates the value
- Explicit `String(N)` lengths matching schema `max_length`
- `UniqueConstraint` in `__table_args__` with descriptive `name` (Alembic needs stable names)
- `TYPE_CHECKING` guard for forward references in relationships
- Every `relationship(...)` declares `lazy='raise'` — no implicit loading; see [Loading relationships](#loading-relationships)

### Primary key choice

Integer surrogate keys (shown above) are the default — simple, small, fast. Choose a UUID primary key when identifiers must be generated outside Postgres (client-side, across services, pre-commit) or when they leak through public URLs and sequential IDs would expose internals.

When you do use a UUID, prefer UUIDv7 over v4 — v7 is time-ordered, so B-tree indexes stay efficient on insert:

```python
import uuid
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

class AuthorModel(Base):
    __tablename__ = 'authors'

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
```

If your PostgreSQL exposes native `uuidv7()` (PG 17+ or the `pg_uuidv7` extension), prefer generating it in the database via `server_default`; otherwise generate in Python with `uuid.uuid7()`.

## Usage

### Service Query Patterns

Services accept `AsyncSession` via `Depends(get_session)` and query directly:

```python
from sqlalchemy import delete, insert, select, update


class AuthorService:
    AUTHOR_LIST_ADAPTER: TypeAdapter[list[Author]] = TypeAdapter(list[Author])

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
        query = (
            insert(AuthorModel)
            .values(first_name=creation.first_name, last_name=creation.last_name)
            .returning(AuthorModel)
        )
        author = await self._session.scalar(query)
        return Author.model_validate(author)

    async def delete_author_by_id(self, author_id: int) -> None:
        query = delete(AuthorModel).filter(AuthorModel.id == author_id).returning(AuthorModel.id)
        deleted_author_id = await self._session.scalar(query)
        if deleted_author_id is None:
            _logger.info('Author with id=%s not found but requested for deletion', author_id)
```

- Request-scoped write methods that receive `get_session` do not call `commit()` or `rollback()`
- `open_db_session()` or the caller-owned session defines the transaction boundary
- Do not wrap single-statement CRUD writes in `begin_nested()`. Reach for it only when you need partial rollback inside a larger transaction — bulk import that should continue past a per-row failure, or catching `IntegrityError` and keeping the outer transaction usable. For test isolation against accidental `session.commit()` calls, use `join_transaction_mode='create_savepoint'` in the test session fixture, not service-level savepoints.
- `insert(...).returning(Model)` — single query for insert+read
- Domain exceptions (`NotFoundError`) — never `HTTPException` in services

### Loading relationships

**No hidden loads.** Every relationship attribute the service or response touches must be loaded explicitly in the query that fetches the parent, via `.options(joinedload(...))` or `.options(selectinload(...))`. Lazy loading is forbidden — all `relationship(...)` declarations set `lazy='raise'` so a missed eager-load fails with `InvalidRequestError` at the call site instead of leaking N+1 queries or surprising the next reader.

Pick the loader by the **relationship shape** and **how many parents** you load:

| Relationship | Loading | Use |
|---|---|---|
| many-to-one / one-to-one | single fetch or list | `joinedload` |
| one-to-many / many-to-many | single parent | `joinedload` (call `.unique()`) or `selectinload` |
| one-to-many / many-to-many | multiple parents (lists, paginated) | `selectinload` |

**Single fetch — `joinedload`** (one round-trip via LEFT OUTER JOIN, ideal for to-one):

```python
from sqlalchemy import select
from sqlalchemy.orm import joinedload


async def get_book_by_id(self, book_id: int) -> Book:
    query = (
        select(BookModel)
        .options(joinedload(BookModel.author))
        .filter(BookModel.id == book_id)
    )
    book = await self._session.scalar(query)
    if book is None:
        raise NotFoundError(f'Book(id={book_id}) not found')
    return Book.model_validate(book)
```

**Paginated list with a collection — `selectinload`** (parent SELECT + one `WHERE id IN (...)` SELECT per loaded relationship; no row duplication, no subquery wrap on `LIMIT`):

```python
from sqlalchemy.orm import selectinload


async def list_books(
    self, filters: BookListFilters, pagination_params: Params,
) -> Page[Book]:
    query = (
        select(BookModel)
        .options(selectinload(BookModel.tags))  # M2M — selectinload, never joinedload
        .options(joinedload(BookModel.author))  # to-one — joinedload is fine on lists
    )
    query = self._apply_filters(query, filters)
    return await apaginate(
        self._session, query, params=pagination_params,
        transformer=lambda books: self.BOOK_LIST_ADAPTER.validate_python(books, from_attributes=True),
    )
```

### Pagination

Use `fastapi_pagination` with a `TypeAdapter` transformer:

```python
from pydantic import TypeAdapter
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import apaginate


async def list_authors(
    self, filters: AuthorListFilters, sorting: AuthorListSorting, pagination_params: Params
) -> Page[Author]:
    query = select(AuthorModel)
    query = self._apply_filters(query, filters)
    query = self._apply_sorting(query, sorting)
    return await apaginate(
        self._session, query, params=pagination_params,
        transformer=lambda authors: self.AUTHOR_LIST_ADAPTER.validate_python(authors, from_attributes=True),
    )
```

The transformer validates ORM objects into Pydantic models — without it you get raw model instances.

### Filtering

Case-insensitive contains pattern for text filters:

```python
from sqlalchemy import Select


def _apply_filters(self, query: Select, filters: AuthorListFilters) -> Select:
    if filters.name:
        full_name = func.concat(AuthorModel.first_name, ' ', AuthorModel.last_name)
        query = query.filter(full_name.icontains(filters.name))
    if filters.ids:
        query = query.filter(AuthorModel.id.in_(filters.ids))
    if filters.created_from:
        query = query.filter(AuthorModel.created_at >= filters.created_from)
    return query
```

### Migrations

Always generate with Alembic autogenerate:

```bash
make migration MSG="add authors"
```

Never hand-write migration files. Ensure `migrations/env.py` imports all models so metadata is complete. Customize the generated file only if Alembic cannot detect the change (e.g., data migrations).

## Testing

See `reference/testing.md` for testcontainers-backed database isolation: session-scoped Postgres container,
migration-backed engine fixture, function-scoped rollback session, and startup-migration disabling.

## Red Flags — STOP

These mean the database boundary is drifting. Stop and apply the named rule:

| About to… | Rule to apply |
|---|---|
| Add `Column(...)` instead of `Mapped[]` / `mapped_column()` | Models — use SQLAlchemy 2.0 style |
| Leave `String` length implicit | Models — match schema `max_length` with explicit `String(N)` |
| Add unnamed constraints | Models — every constraint needs a stable Alembic name |
| Declare `relationship(...)` without `lazy='raise'` | Loading relationships — every relationship is opt-in per query; no implicit loads |
| Touch a relationship attribute that the originating query did not eager-load | Loading relationships — add `.options(joinedload(...))` (to-one) or `.options(selectinload(...))` (collection) to the query, do not work around the error |
| Use `joinedload` on a collection (one-to-many / many-to-many) in a paginated list query | Loading relationships — use `selectinload` for collections on multiple parents |
| Forget `Result.unique()` / `scalars().unique()` after `joinedload(collection)` | Loading relationships — joinedload duplicates parent rows on collections; deduplicate or switch to `selectinload` |
| Soften `lazy='raise'` to `'select'` / `'raise_on_sql'` to make an error go away | Loading relationships — the rule stands; fix the originating query, do not weaken the model |
| Hand-write a migration without autogenerate | Migrations — run `make migration MSG="..."` first |
| Add a repository layer between services and SQLAlchemy | Usage — services own queries directly |
| Paginate with manual `limit` / `offset` math | Pagination — use `apaginate()` with a transformer |
| Use `==` for requested case-insensitive text search | Filtering — use `icontains` / `ilike` |
| Move request-scoped `commit()` / `rollback()` from the session provider into CRUD service methods | Engine and Session Factory — keep request transaction ownership in `open_db_session()` |
| Wrap a single-statement CRUD write in `begin_nested()` / SAVEPOINT for "safety" or "test rollback" | Service Query Patterns — `begin_nested()` is for partial rollback inside a larger transaction; for test isolation use `join_transaction_mode='create_savepoint'` in the fixture |
| Replace Postgres tests with SQLite or mocks | Testing — use testcontainers; see `reference/testing.md` |

## Gotchas

- Always include `session` fixture in test signatures even if the test doesn't query the DB directly — it sets up transaction rollback
- All constraints need explicit `name` in `__table_args__` — Alembic needs stable names across environments
- `get_settings().DATABASE_URL` returns a `PostgresDsn` object — call `.unicode_string()` when a plain string is needed
- `expire_on_commit=False` on the session factory prevents attribute-expiration errors after commit
