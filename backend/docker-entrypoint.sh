#!/bin/sh
set -e

echo "Waiting for database..."
python -c "
import time
import sqlalchemy
from app.core.config import settings

for attempt in range(30):
    try:
        engine = sqlalchemy.create_engine(settings.DATABASE_URL)
        with engine.connect():
            print('Database is ready.')
            break
    except Exception as exc:
        print(f'Database not ready yet ({attempt+1}/30): {exc}')
        time.sleep(1)
else:
    raise SystemExit('Database never became ready.')
"

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Running migrations..."
    alembic upgrade head
fi

if [ "${RUN_SEED:-true}" = "true" ] && [ "${ENV:-development}" = "development" ] && [ "$SEED_ON_START" = "true" ]; then
    echo "Seeding development data..."
    python seed.py
elif [ "${RUN_SEED:-true}" = "true" ] && [ "${ENV:-development}" = "e2e" ] && [ "$SEED_ON_START" = "true" ]; then
    echo "Seeding isolated E2E fixture data..."
    python e2e_seed.py
fi

exec "$@"
