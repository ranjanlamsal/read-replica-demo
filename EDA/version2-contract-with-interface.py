from abc import ABC, abstractmethod


class OrderSubscriber(ABC):
    """
    ROLE: Subscriber Interface (the contract)
    This is the ONLY thing the Publisher knows about subscribers.
    Publisher will call .update(data) on everything in its list.
    """
    @abstractmethod
    def update(self, order: dict) -> None:
        """
        Called by the publisher when an order event occurs.
        Every concrete subscriber MUST implement this.
        """
        
        pass


class OrderSystem:
	"""
	ROLE: Publisher
    Now holds a list of OrderSubscriber (interface), not functions.
    Still zero knowledge of what subscribers do.
	"""
	
	def __init__(self):
		self._subscribers: list[OrderSubscriber] = []

	def subscribe(self, subscriber: OrderSubscriber):
		if not isinstance(subscriber, OrderSubscriber):
			raise TypeError("subscriber must implement OrderSubscriber")
		self._subscribers.append(subscriber)

	def unsubscribe(self, subscriber: OrderSubscriber):
		if subscriber in self._subscribers:
			self._subscribers.remove(subscriber)

	def place_order(self, order: dict):
		print(f"Order placed: {order['id']}")
		self._notify(order)

	def _notify(self, order: dict):
		for subscriber in self._subscribers:
			subscriber.update(order)  # <-- calling the interface method
			


class EmailNotifier(OrderSubscriber):
    """
    ROLE: Concrete Subscriber
    Now formally implement the interface.
    Each is its own class with its own state and dependencies.
    """
    def __init__(self, smtp_host: str):
        self.smtp_host = smtp_host  # own configuration

    def update(self, order: dict) -> None:
        print(f"[{self.smtp_host}] Sending confirmation for {order['id']}")


class InventoryManager(OrderSubscriber):
    def __init__(self, warehouse_id: str):
        self.warehouse_id = warehouse_id

    def update(self, order: dict) -> None:
        print(f"[Warehouse {self.warehouse_id}] Deducting: {order['items']}")

class FraudDetector(OrderSubscriber):
    def update(self, order: dict) -> None:
        score = self._calculate_risk(order)
        print(f"Fraud score for {order['id']}: {score}")

    def _calculate_risk(self, order: dict) -> float:
        return 0.02  
	
# ─────────────────────────────────────────────────────────────
# ROLE: Client
# Note: each subscriber has its own constructor args.
# The publisher doesn't care. It just calls .update().
# ─────────────────────────────────────────────────────────────

order_system = OrderSystem()
order_system.subscribe(EmailNotifier(smtp_host='smtp.myapp.com'))
order_system.subscribe(InventoryManager(warehouse_id='WH-01'))
order_system.subscribe(FraudDetector())

order_system.place_order({'id': 'ORD-002', 'items': ['gadget', 'widget']})
