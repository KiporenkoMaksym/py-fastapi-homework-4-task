import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.database.models.base import Base

settings = get_settings()

SQLITE_DATABASE_URL = f"sqlite+aiosqlite:///{settings.PATH_TO_DB}"
sqlite_engine = create_async_engine(SQLITE_DATABASE_URL, echo=False)
AsyncSQLiteSessionLocal = sessionmaker(  # type: ignore
    bind=sqlite_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


_tables_initialized = False
_initialization_lock = asyncio.Lock()


async def initialize_sqlite_database() -> None:
    global _tables_initialized

    if _tables_initialized:
        return

    async with _initialization_lock:
        if _tables_initialized:
            return

        async with sqlite_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        _tables_initialized = True


async def get_sqlite_db() -> AsyncGenerator[AsyncSession, None]:
    await initialize_sqlite_database()

    async with AsyncSQLiteSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_sqlite_db_contextmanager() -> AsyncGenerator[AsyncSession, None]:
    await initialize_sqlite_database()

    async with AsyncSQLiteSessionLocal() as session:
        yield session


async def reset_sqlite_database() -> None:
    """
    Reset the SQLite database.

    This function drops all existing tables and recreates them.
    It is useful for testing purposes or when resetting the database is required.

    Warning: This action is irreversible and will delete all stored data.

    :return: None
    """
    async with sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
