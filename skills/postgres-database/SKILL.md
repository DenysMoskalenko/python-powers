---
name: postgres-database
description: Use when writing SQLAlchemy 2.0 async models, queries, or Alembic migrations against PostgreSQL — `Mapped[]` columns, `ondelete`, `timezone=True`, `uuidv7` keys, service CRUD, pagination and filtering, testcontainers database isolation, or diagnosing `MissingGreenlet`, `lazy='raise'` / `InvalidRequestError`, or N+1 queries.
---

# PostgreSQL Database Patterns

This skill owns the database half of a service: SQLAlchemy models, relationship loading, the query and write patterns services use, pagination and filtering helpers, Alembic migrations, and the Postgres test fixtures. Services hold the queries themselves; there is no repository layer. An explicit instruction from the user or the project (`AGENTS.md`, `pyproject.toml`, existing code) overrides any house default here; keep the invariants that still apply, follow the instruction for the rest, and name the default you departed from.

> Requires Python 3.13+, SQLAlchemy 2.0+, Alembic, PostgreSQL 18+ (uuidv7), psycopg, fastapi-pagination, testcontainers.
> Examples use `app/` as the top-level package and `app/domains/<feature>/` for feature modules. Substitute your names if different.

**Related**: `python-code-style` defines the naming used here (`<Entity>Model`, `_logger`, `*Error`); load it alongside. Also `python-testing`, `python-tooling`, `fastapi-service`, `project-scaffolding`.
For routes, request and response schemas, and exception handlers use `fastapi-service`; for factories, test helpers and the `app` / `client` fixtures use `python-testing`.

## Models

Put one entity per module under `app/infrastructure/db/models/`; class naming follows `python-code-style`. Annotate every column with `Mapped[]` and declare it with `mapped_column()`. Give every `String` an explicit length that matches the schema's `max_length`, so the column is a bounded `VARCHAR(N)` and the database rejects oversized values that slipped past validation. Widening the limit later is a catalog-only change on PostgreSQL, so pick a length you can live with. Use `Text` where the content is genuinely unbounded prose with no product limit — a comment body, a description — and then leave `max_length` off the pydantic field too, so the two halves still agree.

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

Timestamps are `DateTime(timezone=True)` with `server_default=func.now()`, so the column is a `timestamptz` and the database, not the application clock, produces the value. `updated_at` adds `onupdate=func.now()` for ORM-issued updates.

Sibling model modules refer to each other through an `if TYPE_CHECKING:` import plus a quoted annotation. The guarded import is what keeps ruff's `F821` quiet, and SQLAlchemy resolves the quoted `'BookModel'` from its declarative registry when mappers are configured, so there is no runtime import and no cycle between modules.

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

Single-column unique constraints, foreign keys and indexes get their names from the naming convention on `Base` (see `reference/setup.md`). Give a composite constraint an explicit `name=`: the convention's `uq` template interpolates only the first column, so two composite unique constraints that start with the same column would be emitted with the same name.

A numeric column drawn from a fixed range gets the same treatment as a bounded `String`: mirror the schema's `ge`/`le` as a named `CheckConstraint` in `__table_args__`, so a value that reached the database another way is rejected there too — `__table_args__ = (CheckConstraint('rating BETWEEN 1 AND 5', name='rating_range'),)`. Every `CheckConstraint` needs a `name=`, single-column ones included: the `ck` template interpolates `%(constraint_name)s`, so an unnamed check raises `InvalidRequestError` when the table is created. The convention turns `name='rating_range'` on a `reviews` table into `reviews_rating_range_check`.

### Cascades and deletes

`passive_deletes=True` on the parent relationship and `ondelete='CASCADE'` on the child's foreign key are one decision, not two. `passive_deletes=True` tells the ORM not to load and delete children itself because the database will, and the service deletes parents with a Core `delete()` statement, which bypasses ORM cascades entirely. Without the database rule, that delete raises `IntegrityError: ... violates foreign key constraint`. If you do not want the database to cascade, drop `passive_deletes=True` and delete the children explicitly.

### Primary keys

An integer surrogate key is the house default: small, cheap to index, and readable in logs. Choose a UUID when identifiers are generated outside this database — by clients, by another service, or before the row exists — or when they appear in public URLs and a sequential id would leak row counts. Prefer UUIDv7 over v4, because v7 is time-ordered and keeps B-tree inserts at the right edge of the index instead of scattering them. UUIDv7 encodes its creation timestamp, so it is not an opaque identifier. `reference/setup.md` has the `CoverModel` example these queries load, where the database generates the key.

## Loading relationships

Every `relationship()` declares `lazy='raise'`, so nothing loads implicitly. Touching an attribute the originating query did not load raises `InvalidRequestError` naming `lazy='raise'` at the access site, instead of emitting a hidden query per row or failing later as `MissingGreenlet` during response serialization. The fix is the query that fetched the object: add the missing `.options(...)`. Declare an eager `lazy=` on the relationship only when every query needs it and say so in a comment; when the user asks for that, do it and keep `lazy='raise'` on the rest.

| Relationship | Single-object fetch | List or paginated query |
|---|---|---|
| many-to-one, one-to-one | `joinedload` | `selectinload` |
| one-to-many, many-to-many | `selectinload` | `selectinload` |

`joinedload` fetches a to-one in the same round trip through a LEFT OUTER JOIN, which is the cheapest option when there is one parent row. Across a list it repeats every column of a shared parent on each child row, so lists use `selectinload`, which issues one extra `WHERE id IN (...)` SELECT per relationship and sends each parent once.

`joinedload` on a collection is the exception, not a ban: it multiplies parent rows and forces `LIMIT` into a subquery, and SQLAlchemy then requires `Result.unique()` before the rows can be read. Use it only with a stated reason about the shape of that query, and profile the change on a hot endpoint rather than assuming.

## Service queries

Services take an `AsyncSession` through `Depends(get_session)` and build statements directly. Reads select the model, declare their eager loads, and validate into the response schema:

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

`apaginate` runs the count and page queries and needs the `transformer` to turn the returned ORM objects into schemas; without it the `Page` carries model instances. Keep the `TypeAdapter` as a class attribute so it is built once per process, not once per request. Filters go in a `_apply_filters` helper that takes and returns a `Select`, so the query method stays readable and each clause is skipped when its field is unset. `icontains` renders `ILIKE '%value%'`, and `autoescape=True` escapes `%` and `_` inside the user's value so a search for `a_b` does not match everything.

Writes are single statements with `.returning(...)`, which inserts or updates and reads the row back in one round trip:

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

`create_book` looks the author up first so an unknown `author_id` is a `NotFoundError` at the boundary instead of an `IntegrityError` from the foreign key. A delete that matched no row is logged and returns: the caller's goal already holds, so the route answers 204. Raise `NotFoundError` there only when the caller must distinguish "deleted" from "never existed", as an audited or billed operation does.

`exclude_unset=True` is what makes PATCH partial: a field the client omitted stays out of `changes` and is never written, while a field sent as `null` is present and clears the column. That is why the patch schema types a field against its column: on a nullable column the field is `T | None` and `null` clears it; on a NOT NULL column it is `T = Field(default=None)`, so an omitted field is still unset while a sent `null` is a 422 rather than an `IntegrityError`. Pydantic does not validate the default, but ty does, so that line carries `# ty: ignore[invalid-assignment]`. The schema itself belongs to `fastapi-service`. Services raise domain exceptions such as `NotFoundError` and leave the HTTP mapping to the exception handlers in `fastapi-service`.

Request-scoped services do not call `commit()` or `rollback()`; the transaction belongs to `open_db_session()`, which commits on a clean exit and rolls back on an exception. Do not wrap a single-statement write in `begin_nested()` either — one statement is already atomic, and a savepoint around it only adds a round trip. `begin_nested()` earns its place when part of a larger transaction must roll back on its own, such as a bulk import that continues past a failing row or an `IntegrityError` you catch and recover from.

## Migrations

Generate every schema migration with autogenerate:

```bash
uv run alembic revision --autogenerate -m "add books"
```

Autogenerate compares the models with the database `DATABASE_URL` points at, so start the local stack (`make up-dependencies`, or `docker compose up -d`) and bring it to head (`make migrate`) first; a stale local schema produces a wrong diff. Run `migrate` and `downgrade` only against the local compose database unless the user explicitly names another target.

Then open the generated revision and read it. Autogenerate is a starting point, not a verdict: it renders a column rename as a drop plus an add, which destroys data, and it sees neither enum value changes nor a new `CheckConstraint` — both come back as an empty revision. Hand-edit the revision for those cases and write data migrations by hand. `migrations/env.py` imports every model module before it reads `Base.metadata`, so a model that is never imported is invisible to autogenerate and its table shows up in the next revision as a drop.

## Setup and testing

`reference/setup.md` holds the `Base` and its Alembic naming convention, the `lru_cache`d async engine and session factory, the `get_session` and `open_db_session` providers, and `get_alembic_config`. Load it when wiring a new project or changing session or transaction ownership.

`reference/testing.md` holds the testcontainers Postgres fixture, the migration-backed engine fixture that shares its connection with Alembic, and the function-scoped rollback `session` fixture. Load it when setting up or debugging database tests. Run the tests against a real Postgres container; SQLite and mocked sessions do not have the constraints, types or cascade behaviour these patterns rely on.

## Common mistakes

| Mistake | Do instead | Why |
|---|---|---|
| `Column(...)` in a model | `Mapped[T] = mapped_column(...)` | Only the annotated form gives the type checker and `ty` a real column type |
| `String` with no length | `String(N)` matching the schema's `max_length`, or `Text` for unbounded prose | Unbounded `VARCHAR` accepts anything validation missed, and the column then disagrees with the schema's `max_length` |
| `passive_deletes=True` with a plain `ForeignKey` | Add `ondelete='CASCADE'` to the child foreign key | The ORM leaves the children to the database, and a Core `delete()` then hits the constraint |
| Relaxing `lazy='raise'` to silence an error | Add the `.options(...)` to the query that fetched the object | The model change hides every other missing load too |
| `joinedload` for a to-one inside a list query | `selectinload` | The join repeats each shared parent's columns on every child row |
| Composite constraint, or any `CheckConstraint`, without `name=` | Explicit `name=` in `__table_args__` | The `uq` template interpolates only the first column, so two such constraints collide, and the `ck` template has nothing to interpolate at all |
| `commit()` or `rollback()` in a request-scoped service | Leave the transaction to `open_db_session()` | Two owners means a half-written request can still be committed |

## Gotchas

- A unique constraint over a nullable column does nothing by default, because PostgreSQL treats every NULL as distinct. `postgresql_nulls_not_distinct=True` renders `UNIQUE NULLS NOT DISTINCT` and makes the constraint fire.
- `insert(...).returning(...)` run through `session.scalar()` reaches the server immediately, so the row is visible to the rest of the transaction with no `flush()`.
- `update(...).values()` with an empty mapping compiles. On a model with `onupdate=func.now()` it executes as `UPDATE books SET updated_at=now()`, bumping the timestamp on a PATCH that changed nothing; without an `onupdate` column it reaches the server as `UPDATE books SET ` and fails with `syntax error at end of input`. That is why `patch_book` returns early when nothing was set.
- `Result.unique()` is only needed when a `joinedload` targets a collection. Seeing it anywhere else usually means a `joinedload` should have been a `selectinload`.
