"""
replication_lag_demo.py
───────────────────────
Demonstrates actual WAL replication lag between master and replica.

Strategy:
  1. Pause WAL streaming on master (pg_wal_replay_pause on replica)
  2. Commit data to master — it's visible on master immediately
  3. Poll replica rapidly — data is NOT there yet (WAL not replayed)
  4. Resume WAL replay on replica
  5. Poll replica again — data appears as WAL catches up

Usage (inside container):
    uv run python scripts/replication_lag_demo.py
"""

import os
import sys
import time

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connections
from library.models import Author, Book

AUTHOR_NAME = "WAL Lag Demo Author"
BOOKS = [
    {"title": "WAL Book One",   "isbn": "wal-001", "published_year": 2021, "genre": "Fiction", "rating": 4.1},
    {"title": "WAL Book Two",   "isbn": "wal-002", "published_year": 2022, "genre": "Sci-Fi",  "rating": 3.8},
    {"title": "WAL Book Three", "isbn": "wal-003", "published_year": 2023, "genre": "Mystery", "rating": 4.5},
]


def exec_replica(sql):
    with connections["replica"].cursor() as cur:
        cur.execute(sql)
        try:
            return cur.fetchone()
        except Exception:
            return None


def exec_master(sql):
    with connections["default"].cursor() as cur:
        cur.execute(sql)
        try:
            return cur.fetchone()
        except Exception:
            return None


def cleanup():
    Author.objects.using("default").filter(name=AUTHOR_NAME).delete()


def main():
    cleanup()

    print("\n=== WAL Replication Lag Demo ===\n")

    # ── Step 1: pause WAL replay on replica ──────────────────────────────────
    print("Step 1 — Pausing WAL replay on replica...")
    exec_replica("SELECT pg_wal_replay_pause()")
    paused = exec_replica("SELECT pg_is_wal_replay_paused()")
    print(f"         WAL replay paused: {paused[0]}\n")

    # ── Step 2: commit data to master ────────────────────────────────────────
    print("Step 2 — Writing author + 3 books to MASTER (committed)...")
    author = Author.objects.using("default").create(name=AUTHOR_NAME, bio="WAL demo")
    for b in BOOKS:
        Book.objects.using("default").create(author=author, **b)

    master_count = Author.objects.using("default").filter(name=AUTHOR_NAME).count()
    print(f"         MASTER sees: authors={master_count}, books={Book.objects.using('default').filter(author=author).count()}\n")

    # ── Step 3: poll replica — should see nothing (WAL paused) ───────────────
    print("Step 3 — Polling REPLICA while WAL is paused (expect 0)...")
    for i in range(4):
        r_authors = Author.objects.using("replica").filter(name=AUTHOR_NAME).count()
        r_books   = Book.objects.using("replica").filter(author__name=AUTHOR_NAME).count()
        print(f"         [REPLICA] poll {i+1}: authors={r_authors}, books={r_books}")
        time.sleep(0.3)

    # ── Step 4: resume WAL replay ─────────────────────────────────────────────
    print("\nStep 4 — Resuming WAL replay on replica...")
    exec_replica("SELECT pg_wal_replay_resume()")
    paused = exec_replica("SELECT pg_is_wal_replay_paused()")
    print(f"         WAL replay paused: {paused[0]}\n")

    # ── Step 5: poll replica until it catches up ──────────────────────────────
    print("Step 5 — Polling REPLICA after WAL resume (waiting for catch-up)...")
    start = time.monotonic()
    for i in range(20):
        r_authors = Author.objects.using("replica").filter(name=AUTHOR_NAME).count()
        r_books   = Book.objects.using("replica").filter(author__name=AUTHOR_NAME).count()
        elapsed = (time.monotonic() - start) * 1000
        print(f"         [REPLICA] poll {i+1} ({elapsed:.1f}ms): authors={r_authors}, books={r_books}")
        if r_authors > 0 and r_books == len(BOOKS):
            print(f"\n  ✓ Replica caught up in {elapsed:.1f}ms after WAL resume\n")
            break
        time.sleep(0.05)
    else:
        print("\n  ✗ Replica did not catch up within 1s\n")

    print("=== Done ===\n")
    cleanup()


if __name__ == "__main__":
    main()
