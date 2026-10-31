from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context
from app.core.config import get_settings
from app.models import document, evaluation, pipeline, study, telemetry  # noqa: F401

config = context.config
if config.config_file_name is not None:
    # Sem isto, rodar as migracoes no lifespan desliga os loggers do uvicorn e os erros somem.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool

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
