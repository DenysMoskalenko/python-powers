---
name: postgres-database
description: Use when writing SQLAlchemy 2.0 async models, queries, or Alembic migrations (`migrations/env.py`, `alembic revision --autogenerate`) against PostgreSQL — `Mapped[]` columns, `ondelete`, `timezone=True`, `uuidv7` keys, service CRUD, pagination and filtering, testcontainers database isolation, or diagnosing `MissingGreenlet`, `lazy='raise'` / `InvalidRequestError`, or N+1 queries.
---

# PostgreSQL Database Patterns

This skill owns the database half of a service: SQLAlchemy models, relationship loading, service queries and writes, pagination and filtering, Alembic migrations, and the Postgres test fixtures. Services hold the queries; there is no repository layer. An explicit user or project instruction (`AGENTS.md`, `pyproject.toml`, existing code) overrides a house default here; keep the invariants that still apply and name the default you departed from.

> Requires Python 3.13+, SQLAlchemy 2.0+, Alembic, PostgreSQL 18+ (uuidv7), psycopg, fastapi-pagination, testcontainers.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `fastapi-service` (routes, schemas, exception handlers), `python-testing` (factories, helpers, `app` / `client` fixtures), `python-tooling`, `project-scaffolding`.

## Models

One entity per module under `app/infrastructure/db/models/`. Annotate every column with `Mapped[]` and `mapped_column()`. Give every `String` an explicit length matching the schema's `max_length`, so the database rejects oversized values that slipped past validation; use `Text` for genuinely unbounded prose and leave `max_length` off the pydantic field too.

```python
# app/infrastructure/db/models/author.py
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, func, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.book import BookModel


class AuthorModel(Base):
    __tablename__ = 'authors'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    books: Mapped[list['BookModel']] = relationship(
        back_populates='author',
        cascade='all, delete-orphan',
        passive_deletes=True,
        lazy='raise',
    )
```

Timestamps are `DateTime(timezone=True)` with `server_default=func.now()`: a `timestamptz` the database clock fills; `updated_at` adds `onupdate=func.now()` for ORM-issued updates.

Sibling model modules refer to each other through an `if TYPE_CHECKING:` import plus a quoted annotation: the guarded import keeps ruff's `F821` quiet, and SQLAlchemy resolves `'BookModel'` from its declarative registry, so there is no runtime cycle.

```python
# app/infrastructure/db/models/book.py
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.author import AuthorModel
    from app.infrastructure.db.models.cover import CoverModel


class BookModel(Base):
    __tablename__ = 'books'
    __table_args__ = (
        UniqueConstraint(
            'title',
            'author_id',
            'published_year',
            name='books_title_author_year_key',
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    published_year: Mapped[int | None] = mapped_column(Integer)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey('authors.id', ondelete='CASCADE'))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    author: Mapped['AuthorModel'] = relationship(back_populates='books', lazy='raise')
    cover: Mapped['CoverModel | None'] = relationship(
        back_populates='book',
        cascade='all, delete-orphan',
        passive_deletes=True,
        lazy='raise',
    )
```

Single-column constraints and indexes get their names from the naming convention on `Base` (`references/setup.md`). A composite constraint needs an explicit `name=`: the `uq` template interpolates only the first column, so two composite constraints starting with the same column would collide. Mirror a schema's `ge`/`le` as `CheckConstraint('rating BETWEEN 1 AND 5', name='rating_range')` in `__table_args__`; every `CheckConstraint` needs a `name=`, because the `ck` template interpolates `%(constraint_name)s` and an unnamed check raises `InvalidRequestError`.

### Cascades and deletes

`passive_deletes=True` on the parent relationship and `ondelete='CASCADE'` on the child's foreign key are one decision: the service deletes parents with a Core `delete()`, which bypasses ORM cascades, so without the database rule that delete raises `IntegrityError: ... violates foreign key constraint`. If the database should not cascade, drop `passive_deletes=True` and delete children explicitly.

### Primary keys

An integer surrogate key is the house default. Choose a UUID when identifiers are generated outside this database or a sequential id would leak row counts in public URLs; prefer UUIDv7 over v4 (time-ordered, so B-tree inserts stay at the right edge of the index; it encodes its creation timestamp, so it is not opaque). `references/setup.md` has the `CoverModel` example, where the database generates the key.

## Loading relationships

Every `relationship()` declares `lazy='raise'`, so nothing loads implicitly: touching an attribute the query did not load raises `InvalidRequestError` at the access site instead of a hidden query per row or a later `MissingGreenlet` during serialization. The fix is the missing `.options(...)` on the query, not the model. An eager `lazy=` is for the rare relationship every query needs; say so in a comment.

| Relationship | Single-object fetch | List or paginated query |
|---|---|---|
| many-to-one, one-to-one | `joinedload` | `selectinload` |
| one-to-many, many-to-many | `selectinload` | `selectinload` |

`joinedload` fetches a to-one in the same round trip through a LEFT OUTER JOIN; across a list it repeats a shared parent's columns on each child row, so lists use `selectinload`, one extra `WHERE id IN (...)` SELECT per relationship. `joinedload` on a collection multiplies parent rows, forces `LIMIT` into a subquery, and requires `Result.unique()`; use it only with a stated reason and a profile.

## Service queries

Services take an `AsyncSession` through `Depends(get_session)` and build statements directly. Reads declare their eager loads and validate into the response schema:

```python
# app/domains/books/service.py
from logging import getLogger
from typing import Annotated

from fastapi import Depends
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import TypeAdapter
from sqlalchemy import delete, insert, Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.exceptions import NotFoundError
from app.domains.books.schemas import (
    Author,
    AuthorCreate,
    Book,
    BookCreate,
    BookDetail,
    BookListFilters,
    BookListSorting,
    BookPatch,
    BookWithAuthor,
)
from app.infrastructure.db.database import get_session
from app.infrastructure.db.models.author import AuthorModel
from app.infrastructure.db.models.book import BookModel

_logger = getLogger(__name__)


class BookService:
    BOOK_LIST_ADAPTER: TypeAdapter[list[BookWithAuthor]] = TypeAdapter(list[BookWithAuthor])

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

    async def list_books(
        self, filters: BookListFilters, sorting: BookListSorting, pagination_params: Params
    ) -> Page[BookWithAuthor]:
        query = select(BookModel).options(selectinload(BookModel.author))
        query = self._apply_filters(query, filters)
        query = sorting.sort_query(query, BookModel)
        return await apaginate(
            self._session,
            query,
            params=pagination_params,
            transformer=lambda books: self.BOOK_LIST_ADAPTER.validate_python(books, from_attributes=True),
        )

    def _apply_filters(self, query: Select, filters: BookListFilters) -> Select:
        if filters.ids is not None:
            query = query.filter(BookModel.id.in_(filters.ids))
        if filters.title is not None:
            query = query.filter(BookModel.title.icontains(filters.title, autoescape=True))
        if filters.author_id is not None:
            query = query.filter(BookModel.author_id == filters.author_id)
        if filters.created_from is not None:
            query = query.filter(BookModel.created_at >= filters.created_from)
        return query
```

`apaginate` runs the count and page queries and needs the `transformer` to turn ORM objects into schemas. The `TypeAdapter` is a class attribute so it is built once per process. `icontains` renders `ILIKE '%value%'`; `autoescape=True` escapes `%` and `_` in the user's value.

Writes are single statements with `.returning(...)`, one round trip writing and reading the row back:

```python
# app/domains/books/service.py, same class
    async def create_book(self, creation: BookCreate) -> Book:
        await self._get_author_model_or_raise(creation.author_id)
        query = insert(BookModel).values(**creation.model_dump()).returning(BookModel)
        book = await self._session.scalar(query)
        return Book.model_validate(book)

    async def patch_book(self, book_id: int, updates: BookPatch) -> Book:
        changes = updates.model_dump(exclude_unset=True)
        if not changes:
            return Book.model_validate(await self._get_book_model_or_raise(book_id))

        query = update(BookModel).filter(BookModel.id == book_id).values(**changes).returning(BookModel)
        book = await self._session.scalar(query)
        if book is None:
            raise NotFoundError(f'Book(id={book_id}) not found')
        return Book.model_validate(book)

    async def create_author(self, creation: AuthorCreate) -> Author:
        query = insert(AuthorModel).values(**creation.model_dump()).returning(AuthorModel)
        author = await self._session.scalar(query)
        return Author.model_validate(author)

    async def delete_author_by_id(self, author_id: int) -> None:
        query = delete(AuthorModel).filter(AuthorModel.id == author_id).returning(AuthorModel.id)
        deleted_author_id = await self._session.scalar(query)
        if deleted_author_id is None:
            _logger.info(
                f'Author(id={author_id}) requested for deletion was not found',
                extra={'extra': {'author_id': author_id}},
            )

    async def _get_author_model_or_raise(self, author_id: int) -> AuthorModel:
        author = await self._session.scalar(select(AuthorModel).filter(AuthorModel.id == author_id))
        if author is None:
            raise NotFoundError(f'Author(id={author_id}) not found')
        return author

    async def _get_book_model_or_raise(self, book_id: int) -> BookModel:
        book = await self._session.scalar(select(BookModel).filter(BookModel.id == book_id))
        if book is None:
            raise NotFoundError(f'Book(id={book_id}) not found')
        return book
```

`create_book` looks the author up first so an unknown `author_id` is a `NotFoundError` instead of an `IntegrityError`. A delete that matched no row is logged and returns (the route answers 204); raise `NotFoundError` only when the caller must distinguish "deleted" from "never existed". `exclude_unset=True` makes PATCH partial: an omitted field stays out of `changes`, a field sent as `null` clears the column; the patch schema that keeps `null` off NOT NULL columns is in `fastapi-service`, as are the handlers mapping domain exceptions to HTTP.

Request-scoped services do not call `commit()` or `rollback()`; the transaction belongs to `open_db_session()`, which commits on a clean exit and rolls back on an exception. `begin_nested()` around a single statement only adds a round trip; it earns its place when part of a larger transaction must roll back on its own, such as a bulk import that continues past a failing row.

## Migrations

Generate schema migrations with autogenerate:

```bash
uv run alembic revision --autogenerate -m "add books"
```

Autogenerate diffs the models against the database `DATABASE_URL` points at, so start the local stack (`docker compose up -d`) and bring it to head (`make migrate`) first; a stale schema produces a wrong diff. `migrate` and `downgrade` run only against the local compose database unless the user names another target.

Then read the generated revision. Autogenerate renders a column rename as a drop plus an add, and sees neither enum value changes nor a new `CheckConstraint` — both come back as an empty revision; hand-edit those and write data migrations by hand. `migrations/env.py` imports every model module before reading `Base.metadata`; a model that is never imported is invisible and its table comes back as a drop.

## Setup and testing

`references/setup.md` holds `Base` and its naming convention, the engine and session factory, `get_session`, `open_db_session`, and `get_alembic_config`; load it when wiring a new project or changing transaction ownership. `references/testing.md` holds the testcontainers Postgres fixture, the migration-backed engine fixture, and the rollback `session` fixture; load it when setting up or debugging database tests. SQLite and mocked sessions lack the constraints, types and cascades these patterns rely on.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| `Column(...)` in a model | `Mapped[T] = mapped_column(...)` | Only the annotated form gives `ty` a real column type |
| Relaxing `lazy='raise'` to silence an error | Add the `.options(...)` to the query that fetched the object | The model change hides every other missing load too |
| `commit()` or `rollback()` in a request-scoped service | Leave the transaction to `open_db_session()` | Two owners means a half-written request can still be committed |

## Gotchas

- A unique constraint over a nullable column does nothing by default, because PostgreSQL treats every NULL as distinct; `postgresql_nulls_not_distinct=True` renders `UNIQUE NULLS NOT DISTINCT`.
- `insert(...).returning(...)` through `session.scalar()` reaches the server immediately; the row is visible to the rest of the transaction with no `flush()`.
- `update(...).values()` with an empty mapping compiles: with `onupdate=func.now()` it runs `UPDATE books SET updated_at=now()` on a PATCH that changed nothing; without one it fails with `syntax error at end of input`. Hence the early return in `patch_book`.
- `Result.unique()` is only needed when a `joinedload` targets a collection; anywhere else the `joinedload` should probably be a `selectinload`.
