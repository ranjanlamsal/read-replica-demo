from abc import ABC, abstractmethod
from collections import defaultdict


class EventListener(ABC):
    # ─────────────────────────────────────────────────────────────
    # ROLE: Subscriber Interface
    # Same as V2 — all subscribers must implement update().
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    def update(self, event_type: str, data: dict) -> None:
        ...


class EventManager:
    # ─────────────────────────────────────────────────────────────
    # ROLE: EventManager (extracted subscription infrastructure)
    # This is NOT the publisher. It only manages the subscriber list
    # and dispatches notifications. The publisher delegates to it.
    # ─────────────────────────────────────────────────────────────

    def __init__(self):
        # Maps event_type (string) -> list of EventListener
        self._listeners: dict[str, list[EventListener]] = defaultdict(list)

    def subscribe(self, event_type: str, listener: EventListener):
        self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: str, listener: EventListener):
        self._listeners[event_type].remove(listener)

    def notify(self, event_type: str, data: dict):
        """Notify only listeners registered for this specific event type."""
        for listener in self._listeners.get(event_type, []):
            listener.update(event_type, data)


class OrderSystem:
    # ─────────────────────────────────────────────────────────────
    # ROLE: Publisher — now delegates subscription management
    # Publisher's job: business logic + emit events via its manager.
    # ─────────────────────────────────────────────────────────────

    """
    Has an EventManager as a public attribute.
    External code subscribes via: order_system.events.subscribe()
    This is exactly the pattern refactoring.guru shows for Editor.
    """

    def __init__(self):
        self.events = EventManager()   # <-- delegation

    def place_order(self, order: dict):
        print(f"Order placed: {order['id']}")
        self.events.notify('order:placed', order)   # <-- delegate

    def ship_order(self, order: dict):
        print(f"Order shipped: {order['id']}")
        self.events.notify('order:shipped', order)  # <-- different event

    def cancel_order(self, order: dict):
        print(f"Order cancelled: {order['id']}")
        self.events.notify('order:cancelled', order)


class EmailNotifier(EventListener):
    # ─────────────────────────────────────────────────────────────
    # ROLE: Concrete Subscribers
    # Now each subscriber can specify WHICH events it cares about.
    # ─────────────────────────────────────────────────────────────

    def update(self, event_type: str, data: dict) -> None:
        messages = {
            'order:placed':    f"Confirmation sent for {data['id']}",
            'order:shipped':   f"Shipment notice sent for {data['id']}",
            'order:cancelled': f"Cancellation notice sent for {data['id']}",
        }
        print(f"Email: {messages.get(event_type, 'Unknown event')}")


class InventoryManager(EventListener):
    # ─────────────────────────────────────────────────────────────
    # ROLE: Concrete Subscribers
    # Now each subscriber can specify WHICH events it cares about.
    # ─────────────────────────────────────────────────────────────

    """Only cares about placed and cancelled orders."""

    def update(self, event_type: str, data: dict) -> None:
        if event_type == 'order:placed':
            print(f"Inventory: Deducting for {data['id']}")
        elif event_type == 'order:cancelled':
            print(f"Inventory: Restoring for {data['id']}")


class ShippingTracker(EventListener):
    # ─────────────────────────────────────────────────────────────
    # ROLE: Concrete Subscribers
    # Now each subscriber can specify WHICH events it cares about.
    # ─────────────────────────────────────────────────────────────

    """Only cares about shipped orders."""

    def update(self, event_type: str, data: dict) -> None:
        print(f"Tracking: Creating shipment record for {data['id']}")


# ─────────────────────────────────────────────────────────────
# ROLE: Client
# Subscribes each listener to specific events, not all events.
# ─────────────────────────────────────────────────────────────

email    = EmailNotifier()
inventory = InventoryManager()
shipping  = ShippingTracker()
order_system = OrderSystem()

order_system.events.subscribe('order:placed',    email)
order_system.events.subscribe('order:placed',    inventory)
order_system.events.subscribe('order:shipped',   email)
order_system.events.subscribe('order:shipped',   shipping)
order_system.events.subscribe('order:cancelled', email)
order_system.events.subscribe('order:cancelled', inventory)

order = {'id': 'ORD-003', 'items': ['item1']}
order_system.place_order(order)
order_system.ship_order(order)