# Author service queries

Define `raise_on_duplicate` once in `app/infrastructure/db/database.py`. Use it around a write when any duplicate key should produce the same conflict response.

```python
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AlreadyExistError


@contextmanager
def raise_on_duplicate() -> Iterator[None]:
    try:
        yield
    except IntegrityError as exc:
        if isinstance(exc.orig, UniqueViolation):
            raise AlreadyExistError() from exc
        raise
```

The author pre-check gives the client the full name and birthday when it finds an existing match. If the write hits a unique constraint, the HTTP handler returns status 409 with `{"detail": "Conflict"}`. If the API needs only a generic conflict, omit the pre-check query. The session provider owns rollback.

The model uses an immediate unique constraint. A deferred constraint can fail at commit. To translate that failure, wrap the transaction including its commit when every duplicate in that transaction has the same meaning.

```python
from logging import getLogger
from typing import Annotated

from fastapi import Depends
from pydantic import TypeAdapter
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistError, NotFoundError
from app.domains.authors.schemas import Author, AuthorCreate, AuthorUpdate
from app.infrastructure.db.database import get_session, raise_on_duplicate
from app.infrastructure.db.models.author import AuthorModel

_logger = getLogger(__name__)


class AuthorService:
    AUTHOR_LIST_ADAPTER: TypeAdapter[list[Author]] = TypeAdapter(list[Author])

    def __init__(self, session: Annotated[AsyncSession, Depends(get_session, scope='function')]) -> None:
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
        with raise_on_duplicate():
            author = await self._session.scalar(query)
        return Author.model_validate(author)

    async def update_author(self, author_id: int, updates: AuthorUpdate) -> Author:
        await self.get_author_by_id(author_id)
        await self._validate_author_unique(updates, exclude_author_id=author_id)
        query = update(AuthorModel).filter(AuthorModel.id == author_id).values(**updates.model_dump())
        with raise_on_duplicate():
            author = await self._session.scalar(query.returning(AuthorModel))
        if author is None:
            raise NotFoundError(f'Author(id={author_id}) not found')
        return Author.model_validate(author)

    async def delete_author_by_id(self, author_id: int) -> None:
        query = delete(AuthorModel).filter(AuthorModel.id == author_id).returning(AuthorModel.id)
        deleted_author_id = await self._session.scalar(query)
        if deleted_author_id is None:
            _logger.info(
                f'Author with id={author_id} not found but was requested for deletion',
                extra={'extra': {'author_id': author_id}},
            )

    async def _validate_author_unique(self, creation: AuthorCreate, *, exclude_author_id: int | None = None) -> None:
        query = select(AuthorModel.id).filter(
            AuthorModel.first_name == creation.first_name,
            AuthorModel.last_name == creation.last_name,
            AuthorModel.birthday.is_not_distinct_from(creation.birthday),  # NULL-safe equality
        )
        if exclude_author_id is not None:
            query = query.filter(AuthorModel.id != exclude_author_id)
        if await self._session.scalar(query) is not None:
            raise AlreadyExistError(
                f'Author(name={creation.first_name} {creation.last_name}, birthday={creation.birthday}) already exists'
            )
```
