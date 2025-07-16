import logging
import os
from logging.config import fileConfig

from flask import current_app

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def get_engine():
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

def get_metadata():
    # This will be used by Alembic to gather the metadata during autogenerate.
    # It needs to be the same metadata object that your models are defined with.
    # Forcing direct import to simplify debugging model discovery issues.
    from app.models import db as target_db  # Ensures app.models.__init__ is run
    logger.info("get_metadata: Using direct import from app.models for db.metadata")
    return target_db.metadata


config.set_main_option('sqlalchemy.url', get_engine_url())

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    """
    Debug filter function for Alembic's autogenerate.
    Logs information about objects being considered for comparison.
    'object': The schema item (Table, Column, Index, etc.) being considered.
    'name': The name of the schema item.
    'type_': A string describing the type of object ('table', 'column', 'index', etc.).
    'reflected': True if the object was reflected from the database, False if it's from target_metadata.
    'compare_to': The sqlalchemy.schema.MetaData object that this item is being compared against.
                  If 'reflected' is True, 'object' is from DB, 'compare_to' is target_metadata (our models).
                  If 'reflected' is False, 'object' is from target_metadata, 'compare_to' is DB metadata.
    """
    obj_metadata_id = id(object.metadata) if hasattr(object, 'metadata') and object.metadata is not None else 'N/A (obj has no .metadata or is None)'
    compare_to_id = id(compare_to) if compare_to is not None else 'N/A'

    logger.info(
        f"INCLUDE_OBJECT_DEBUG: name='{name}' (type='{type_}', reflected={reflected}). "
        f"Object's metadata ID: '{obj_metadata_id}'. "
        f"Comparing against MetaData ID: '{compare_to_id}'."
    )
    # For debugging, include all objects to see full comparison scope.
    return True


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    # Get the application's full SQLAlchemy metadata
    app_metadata = get_metadata()

    # Log diagnostic information about the metadata Alembic will use for comparison
    logger.info(f"RUN_MIGRATIONS_ONLINE_DEBUG: app_metadata object ID: {id(app_metadata)}")
    logger.info(f"RUN_MIGRATIONS_ONLINE_DEBUG: Tables in app_metadata: {sorted(list(app_metadata.tables.keys()))}")

    conf_args = {
        "render_as_batch": True,
        # compare_type and compare_server_default are often useful for SQLite,
        # but temporarily commented out during initial table creation debugging.
        "compare_type": True,
        "compare_server_default": True
    }
    if os.environ.get('FLASK_DEBUG') == '1':
        conf_args["sqlalchemy_echo"] = True

    conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=app_metadata,
            include_object=include_object,
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
