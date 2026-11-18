# Author service queries

The author identity is the full name and birthday. The pre-check gives an early domain error for a visible duplicate. A concurrent duplicate can still pass that check. Both writes translate the specific constraint violation, and the session provider rolls back the failed transaction.

```python
from collections.abc import Iterator
from contextlib import contextmanager
from logging import getLogger
from typing import Annotated

from fastapi import Depends
from psycopg.errors import UniqueViolation
from pydantic import TypeAdapter
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistError, NotFoundError
from app.domains.authors.schemas import Author, AuthorCreate, AuthorUpdate
from app.infrastructure.db.database import get_session
from app.infrastructure.db.models.author import AuthorModel

_logger = getLogger(__name__)


@contextmanager
def _translate_author_conflict(creation: AuthorCreate) -> Iterator[None]:
    try:
        yield
    except IntegrityError as exc:
        if isinstance(exc.orig, UniqueViolation) and exc.orig.diag.constraint_name == 'uq_authors_full_name_birthday':
            raise AlreadyExistError(
                f'Author(name={creation.first_name} {creation.last_name}, birthday={creation.birthday}) already exists'
            ) from exc
        raise


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
        with _translate_author_conflict(creation):
            author = await self._session.scalar(query)
        return Author.model_validate(author)

    async def update_author(self, author_id: int, updates: AuthorUpdate) -> Author:
        await self.get_author_by_id(author_id)
        await self._validate_author_unique(updates, exclude_author_id=author_id)
        query = update(AuthorModel).filter(AuthorModel.id == author_id).values(**updates.model_dump())
        with _translate_author_conflict(updates):
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
