# PostgreSQL Setup

Reference for the SQLAlchemy 2.0 async base, engine, and session plumbing. Load this when wiring up a project's `Base`, async engine, or session providers.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- `Base` / `DeclarativeBase` with Alembic naming convention
- `lru_cache`d async engine and session factory
- `get_session` (FastAPI dependency) and `open_db_session` (context manager) providers
- Dependency lifetime for CRUD and streaming responses

## DeclarativeBase

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

## Engine and Session Factory

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

- `get_session` — async generator for FastAPI `Depends()`, shared within a request for the same dependency scope
- `open_db_session` — context manager for non-FastAPI use (scripts, agents, CLI)
- `lru_cache` on engine and factory — singleton per process, clearable in tests

## Dependency lifetime

For ordinary CRUD, inject `Annotated[AsyncSession, Depends(get_session, scope='function')]`. Teardown, including `commit()`, finishes after the endpoint function returns and before the response is sent, so a commit failure can still produce an error response.

Keep the default `use_cache=True`: nested services using the same `get_session` and scope share one session per request. `function` refers to the endpoint's lifetime, not each service constructor. Use the same scope consistently; mixing `function` and `request` creates separate dependency cache entries and sessions.

For a streaming response that reads from the session after the endpoint returns, use `Depends(get_session, scope='request')` so the session stays open through response delivery. Streams that do not use the session while streaming can keep `function` scope. Complete any writes in a transaction that commits before streaming starts; a commit failure after the response has started cannot change its status.

See [FastAPI dependency scopes](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope) for teardown timing and restrictions on yielding sub-dependencies.
