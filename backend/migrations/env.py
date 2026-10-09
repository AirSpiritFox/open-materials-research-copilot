from alembic import context
from app.db import Base, make_engine
config = context.config
target_metadata = Base.metadata
def run_migrations():
    engine = make_engine()
    if context.is_offline_mode():
        context.configure(url=str(engine.url), target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()
run_migrations()
