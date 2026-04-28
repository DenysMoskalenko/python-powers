# PostgreSQL Test Fixtures

Reference for testcontainers-backed database isolation. Load this when setting up Postgres fixtures, migration-backed test engines, or per-test rollback sessions.

Examples use `app/` as the top-level package — substitute your package name if different.

## Contents

- Session-scoped Postgres container
- Engine fixture with migrations
- Function-scoped session with rollback
- Startup migration disabling

## Session-scoped Postgres container

One container per test session. Alembic migrations run once:

```python
import os
from collections.abc import Generator

import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope='session', autouse=True)
def _postgres_container() -> Generator[PostgresContainer, None, None]:
    with PostgresContainer(
        image='postgres:18-alpine', username='test', password='test', dbname='TestDB',
    ) as postgres:
        host = postgres.get_container_host_ip()
        port = postgres.get_exposed_port(5432)
        os.environ['DATABASE_URL'] = (
            f'postgresql+psycopg://{postgres.username}:{postgres.password}@{host}:{port}/{postgres.dbname}'
        )
        get_settings.cache_clear()
        async_engine.cache_clear()
        async_session_factory.cache_clear()
        yield postgres
```

Clear all `lru_cache`d functions after setting the test `DATABASE_URL` so the app picks up the test database.

## Engine fixture with migrations

```python
from collections.abc import AsyncIterable

from alembic.command import downgrade, upgrade
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@pytest.fixture(scope='session')
async def _engine(_postgres_container: PostgresContainer) -> AsyncIterable[AsyncEngine]:
    settings = get_settings()
    alembic_config = get_alembic_config(settings.DATABASE_URL)

    engine = create_async_engine(settings.DATABASE_URL.unicode_string())
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: downgrade(alembic_config, 'base'))
        await connection.run_sync(lambda conn: upgrade(alembic_config, 'head'))
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: downgrade(alembic_config, 'base'))
        await engine.dispose()
```

## Function-scoped session with rollback

Each test gets a session wrapped in a transaction that rolls back after the test:

```python
from collections.abc import AsyncIterable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture(scope='function')
async def session(app: FastAPI, _engine: AsyncEngine) -> AsyncIterable[AsyncSession]:
    connection = await _engine.connect()
    trans = await connection.begin()

    session_factory = async_sessionmaker(connection, expire_on_commit=False)
    session = session_factory()

    override_dependency(app, get_session, lambda: session)

    try:
        yield session
    finally:
        await trans.rollback()
        await session.close()
        await connection.close()
```

The `session` fixture overrides `get_session` so the app uses the test session. After the test, the transaction rolls back and the database is clean.

## Startup migration disabling

```python
def pytest_configure(config: pytest.Config) -> None:
    os.environ['MIGRATION_ON_STARTUP'] = 'False'
```

Disable startup migrations in tests — the engine fixture handles them.

## Gotchas

- Always include the `session` fixture in test signatures even if the test only calls HTTP; it installs the rollback-bound session override.
- Clear cached settings, engine, and session factory after writing `DATABASE_URL`.
- Keep Alembic migrations as the source of truth for test schema creation; do not call `Base.metadata.create_all()`.
