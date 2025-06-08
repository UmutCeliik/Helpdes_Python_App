import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy import text

from alembic import context

# Projenizin ana dizinini Python path'ine ekleyin
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Kendi modellerinizin Base objesini ve modellerin kendisini import edin
from database_pkg.database import Base
from database_pkg import db_models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def process_revision_directives(context, revision, directives):
    """
    Şemaların (users_schema, tickets_schema) veritabanında otomatik
    oluşturulmasını sağlayan helper fonksiyon.
    """
    # DÜZELTME: Bağlantıya doğrudan context.connection ile erişilir.
    connection = context.connection
    
    # Modellerinizdeki şemaları al
    schemas_in_models = set()
    for table in target_metadata.tables.values():
        if table.schema:
            schemas_in_models.add(table.schema)

    # Veritabanında var olan şemaları al
    if schemas_in_models:
        existing_schemas = set(connection.dialect.get_schema_names(connection))
        # Eksik şemaları oluştur
        for schema in schemas_in_models - existing_schemas:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()