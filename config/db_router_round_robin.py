# config/db_router.py
import itertools
import threading
from django.conf import settings

class PrimaryReplicaRouter:

    # Class-level state shared across all instances of this router.
    # threading.local() ensures each thread has its own counter,
    # avoiding lock contention between concurrent requests.
    _local = threading.local()

    def _replica_aliases(self):
        return [
            alias for alias in settings.DATABASES
            if alias != "default"
        ]

    def _get_replica(self):
        replicas = self._replica_aliases()
        if not replicas:
            return "default"

        # Initialize a per-thread cycle iterator on first use
        if not hasattr(self._local, "cycle"):
            self._local.cycle = itertools.cycle(replicas)

        return next(self._local.cycle)

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
