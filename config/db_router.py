"""
PrimaryReplicaRouter
────────────────────
This is the heart of read replica routing at the application layer.

Django calls these methods automatically before every database operation:

    db_for_read()   → called before every SELECT
    db_for_write()  → called before every INSERT / UPDATE / DELETE
    allow_migrate() → called during migrations

Flow:
  READ  (SELECT)  → routed to 'replica'  (standby node)
  WRITE (INSERT / UPDATE / DELETE / migrations) → routed to 'default' (master)
"""
import random
from django.conf import settings

class PrimaryReplicaRouter:

    def _replica_aliases(self):
        return [alias for alias in settings.DATABASES if alias != "default"]

    # ── Reads → replica ──────────────────────────────────────────────────────
    def db_for_read(self, model, **hints):
        """
        All SELECT queries go to the replica.

        The `hints` dict can carry a `instance` key (the object being
        refreshed).  We don't need to inspect it here — every read goes
        to the replica regardless.
        """
        instance = hints.get("instance")
        if instance is not None and instance._state.db == "default":
            return "default"
        replicas = self._replica_aliases()
        return random.choice(replicas) if replicas else "default"

    # ── Writes → master ──────────────────────────────────────────────────────
    def db_for_write(self, model, **hints):
        """
        All INSERT / UPDATE / DELETE go to the master.
        """
        return "default"

    # ── Relations must live on the same DB ───────────────────────────────────
    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations between any two objects as long as they both live
        on either master or replica (they mirror each other so this is safe).
        """
        return (
            obj1._state.db in settings.DATABASES
            and obj2._state.db in settings.DATABASES
        )

    # ── Migrations always run on master ──────────────────────────────────────
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Schema changes (CREATE TABLE, ALTER TABLE…) only on the master.
        The replica gets them automatically through WAL streaming.
        """
        return db == "default"
