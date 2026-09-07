from alembic import context

from alpendata_api.database import database_factory
from alpendata_api.models import Base
from alpendata_api.settings import Settings


def migrate(connection):
    sqlite = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True, transactional_ddl=True
    )
    with context.begin_transaction():
        if sqlite:
            # Pysqlite otherwise autocommits DDL and resets FK deferral during
            # a batch rebuild. Begin the real transaction before any reflection.
            if not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN")
            previous_deferral = connection.exec_driver_sql("PRAGMA defer_foreign_keys").scalar()
            connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        context.run_migrations()
        if sqlite:
            # FK enforcement stays enabled. Validate the rebuilt graph before
            # settling deferred references to temporarily replaced tables.
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("migration_foreign_key_validation_failed")
            connection.exec_driver_sql("PRAGMA defer_foreign_keys=" + ("ON" if previous_deferral else "OFF"))


if context.is_offline_mode():
    context.configure(
        url=Settings.from_environment().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    migrate(context.config.attributes["connection"])
else:
    engine, _ = database_factory(Settings.from_environment().database_url)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
