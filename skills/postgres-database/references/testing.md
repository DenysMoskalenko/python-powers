# PostgreSQL Test Fixtures

Database tests run against a real PostgreSQL container whose schema is built by the project's own Alembic migrations, and every test gets a session inside a transaction that is rolled back afterwards. Load this when setting up those fixtures or debugging one that hangs, leaks rows between tests, or cannot see the container's database.

Examples use `app/` as the top-level package. Substitute your package name if different. Everything below lives in `tests/conftest.py` unless another path is given.

## Contents

- [Postgres container](#postgres-container) — session-scoped, autouse
- [Engine fixture](#engine-fixture) — migrations on the caller's connection
- [Alembic connection branch](#alembic-connection-branch) — the `migrations/env.py` half
- [Rollback session](#rollback-session) — the function-scoped `session` fixture
- [Startup migrations](#startup-migrations)
- [Gotchas](#gotchas)

The `app` and `client` fixtures, `temporary_override`, and the test-dependency helpers these fixtures import from `tests/dependencies.py` belong to `python-testing`. The pytest-asyncio loop-scope settings that let session-scoped async fixtures serve function-scoped tests live in `pyproject.toml` and belong to `python-tooling`.

## Postgres container

```python
from collections.abc import Generator
import os

import pytest
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope='session', autouse=True)
def _postgres_container() -> Generator[PostgresContainer]:
    with PostgresContainer(
        image='postgres:18-alpine',
        username='test',
        password='test',  # noqa: S106
        dbname='TestDB',
        driver='psycopg',
    ) as postgres:
        os.environ['DATABASE_URL'] = postgres.get_connection_url()

        from app.core.config import get_settings
        from app.infrastructure.db.database import async_engine, async_session_factory

        get_settings.cache_clear()
        async_engine.cache_clear()
        async_session_factory.cache_clear()

        yield postgres
```

Import `PostgresContainer` from `testcontainers.community.postgres`. The old `testcontainers.postgres` path still works but emits a `DeprecationWarning`, which shows up in the `-ra` summary and which the warnings policy in `python-tooling` then makes you fix or suppress.

`driver='psycopg'` makes `get_connection_url()` return a `postgresql+psycopg://` URL with the mapped host and port already in it, so there is no hand-built connection string to keep in sync.

Pin `image=` to the major version production runs. A newer test major hides functions and defaults the deployment target lacks, so a schema that builds here fails its first migration there.

The fixture is `autouse` so pytest instantiates it before any other session-scoped fixture. That ordering is what lets `create_app()` and the engine read the container's `DATABASE_URL`. Clear the cached settings, engine and session factory immediately after writing the environment variable, before anything opens a connection against the default URL.

## Engine fixture

```python
from collections.abc import AsyncGenerator

from alembic.command import downgrade, upgrade
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings
from app.infrastructure.db.database import get_alembic_config


@pytest.fixture(scope='session')
async def _engine(_postgres_container: PostgresContainer) -> AsyncGenerator[AsyncEngine]:
    settings = get_settings()
    alembic_config = get_alembic_config(settings.DATABASE_URL)

    engine = create_async_engine(settings.DATABASE_URL.unicode_string())
    async with engine.begin() as connection:
        await connection.run_sync(_alembic_upgrade, alembic_config)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(_alembic_downgrade, alembic_config)
        await engine.dispose()


def _alembic_upgrade(connection: Connection, alembic_config: Config) -> None:
    alembic_config.attributes['connection'] = connection
    upgrade(alembic_config, 'head')


def _alembic_downgrade(connection: Connection, alembic_config: Config) -> None:
    alembic_config.attributes['connection'] = connection
    downgrade(alembic_config, 'base')
```

`run_sync` hands Alembic the synchronous `Connection` behind the async one, and `attributes['connection']` is what makes Alembic use it instead of opening its own. Without that line Alembic builds its own engine from the same URL and the migrations commit on a separate connection, outside the transaction this fixture controls.

The teardown downgrade to `base` is worth keeping: it exercises the `downgrade()` half of every revision once per run, which is otherwise never tested.

## Alembic connection branch

`migrations/env.py` has to accept that connection. Branch on it and fall back to building an engine, so the Alembic CLI still works:

```python
# migrations/env.py
import os
from typing import cast

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

from app.infrastructure.db.database import Base
from app.infrastructure.db.models import load_all_models

config = context.config
load_all_models()
target_metadata = Base.metadata


def get_url() -> str:
    return cast(str, os.getenv('DATABASE_URL', config.get_main_option('sqlalchemy.url')))


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get('connection')
    if connection is not None:
        do_run_migrations(connection)
        return

    configuration = cast(dict[str, str], config.get_section(config.config_ini_section))
    configuration['sqlalchemy.url'] = get_url()
    connectable = engine_from_config(configuration, prefix='sqlalchemy.', poolclass=pool.NullPool)

    with connectable.connect() as own_connection:
        do_run_migrations(own_connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`load_all_models()` walks `app/infrastructure/db/models/` and imports every module, so `Base.metadata` is complete before autogenerate compares it against the database. Reading `DATABASE_URL` from the environment first is what lets the same `env.py` serve the CLI, the container and deployment. The module-level dispatch at the end is what Alembic executes; without it every `upgrade` returns without running anything.

## Rollback session

```python
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.infrastructure.db.database import get_session
from tests.dependencies import temporary_override


@pytest.fixture
async def session(app: FastAPI, _engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    connection = await _engine.connect()
    trans = await connection.begin()

    session_factory = async_sessionmaker(
        connection, autoflush=False, expire_on_commit=False, join_transaction_mode='create_savepoint'
    )
    session = session_factory()

    try:
        with temporary_override(app, get_session, lambda: session):
            yield session
    finally:
        await trans.rollback()
        await session.close()
        await connection.close()
```

The fixture opens the outer transaction itself and binds the session to that connection, so rolling back at the end erases everything the test wrote, schema included if it created any.

`join_transaction_mode='create_savepoint'` makes the session open a SAVEPOINT instead of joining the outer transaction directly. An application `commit()` then releases the savepoint rather than committing the outer transaction, so a `commit()` from any code path — a service that breaks the no-commit rule, or code that opens `open_db_session()` itself — cannot escape the rollback. Requests under test never reach `open_db_session()`: the override hands them this session directly.

Installing the override through `temporary_override` restores whatever was there before, so a later test that requests only `client` gets the default override back instead of silently reusing this test's closed session.

## Startup migrations

This is the line this skill contributes to the `pytest_configure` skeleton `python-testing` owns:

```python
os.environ['MIGRATION_ON_STARTUP'] = 'False'
```

The `_engine` fixture owns schema creation. Leaving startup migrations on means the application's lifespan races the fixture for the same tables.

## Gotchas

- Request the `session` fixture in every test that reaches the database, including pure HTTP tests that never touch the session directly. It is the fixture that installs the rollback-bound override; without it the request hits the sentinel `python-testing` installs (or, with no sentinel, a real committed transaction).
- Do not downgrade to `base` before the first upgrade. A fresh container has no `alembic_version` table, so there is nothing to downgrade and the call is pure startup cost.
- Let Alembic build the test schema. `Base.metadata.create_all()` produces a schema that no migration was ever run to reach, so a broken revision passes the suite and fails in deployment.
- `_engine` downgrades to `base` on teardown, so it must keep its `_postgres_container` parameter and never see any other URL. Drop the parameter and a run against a `DATABASE_URL` that points at a real database wipes that schema at the end.
