from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from app.core.config import settings


def _build_db_url() -> str:
    # asyncpg URL
    return f"postgresql+asyncpg://{settings.PG_USER}:{settings.PG_PASSWORD}@{settings.PG_HOST}:{settings.PG_PORT}/{settings.PG_DB}"


connect_args = {}
if settings.PG_SSLMODE:
    # asyncpg SSL: pass an SSLContext via "ssl" is best, but for simplicity we use PGSSL env-style params.
    # SQLAlchemy will pass through 'ssl' only if provided; asyncpg also supports "ssl" param.
    # We'll build SSLContext if sslrootcert path is provided.
    import ssl
    if settings.PG_SSLMODE.lower() in ("verify-full", "verify-ca") and settings.PG_SSLROOTCERT_PATH:
        ctx = ssl.create_default_context(cafile=settings.PG_SSLROOTCERT_PATH)
        # verify-full implies hostname check enabled
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        connect_args["ssl"] = ctx
    elif settings.PG_SSLMODE.lower() in ("require", "prefer"):
        ctx = ssl.create_default_context()
        connect_args["ssl"] = ctx

engine = create_async_engine(_build_db_url(), pool_pre_ping=True, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def db_ping() -> bool:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
