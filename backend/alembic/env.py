"""Alembic environment: the app's SQLite database, from the models alone.

Its own engine, without the app's PRAGMAs: with foreign_keys=ON, the table rebuild a
batch migration does (DROP TABLE) would delete rows in child tables through ON DELETE
CASCADE. render_as_batch is required, since SQLite cannot alter most things in place.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.database import Base, ensure_data_dirs  # noqa: E402
import app.models  # noqa: E402,F401  (registers every table)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    ensure_data_dirs()
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    ensure_data_dirs()  # the database file may have just been created


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
