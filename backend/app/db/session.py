from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.engine import create_database_engine
from app.observability.metrics import metrics


engine = create_database_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def update_pool_metrics() -> None:
    pool = engine.pool
    metrics.set_database_pool(
        size=int(getattr(pool, "size", lambda: 0)()),
        checked_out=int(getattr(pool, "checkedout", lambda: 0)()),
        overflow=max(0, int(getattr(pool, "overflow", lambda: 0)())),
        capacity=settings.DATABASE_POOL_SIZE + settings.DATABASE_MAX_OVERFLOW,
    )


@event.listens_for(engine, "checkout")
def _pool_checked_out(*_args) -> None:
    update_pool_metrics()


@event.listens_for(engine, "checkin")
def _pool_checked_in(*_args) -> None:
    update_pool_metrics()


@event.listens_for(engine, "handle_error")
def _database_error(*_args) -> None:
    metrics.observe_database_error()
    metrics.observe_dependency("postgres", "failure")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
