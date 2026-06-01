---
name: postgres-database
description: Use when working with PostgreSQL via SQLAlchemy 2.0 async and Alembic — defining models, writing service queries (CRUD, pagination, filtering), generating or debugging migrations, or setting up testcontainers-based database isolation in tests.
---

# PostgreSQL Database Patterns

SQLAlchemy 2.0 async patterns for PostgreSQL. Services own queries directly — no repository layer.

> Requires Python 3.13+, SQLAlchemy 2.0+, Alembic, PostgreSQL, testcontainers, psycopg.
> Examples use `app/` as the top-level package. Substitute your package name if different.

**Related**: `python-code-style`, `python-testing`, `python-tooling`, `fastapi-service`, `project-scaffolding`.

For HTTP routes and Pydantic schemas use `fastapi-service`. For shared test fixtures and assertion patterns use `python-testing`.

## Setup

See `reference/setup.md` for the `Base` / `DeclarativeBase` with Alembic naming convention, the `lru_cache`d async engine and session factory, and the `get_session` / `open_db_session` session providers.

### Models

Models live in `app/infrastructure/db/models/<entity>.py`. Naming: `<Entity>Model`.

```python
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, func, Integer, String, UniqueConstraint
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

One-to-one example (Book ↔ Cover — each book has at most one cover):

```python
class BookModel(Base):
    __tablename__ = 'books'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey('authors.id'))

    cover: Mapped['CoverModel | None'] = relationship(
        back_populates='book',
        lazy='raise',
    )


class CoverModel(Base):
    __tablename__ = 'covers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey('books.id'), unique=True)
    image_url: Mapped[str] = mapped_column(String(512))

    book: Mapped['BookModel'] = relationship(
        back_populates='cover',
        lazy='raise',
    )
```

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

**`selectinload` is the default.** Use `joinedload` only where related rows can't multiply: a one-to-one, or a many-to-one you fetch for a single parent. The two damage cases are `joinedload` on a collection (duplicates parent rows, wraps `LIMIT` in a subquery) and `joinedload` on a many-to-one across a list (re-transmits each shared parent's columns on every child row — `O(rows × parent_width)`, over an order of magnitude slower with wide, shared parents).

| Relationship | get-by-id (one parent) | list / paginated |
|---|---|---|
| one-to-one | `joinedload` | `joinedload` |
| many-to-one | `joinedload` | `selectinload` |
| one-to-many / many-to-many | `selectinload` | `selectinload` |

> Matches SQLAlchemy's guidance that `joinedload` is the general-purpose strategy for many-to-one — with one carve-out: lists use `selectinload` to dodge the wide-shared-parent transfer blow-up.

**`joinedload` — to-one on a single-object fetch** (one round-trip via LEFT OUTER JOIN, one joined row per parent):

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

**`selectinload` — collections, and any to-one on a list** (parent SELECT + one `WHERE id IN (...)` SELECT per relationship; no row duplication, dedupes shared parents):

```python
from sqlalchemy.orm import selectinload


async def list_books(
    self, filters: BookListFilters, pagination_params: Params,
) -> Page[Book]:
    query = (
        select(BookModel)
        .options(selectinload(BookModel.author))  # many-to-one on a list — selectinload (dedupes shared parents)
        .options(selectinload(BookModel.tags))    # M2M — selectinload
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
| Touch a relationship attribute that the originating query did not eager-load | Loading relationships — add `.options(joinedload(...))` (to-one on a single fetch) or `.options(selectinload(...))` (collections, or any to-one on a list) to the query, do not work around the error |
| Use `joinedload` on a collection, or on a many-to-one in a list / paginated query | Loading relationships — both blow up (row duplication / `LIMIT` subquery wrap, or re-transmitting shared parents); use `selectinload`. `joinedload` is only for one-to-one, or a to-one on a single-object fetch |
| Call `.unique()` on a query result | Loading relationships — `.unique()` is only needed when `joinedload` is used on a collection, which is forbidden; if you see `.unique()`, that's a signal to drop `joinedload` and switch to `selectinload` |
| Soften `lazy='raise'` to `'select'` / `'raise_on_sql'` to make an error go away | Loading relationships — the rule stands; fix the originating query, do not weaken the model |
| Hand-write a migration without autogenerate | Migrations — run `make migration MSG="..."` first |
| Add a repository layer between services and SQLAlchemy | Usage — services own queries directly |
| Paginate with manual `limit` / `offset` math | Pagination — use `apaginate()` with a transformer |
| Use `==` for requested case-insensitive text search | Filtering — use `icontains` / `ilike` |
| Move request-scoped `commit()` / `rollback()` from the session provider into CRUD service methods | Setup — keep request transaction ownership in `open_db_session()`; see `reference/setup.md` |
| Wrap a single-statement CRUD write in `begin_nested()` / SAVEPOINT for "safety" or "test rollback" | Service Query Patterns — `begin_nested()` is for partial rollback inside a larger transaction; for test isolation use `join_transaction_mode='create_savepoint'` in the fixture |
| Replace Postgres tests with SQLite or mocks | Testing — use testcontainers; see `reference/testing.md` |

## Gotchas

- Always include `session` fixture in test signatures even if the test doesn't query the DB directly — it sets up transaction rollback
- All constraints need explicit `name` in `__table_args__` — Alembic needs stable names across environments
- `get_settings().DATABASE_URL` returns a `PostgresDsn` object — call `.unicode_string()` when a plain string is needed
- `expire_on_commit=False` on the session factory prevents attribute-expiration errors after commit
