# config/db_router.py
import random
import time
import threading
from django.conf import settings
from django.db import connections

class PrimaryReplicaRouter:

    # Cache lag data so we are not querying pg_stat_replication on every read
    _lag_cache = {}
    _lag_cache_lock = threading.Lock()
    _lag_cache_ttl = 10  # seconds

    def _replica_aliases(self):
        return [
            alias for alias in settings.DATABASES
            if alias != "default"
        ]

    def _get_replica_lags(self):
        """
        Query pg_stat_replication on the primary to get replay lag per replica.
        Returns a dict of {alias: lag_seconds} for connected replicas.
        Results are cached for _lag_cache_ttl seconds to avoid overhead.
        """
        now = time.monotonic()

        with self._lag_cache_lock:
            if self._lag_cache.get("ts", 0) + self._lag_cache_ttl > now:
                return self._lag_cache.get("data", {})

        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("""
                    SELECT client_addr,
                           EXTRACT(EPOCH FROM replay_lag) AS lag_seconds
                    FROM pg_stat_replication
                    WHERE state = 'streaming'
                """)
                rows = cursor.fetchall()
        except Exception:
            return {}

        lag_by_ip = {str(row[0]): row[1] or 0 for row in rows}

        # Map IPs back to Django aliases by comparing HOST in DATABASES
        lag_by_alias = {}
        for alias in self._replica_aliases():
            host = settings.DATABASES[alias]["HOST"]
            if host in lag_by_ip:
                lag_by_alias[alias] = lag_by_ip[host]

        with self._lag_cache_lock:
            self._lag_cache = {"ts": now, "data": lag_by_alias}

        return lag_by_alias

    def _get_replica(self):
        replicas = self._replica_aliases()
        if not replicas:
            return "default"

        lags = self._get_replica_lags()

        if not lags:
            # Fall back to random if lag data unavailable
            return random.choice(replicas)

        # Pick the replica with the lowest lag
        return min(lags, key=lags.get)

    def db_for_read(self, model, **hints):
        instance = hints.get("instance")
        if instance is not None and instance._state.db == "default":
            return "default"
        return self._get_replica()

    def db_for_write(self, model, **hints):
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        db_set = set(settings.DATABASES.keys())
        return obj1._state.db in db_set and obj2._state.db in db_set

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return db == "default"
