# PostgreSQL Setup

Reference for the SQLAlchemy 2.0 async base, engine, and session plumbing. Load this when wiring up a project's `Base`, async engine, or session providers.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- `Base` / `DeclarativeBase` with Alembic naming convention
- `lru_cache`d async engine and session factory
- `get_session` (FastAPI dependency) and `open_db_session` (context manager) providers

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

- `get_session` — async generator for FastAPI `Depends()`, one session per request
- `open_db_session` — context manager for non-FastAPI use (scripts, agents, CLI)
- `lru_cache` on engine and factory — singleton per process, clearable in tests
