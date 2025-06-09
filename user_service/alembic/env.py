# user_service/alembic/env.py

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text
import sqlalchemy as sa # <-- sa importu önemli

from alembic import context

# --- Sistem Yolu Ayarı ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Model Import Ayarı ---
from user_service.database import Base
from user_service import db_models

# --- Alembic Yapılandırması ---
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Veritabanı URL'sini Ortam Değişkeninden Okuma ---
db_url_from_env = os.getenv("DATABASE_URL")
if not db_url_from_env:
    raise ValueError("DATABASE_URL ortam değişkeni bulunamadı veya boş. Lütfen ayarlayın.")
config.set_main_option("sqlalchemy.url", db_url_from_env)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        
        # --- ŞEMA OLUŞTURMA BÖLÜMÜ (YENİ EKLENDİ) ---
        # Gerekli şemaların var olduğundan emin ol
        schemas_in_models = set()
        for table in target_metadata.tables.values():
            if table.schema:
                schemas_in_models.add(table.schema)
        
        for schema in schemas_in_models:
            # "CREATE SCHEMA IF NOT EXISTS" komutu şema zaten varsa hata vermez.
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        
        # Şema oluşturma işleminin veritabanına yansıdığından emin olmak için commit
        connection.commit()
        # --- ŞEMA OLUŞTURMA SONU ---

        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()