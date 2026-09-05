from alembic import context

from alpendata_api.database import database_factory
from alpendata_api.models import Base
from alpendata_api.settings import Settings


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


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
