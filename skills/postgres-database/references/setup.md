# PostgreSQL Setup

Reference for the SQLAlchemy 2.0 async base, engine, and session plumbing. Load this when wiring up a project's `Base`, async engine, or session providers.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- `DatabaseSettings`: connection parts, timeouts, and the composed URL
- `Base` / `DeclarativeBase` with Alembic naming convention
- `lru_cache`d async engine and session factory
- `get_session` (FastAPI dependency) and `open_db_session` (context manager) providers
- Dependency lifetime for CRUD and streaming responses

## Connection settings

Configure the connection as parts, never as one `DATABASE_URL`, so the password stays a `SecretStr`. `_EnvSettings` is the service's shared settings base (`env_file='.env'`, `env_ignore_empty=True`, `extra='ignore'`, `frozen=True`, `hide_input_in_errors=True`). Nest the class into `Settings` as `DATABASE: DatabaseSettings = Field(default_factory=DatabaseSettings)`:

```python
from ipaddress import ip_address
import re
from urllib.parse import quote

from pydantic import Field, field_validator, PostgresDsn, SecretStr
from pydantic_settings import SettingsConfigDict

# Non-ASCII is excluded on purpose: `PostgresDsn.build` percent-encodes it and libpq then resolves it literally.
_BARE_SEGMENT = re.compile(r'[A-Za-z0-9._-]+')


def _is_bare_segment(value: str) -> bool:
    """URLs spell IPv6 as `[addr]`, so brackets are the one place a colon may appear."""
    if value.startswith('[') and value.endswith(']'):
        try:
            return '%' not in value and ip_address(value[1:-1]).version == 6
        except ValueError:
            return False
    return _BARE_SEGMENT.fullmatch(value) is not None


class DatabaseSettings(_EnvSettings):
    model_config = SettingsConfigDict(env_prefix='DATABASE_')

    # No default: a pod missing it must fail at startup, not boot against itself.
    host: str
    port: int = Field(default=5432, ge=1, le=65535)
    user: str
    password: SecretStr
    name: str
    # Without both, a blackholed host leaves `/health/ready` on kernel TCP retries instead of answering 503.
    # A dead pooled connection adds up to 10s: psycopg finishes its own cancel before raising.
    connect_timeout_seconds: int = Field(default=5, ge=1)
    readiness_timeout_seconds: float = Field(default=5.0, gt=0)
    # Server-side, on every statement: nothing else bounds a query that hangs after the connection is up.
    statement_timeout_seconds: int = Field(default=10, ge=1)

    @property
    def url(self) -> PostgresDsn:
        """`build` leaves `@`, `/`, `:` and `%` in a credential raw, where they read as URL structure."""
        return PostgresDsn.build(
            scheme='postgresql+psycopg',  # psycopg2, which a bare `postgresql://` selects, is not installed.
            username=quote(self.user, safe=''),
            password=quote(self.password.get_secret_value(), safe=''),
            host=self.host,
            port=self.port,
            path=self.name,
        )

    @field_validator('host', 'name')
    @classmethod
    def validate_bare_segment(cls, value: str) -> str:
        """Neither is quoted, so `h@other` or `db?sslmode=disable` would compose a URL that means something else."""
        if not _is_bare_segment(value):
            raise ValueError('must be letters, digits, ".", "_" or "-" only, or a bracketed IPv6 literal')
        return value
```

- `url` is a `@property`, not `@cached_property`: a cached value keeps the plaintext in `__dict__` and goes stale after `model_copy`
- TLS and other libpq options have no field: set `PGSSLMODE=verify-full` in the process environment, because libpq never sees `.env`

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
    database = get_settings().DATABASE
    return create_async_engine(
        database.url.unicode_string(),
        pool_pre_ping=True,
        connect_args={
            'connect_timeout': database.connect_timeout_seconds,
            'options': f'-c statement_timeout={database.statement_timeout_seconds}s',
        },
    )


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
