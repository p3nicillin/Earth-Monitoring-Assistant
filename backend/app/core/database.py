from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

is_sqlite = settings.database_url.startswith("sqlite")
engine_options: dict[str, object] = {"pool_pre_ping": True}
if not is_sqlite:
    engine_options.update(pool_size=10, max_overflow=20)

engine = create_async_engine(settings.database_url, **engine_options)


if is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(dbapi_connection: object, connection_record: object) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        for function_name in ("AsGeoJSON", "ST_AsGeoJSON"):
            dbapi_connection.create_function(  # type: ignore[attr-defined]
                function_name, 1, lambda value: value
            )


SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
