#!/bin/bash
# Custom entrypoint for replica container.
# If the data directory is empty (or has no PG_VERSION), bootstrap via pg_basebackup.
# Otherwise, just start postgres normally.

set -e

MASTER_HOST="${MASTER_DB_HOST:-postgres_master}"
REPLICA_INDEX="${REPLICA_INDEX:-1}"
PGDATA=/var/lib/postgresql/data

if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo "No existing data found. Bootstrapping replica_${REPLICA_INDEX} from master..."

  echo "Waiting for master to be ready..."
  until pg_isready -h "$MASTER_HOST" -p 5432 -U postgres; do
    sleep 2
  done

  echo "Master is ready. Running pg_basebackup..."
  PGPASSWORD=replicator_pass pg_basebackup \
    -h "$MASTER_HOST" \
    -U replicator \
    -D "$PGDATA" \
    -P -Xs -R

  # Fix ownership so postgres user can read the files
  chown -R postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"

  echo "Bootstrap complete. Starting replica_${REPLICA_INDEX}..."
else
  echo "Existing data found. Starting replica_${REPLICA_INDEX} normally..."
fi

exec gosu postgres postgres
