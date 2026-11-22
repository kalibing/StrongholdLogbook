from alembic import context
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

from logbook.config import settings

url = URL.create("postgresql+psycopg", **settings.database_url)
if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
