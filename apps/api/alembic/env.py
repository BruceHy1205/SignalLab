from __future__ import annotations

import os

from alembic import context
from signal_agents.models import Base as AgentsBase
from signal_datahub.models import Base as DatahubBase
from signal_live.models import Base as LiveBase
from signal_papertrade.models import Base as PapertradeBase
from signal_tracker.models import Base as TrackerBase
from sqlalchemy import engine_from_config, pool

target_metadata = [
    DatahubBase.metadata,
    TrackerBase.metadata,
    PapertradeBase.metadata,
    AgentsBase.metadata,
    LiveBase.metadata,
]

config = context.config
database_url = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://signal:signal@localhost:5432/signal"
)
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
