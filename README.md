# Read Replica Demo — Django + PostgreSQL

A minimal but production-realistic demo of **read replica routing** at the
application layer, using Django's database router API.

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         Django Application           │
                    │                                      │
                    │   GET /api/books/   POST /api/books/ │
                    │         │                  │         │
                    │    db_for_read()      db_for_write() │
                    │         │                  │         │
                    └─────────┼──────────────────┼─────────┘
                              │                  │
                   reads      │                  │  writes
                   (SELECT)   ▼                  ▼  (INSERT/UPDATE/DELETE)
                    ┌──────────────┐    ┌──────────────────┐
                    │  PostgreSQL  │◄───│   PostgreSQL      │
                    │   REPLICA    │    │    MASTER         │
                    │  (standby)   │WAL │   (primary)       │
                    │  port 5433   │streaming port 5432    │
                    └──────────────┘    └──────────────────┘
```

The replica receives every change from the master in real time via
**WAL (Write-Ahead Log) streaming**. It is a hot standby — read-only,
always up to date (with a small replication lag).

---

## Key Concepts

### 1. Django `DATABASES` — two aliases

```python
DATABASES = {
    "default": { "HOST": "postgres_master", ... },  # writes
    "replica": { "HOST": "postgres_replica", ... }, # reads
}
```

Django lets you define as many database connections as you want. The names
are just aliases — the router decides which one is used.

### 2. `DATABASE_ROUTERS` — the traffic cop

```python
DATABASE_ROUTERS = ["config.db_router.PrimaryReplicaRouter"]
```

Before Django executes any SQL it calls your router's methods:

| Django calls          | Router returns | Result                  |
|-----------------------|----------------|-------------------------|
| `db_for_read(model)`  | `"replica"`    | SELECT → replica node   |
| `db_for_write(model)` | `"default"`    | INSERT/UPDATE → master  |
| `allow_migrate(db)`   | `db == "default"` | migrations on master only |

### 3. The Router (`config/db_router.py`)

```python
class PrimaryReplicaRouter:
    def db_for_read(self, model, **hints):
        return "replica"          # all reads → replica

    def db_for_write(self, model, **hints):
        return "default"          # all writes → master

    def allow_relation(self, obj1, obj2, **hints):
        return True               # both DBs mirror each other

    def allow_migrate(self, db, app_label, **hints):
        return db == "default"    # schema changes on master only
```

Zero application code changes needed in views — routing is transparent.

### 4. WAL Streaming Replication (PostgreSQL)

- Master is started with `wal_level=replica` and `max_wal_senders=3`
- A `replicator` user is created on master with `REPLICATION` privilege
- Replica does a `pg_basebackup` on first boot, then streams WAL continuously
- Replica runs in **hot standby** mode — readable, not writable

---

## Project Structure

```
read_replica_demo/
├── config/
│   ├── settings.py        # DATABASES + DATABASE_ROUTERS config
│   ├── db_router.py       # ← THE ROUTER (read this first)
│   └── urls.py
├── library/
│   ├── models.py          # Author, Book
│   ├── serializers.py
│   ├── views.py           # GET→replica, POST→master (logged in response)
│   ├── urls.py
│   └── migrations/
├── scripts/
│   └── populate.py        # Seeds 10 authors + 50 books via master
├── docker-compose.yml     # master + replica + django
├── init-master.sh         # Creates replication user on master
├── init-replica.sh        # pg_basebackup + standby setup
├── Dockerfile
└── requirements.txt
```

---

## Running It

### Prerequisites
- Docker + Docker Compose

### Start everything

```bash
docker-compose up --build
```

On first boot:
1. `postgres_master` starts, runs `init-master.sh` (creates replication user)
2. `postgres_replica` starts, runs `init-replica.sh` (base backup + standby)
3. `web` runs migrations (on master only, via router), seeds data, starts server

### API Endpoints

| Method | URL | DB Used | Description |
|--------|-----|---------|-------------|
| GET | `/api/books/` | **replica** | List all books |
| POST | `/api/books/` | **master** | Create a book |
| GET | `/api/books/<id>/` | **replica** | Get single book |
| GET | `/api/authors/` | **replica** | List authors |
| POST | `/api/authors/` | **master** | Create author |
| GET | `/api/db-status/` | — | Show DB alias → host mapping |

### Test the routing

```bash
# READ → should show "db_used": "replica"
curl http://localhost:8000/api/books/

# WRITE → should show "db_used": "default"
curl -X POST http://localhost:8000/api/books/ \
  -H "Content-Type: application/json" \
  -d '{"title":"Dune","author":1,"isbn":"978-0441013593","published_year":1965,"genre":"Sci-Fi","rating":4.8}'

# See which host each alias resolves to
curl http://localhost:8000/api/db-status/
```

### Check replication lag

```bash
# On master — see connected replicas and lag
docker exec pg_master psql -U postgres -c \
  "SELECT client_addr, state, sent_lsn, write_lsn, replay_lsn FROM pg_stat_replication;"

# On replica — confirm it's in recovery (standby) mode
docker exec pg_replica psql -U postgres -c "SELECT pg_is_in_recovery();"
```

---

## Important Caveat: Read-After-Write

Because writes go to master and reads go to replica, there is a small
**replication lag** (usually milliseconds). If you write a record and
immediately read it, the replica might not have it yet.

For operations that need immediate consistency (e.g. "show the user what
they just submitted"), you can force a read from master:

```python
# Force a specific queryset to use master
book = Book.objects.using("default").get(pk=pk)
```

Use sparingly — the whole point is to offload reads to the replica.

---

## Stopping

```bash
docker-compose down          # keep volumes (data persists)
docker-compose down -v       # nuke volumes (fresh start)
```
