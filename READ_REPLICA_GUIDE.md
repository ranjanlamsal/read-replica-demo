# PostgreSQL Read Replica with Django — Complete Guide

A comprehensive reference for understanding, configuring, and demonstrating
PostgreSQL streaming replication with Django's database router.

---

## Table of Contents

1. [What is a Read Replica?](#1-what-is-a-read-replica)
2. [Why Use a Read Replica?](#2-why-use-a-read-replica)
3. [How PostgreSQL Streaming Replication Works](#3-how-postgresql-streaming-replication-works)
4. [Project Architecture](#4-project-architecture)
5. [PostgreSQL Configuration (Master)](#5-postgresql-configuration-master)
6. [Master Initialization Script](#6-master-initialization-script)
7. [Replica Bootstrap Script](#7-replica-bootstrap-script)
8. [Docker Compose Setup](#8-docker-compose-setup)
9. [Django Database Configuration](#9-django-database-configuration)
10. [Django Database Router](#10-django-database-router)
11. [How a Query Gets Routed](#11-how-a-query-gets-routed)
12. [Replication Lag — Theory and Demo](#12-replication-lag--theory-and-demo)
13. [Sync vs Async Replication](#13-sync-vs-async-replication)
14. [Common Pitfalls](#14-common-pitfalls)
15. [Demo Walkthrough](#15-demo-walkthrough)

---

## 1. What is a Read Replica?

A read replica is a copy of your primary (master) database that stays
continuously synchronized and serves read-only queries.

```
                    ┌─────────────────┐
  App writes ──────▶│   MASTER (RW)   │──── WAL stream ────▶ REPLICA (RO)
  App reads  ──────▶│  postgres:5432  │                      postgres:5432
                    └─────────────────┘                      (host: 5433)
```

The replica is not a backup — it is a live, queryable standby that mirrors
every committed change from master in near real-time.

---

## 2. Why Use a Read Replica?

| Problem | How a replica helps |
|---|---|
| Heavy read load slowing down writes | Offload SELECT queries to replica |
| Long-running reports blocking OLTP | Run analytics on replica |
| High availability | Replica can be promoted to master if master fails |
| Geographic distribution | Place replica closer to read-heavy users |

In this demo the primary goal is **read scalability** — all SELECT queries
go to the replica, freeing the master to handle writes exclusively.

---

## 3. How PostgreSQL Streaming Replication Works

### WAL — Write-Ahead Log

Every change in PostgreSQL is first written to the WAL (Write-Ahead Log)
before it touches the actual data files. The WAL is an append-only sequence
of change records (inserts, updates, deletes, schema changes).

```
Transaction commits on master
        │
        ▼
WAL record written to master's WAL segment file
        │
        ▼
WAL sender process streams the record to replica over TCP
        │
        ▼
WAL receiver process on replica writes it to replica's WAL
        │
        ▼
Startup process (recovery) replays the WAL record
        │
        ▼
Data is now visible on replica
```

### Key processes involved

| Process | Where | Role |
|---|---|---|
| `wal sender` | Master | Reads WAL and streams it to replica |
| `wal receiver` | Replica | Receives WAL records from master |
| `startup` (recovery) | Replica | Replays received WAL records onto data files |

### Physical vs Logical replication

This project uses **physical (streaming) replication**:
- Replicates at the byte level — exact copy of master's data files
- Replica is read-only (cannot accept writes)
- All databases and tables are replicated automatically
- Schema changes replicate automatically via WAL

Logical replication (not used here) replicates at the row level and allows
selective table replication and writes on the replica.

---

## 4. Project Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network (db_network)           │
│                                                         │
│  ┌──────────────┐    WAL stream    ┌──────────────────┐ │
│  │  pg_master   │ ───────────────▶ │   pg_replica     │ │
│  │  port: 5432  │                  │   port: 5432     │ │
│  └──────┬───────┘                  └────────┬─────────┘ │
│         │ writes                            │ reads      │
│         └──────────────┬───────────────────┘            │
│                        │                                 │
│                 ┌──────┴──────┐                          │
│                 │ django_app  │                          │
│                 │  port: 8000 │                          │
│                 └─────────────┘                          │
└─────────────────────────────────────────────────────────┘

Host machine:
  master  → localhost:5432
  replica → localhost:5433
  django  → localhost:8000
```

---

## 5. PostgreSQL Configuration (Master)

The master is started with these flags in `docker-compose.yml`:

```yaml
command: >
  postgres
    -c wal_level=replica
    -c max_wal_senders=3
    -c wal_keep_size=64
```

### `wal_level=replica`

Controls how much information is written to the WAL.

| Value | Description |
|---|---|
| `minimal` | Only enough to recover from a crash. Cannot stream. |
| `replica` | Enough for streaming replication. **This is what we use.** |
| `logical` | Enough for logical replication (superset of replica). |

Setting this to `replica` tells PostgreSQL to include enough detail in WAL
records for a standby server to replay them faithfully.

### `max_wal_senders=3`

The maximum number of simultaneous WAL sender processes. Each replica
connection consumes one WAL sender slot. We set 3 to allow:
- 1 for the replica
- 1 spare for `pg_basebackup` during initial bootstrap
- 1 extra buffer

If this is 0, streaming replication is disabled entirely.

### `wal_keep_size=64`

How many megabytes of WAL segment files to keep on disk even after they
have been sent to replicas. This is a safety buffer.

If a replica falls behind and the master has already deleted the WAL
segments the replica needs, the replica cannot catch up and must be
re-bootstrapped. Setting this to 64MB gives the replica a window to
reconnect after a brief outage without needing a full re-sync.

---

## 6. Master Initialization Script

`init-master.sh` runs once when the master container is first created
(via `docker-entrypoint-initdb.d`).

```bash
psql ... <<-EOSQL
  CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'replicator_pass';
  SELECT pg_reload_conf();
EOSQL

echo "host replication replicator 0.0.0.0/0 md5" >> pg_hba.conf
```

### What it does

**Creates a `replicator` user** with the `REPLICATION` privilege. This is
a special PostgreSQL privilege that allows a user to initiate streaming
replication connections. Regular users cannot do this.

**Appends to `pg_hba.conf`** — PostgreSQL's host-based authentication file.
This line:

```
host  replication  replicator  0.0.0.0/0  md5
```

means: allow the `replicator` user to connect from any IP address (`0.0.0.0/0`)
for the purpose of replication, authenticating with an MD5 password.

Without this line, the replica's connection attempt would be rejected
regardless of the correct password.

---

## 7. Replica Bootstrap Script

`init-replica.sh` is the custom entrypoint for the replica container.
Unlike the master, the replica does NOT use `docker-entrypoint-initdb.d`
because we need to replace the data directory entirely with a copy from
master — which conflicts with how the standard postgres entrypoint works.

```bash
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  # First run — bootstrap from master
  pg_basebackup -h $MASTER_HOST -U replicator -D $PGDATA -P -Xs -R
  chown -R postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"
fi

exec gosu postgres postgres
```

### `pg_basebackup` flags explained

| Flag | Meaning |
|---|---|
| `-h postgres_master` | Connect to master at this hostname |
| `-U replicator` | Authenticate as the replicator user |
| `-D /var/lib/postgresql/data` | Write the backup to this directory |
| `-P` | Show progress |
| `-Xs` | Stream WAL during the backup (`-X` = include WAL, `s` = stream mode) |
| `-R` | Write `standby.signal` and connection info into `postgresql.auto.conf` |

### What `-R` does

The `-R` flag is critical. It writes two things into the data directory:

1. **`standby.signal`** — an empty file whose presence tells PostgreSQL
   "start in standby (recovery) mode". Without this file, PostgreSQL would
   start as a normal primary.

2. **`postgresql.auto.conf`** — appends the `primary_conninfo` setting:
   ```
   primary_conninfo = 'host=postgres_master user=replicator password=replicator_pass ...'
   ```
   This tells the replica where to connect to stream WAL from.

### `gosu postgres postgres`

`gosu` is a minimal `sudo`-like tool included in the postgres Docker image.
It switches to the `postgres` user and executes `postgres` (the server binary).
PostgreSQL refuses to run as root for security reasons, so this is required
when our entrypoint script runs as root.

### Idempotency check

```bash
if [ ! -f "$PGDATA/PG_VERSION" ]; then
```

`PG_VERSION` is a file written by `initdb` (and preserved by `pg_basebackup`)
that contains the PostgreSQL major version number. Its presence means the
data directory is already initialized. On subsequent container restarts,
the bootstrap is skipped and postgres starts normally.

---

## 8. Docker Compose Setup

### Service dependency chain

```
pg_master (healthy) → pg_replica (healthy) → django_app
```

`condition: service_healthy` means Docker waits for the healthcheck to pass
before starting the dependent service. The healthcheck uses `pg_isready`
which probes the PostgreSQL port and returns success only when the server
is accepting connections.

Without this, Django would try to connect before PostgreSQL is ready,
causing connection errors on startup.

### Port mapping

```yaml
postgres_master:
  ports: ["5432:5432"]   # host:container

postgres_replica:
  ports: ["5433:5432"]   # host:container — different host port!
```

Inside the Docker network, both containers listen on port `5432`.
The `5433` mapping is only for connecting from your host machine
(e.g. with psql or a GUI tool). Django connects over the internal
network and always uses `5432` for both.

This is why the Django environment variables explicitly set:
```yaml
- MASTER_DB_PORT=5432
- REPLICA_DB_PORT=5432
```
These override the `.env` file which has `REPLICA_DB_PORT=5433`
(the host-side port, correct for local development but wrong inside Docker).

### Named volumes

```yaml
volumes:
  pg_master_data:
  pg_replica_data:
```

Named volumes persist data between container restarts. When you run
`docker compose down -v`, the `-v` flag removes these volumes, forcing
a full re-initialization on next startup (required when changing
replication configuration).

---

## 9. Django Database Configuration

`config/settings.py` defines two database connections:

```python
DATABASES = {
    "default": {                          # ← master (writes)
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("MASTER_DB_HOST", "localhost"),
        "PORT": os.environ.get("MASTER_DB_PORT", "5432"),
        ...
    },
    "replica": {                          # ← replica (reads)
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("REPLICA_DB_HOST", "localhost"),
        "PORT": os.environ.get("REPLICA_DB_PORT", "5432"),
        ...
        "TEST": {
            "MIRROR": "default",          # ← during tests, use master
        },
    },
}

DATABASE_ROUTERS = ["config.db_router.PrimaryReplicaRouter"]
```

### Why `"default"` for master?

Django always uses the `"default"` database unless told otherwise.
Migrations, the admin, and any code that doesn't go through the router
will use `"default"`. Naming the master `"default"` ensures writes
always land on the correct node.

### `TEST.MIRROR`

During `manage.py test`, Django creates a test database. The `MIRROR`
setting tells Django not to create a separate test database for the
replica — instead, use the `"default"` test database for both connections.
This avoids needing a running replica during tests.

### `DATABASE_ROUTERS`

A list of router class paths. Django calls each router in order for every
database operation. The first router to return a non-`None` value wins.

---

## 10. Django Database Router

`config/db_router.py` implements four methods:

### `db_for_read(model, **hints)`

Called before every `SELECT`. Returns `"replica"` unconditionally.

```python
def db_for_read(self, model, **hints):
    return "replica"
```

This means `Author.objects.all()`, `Book.objects.get(pk=1)`, etc. all
hit the replica automatically — no code changes needed in views.

### `db_for_write(model, **hints)`

Called before every `INSERT`, `UPDATE`, `DELETE`. Returns `"default"`.

```python
def db_for_write(self, model, **hints):
    return "default"
```

### `allow_relation(obj1, obj2, **hints)`

Called when Django checks if a ForeignKey or relation between two objects
is valid. Since master and replica are mirrors of each other, objects from
either database can be related.

```python
def allow_relation(self, obj1, obj2, **hints):
    allowed = {"default", "replica"}
    return obj1._state.db in allowed and obj2._state.db in allowed
```

### `allow_migrate(db, app_label, ...)`

Called during `manage.py migrate`. Returns `True` only for `"default"`.
This prevents Django from trying to run migrations on the replica
(which is read-only and gets schema changes via WAL anyway).

```python
def allow_migrate(self, db, app_label, model_name=None, **hints):
    return db == "default"
```

### Bypassing the router

You can always override routing explicitly:

```python
# Force a read to go to master
Author.objects.using("default").filter(name="Alice")

# Force a write to a specific db (rarely needed)
author.save(using="default")
```

This is useful in management commands or scripts that run right after
migrations, before the replica has caught up.

---

## 11. How a Query Gets Routed

Tracing `GET /api/books/` end to end:

```
HTTP GET /api/books/
        │
        ▼
Django view calls Book.objects.all()
        │
        ▼
Django ORM calls db_for_read(Book)
        │
        ▼
PrimaryReplicaRouter.db_for_read() returns "replica"
        │
        ▼
Django opens connection to REPLICA_DB_HOST:REPLICA_DB_PORT
        │
        ▼
SELECT * FROM book ... executed on replica
        │
        ▼
Results returned to view
```

```
HTTP POST /api/books/
        │
        ▼
Django view calls Book.objects.create(...)
        │
        ▼
Django ORM calls db_for_write(Book)
        │
        ▼
PrimaryReplicaRouter.db_for_write() returns "default"
        │
        ▼
Django opens connection to MASTER_DB_HOST:MASTER_DB_PORT
        │
        ▼
INSERT INTO book ... executed on master
        │
        ▼
WAL record streamed to replica asynchronously
```

---

## 12. Replication Lag — Theory and Demo

### What is replication lag?

The time between a transaction committing on master and that change
becoming visible on the replica. In streaming replication this is
typically sub-millisecond on a local network.

### Why does lag exist?

Even though replication is near-instant, there is always a non-zero
propagation delay:

```
Master commits → WAL flushed → WAL sender reads → TCP send → 
WAL receiver writes → Recovery process replays → Visible on replica
```

Each arrow is a small delay. On localhost this totals ~1-5ms.
Over a WAN it could be 50-200ms.

### Demonstrating lag artificially

Since real lag on localhost is too fast to observe, the demo script
uses `pg_wal_replay_pause()` to freeze the replica's WAL replay:

```python
# Pause WAL replay on replica
exec_replica("SELECT pg_wal_replay_pause()")

# Commit data to master — visible on master immediately
Author.objects.using("default").create(...)

# Replica sees nothing — WAL is queued but not replayed
Author.objects.using("replica").count()  # → 0

# Resume — replica replays queued WAL
exec_replica("SELECT pg_wal_replay_resume()")

# Replica catches up within milliseconds
Author.objects.using("replica").count()  # → 1
```

### Useful replication monitoring queries

Run these on master to check replication status:

```sql
-- Check connected replicas and their lag
SELECT
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    (sent_lsn - replay_lsn) AS replication_lag_bytes
FROM pg_stat_replication;

-- Check WAL sender processes
SELECT * FROM pg_stat_replication;
```

Run on replica:

```sql
-- Check if replica is in recovery (standby) mode
SELECT pg_is_in_recovery();  -- should return true

-- Check if WAL replay is paused
SELECT pg_is_wal_replay_paused();

-- Check lag from master's perspective
SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;
```

---

## 13. Sync vs Async Replication

### Asynchronous (default — what this project uses)

```
Master: COMMIT → returns success to client
                 ↓ (fire and forget)
Replica: receives WAL ... replays ... eventually consistent
```

- Master does not wait for replica acknowledgement
- Fastest write performance
- Small risk of data loss if master crashes before WAL reaches replica
- Replica may be slightly behind master

### Synchronous

```
Master: COMMIT → waits for replica to confirm WAL received → returns success
```

- Zero data loss guarantee
- Slower writes (round-trip to replica on every commit)
- Enable by adding to master's postgres command:
  ```
  -c synchronous_standby_names='*'
  ```

For most web applications, async replication is the right choice.
The data loss window is typically < 1 second and the performance
benefit is significant.

---

## 14. Common Pitfalls

### Read-your-own-writes problem

A user creates a record, then immediately reads it. The write goes to
master, the read goes to replica — but the replica hasn't caught up yet,
so the user sees nothing.

**Solutions:**
- Use `using("default")` for reads immediately after writes in the same request
- Use sticky sessions to route a user's reads to master for a short window
- Accept eventual consistency (often fine for non-critical reads)

### Migrations and replication lag

`manage.py migrate` runs on master. The replica gets the schema changes
via WAL, but there's a brief window where master has the new tables and
the replica doesn't. Any read query hitting the replica during this window
will fail with `relation does not exist`.

**Solution:** In management commands that run right after migrations,
use `.using("default")` for any reads that check newly created tables.

### Replica is read-only

Any attempt to write to the replica directly will fail:

```
ERROR: cannot execute INSERT in a read-only transaction
```

The router prevents this in normal Django code, but be careful with
raw SQL or direct connection usage.

### Volume persistence

If you change replication configuration (e.g. the replicator password),
you must run `docker compose down -v` to wipe volumes and re-initialize.
Simply restarting containers will not re-run the init scripts.

---

## 15. Demo Walkthrough

### Setup

```bash
docker compose down -v   # clean slate
docker compose up --build
```

### Verify replication is working

```bash
# Connect to master
docker exec -it pg_master psql -U postgres -d library_db

# Check WAL senders (should show 1 connected replica)
SELECT client_addr, state, sent_lsn, replay_lsn FROM pg_stat_replication;
```

```bash
# Connect to replica
docker exec -it pg_replica psql -U postgres -d library_db

# Confirm it's in standby mode
SELECT pg_is_in_recovery();  -- → t
```

### Show routing in action

```bash
# Watch Django logs while hitting the API
curl http://localhost:8000/api/books/
# Log shows: [DB ROUTER] SELECT books → alias='replica' host=postgres_replica

curl -X POST http://localhost:8000/api/books/ \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "author": 1, "isbn": "test-999", ...}'
# Write goes to master, replica gets it via WAL
```

### Run the WAL lag demo

```bash
docker exec django_app uv run python scripts/replication_lag_demo.py
```

Expected output:
```
Step 1 — Pausing WAL replay on replica...
         WAL replay paused: True

Step 2 — Writing author + 3 books to MASTER (committed)...
         MASTER sees: authors=1, books=3

Step 3 — Polling REPLICA while WAL is paused (expect 0)...
         [REPLICA] poll 1: authors=0, books=0
         [REPLICA] poll 2: authors=0, books=0
         [REPLICA] poll 3: authors=0, books=0
         [REPLICA] poll 4: authors=0, books=0

Step 4 — Resuming WAL replay on replica...
         WAL replay paused: False

Step 5 — Polling REPLICA after WAL resume (waiting for catch-up)...
         [REPLICA] poll 1 (50.2ms): authors=1, books=3

  ✓ Replica caught up in 50.2ms after WAL resume
```

This demonstrates:
- Data committed to master is immediately visible on master
- The replica sees nothing while WAL replay is paused (simulating lag)
- The moment WAL replay resumes, the replica catches up in milliseconds
