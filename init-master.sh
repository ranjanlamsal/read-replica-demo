#!/bin/bash
# Runs on master only once — creates a replication user
# so the replica can stream WAL from master

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'replicator_pass';
  SELECT pg_reload_conf();
EOSQL

# Allow replicator to connect for replication
echo "host replication replicator 0.0.0.0/0 md5" >> /var/lib/postgresql/data/pg_hba.conf

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "SELECT pg_reload_conf();"

echo "Primary init complete. Replication user created."
