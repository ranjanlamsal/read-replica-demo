class OrderSystem:
	"""
	ROLE: Publisher / Subject
	Responsibility: place orders AND notify interested parties.
	Knows nothing about what observers do — only that they exist.
	"""
	
	def __init__(self):
		self._observers = [] # The subscriber list
	
	def subscribe(self, observer_fn):
		"""Any callable can subscribe."""
		self._observers.append(observer_fn)
		
	def unsubscribe(self, observer_fn):
		self._observers.remove(observer_fn)
	
	def place_order(self, order: dict):
		"""
		Business logic. After doing its own work, it notifies.
		Note: it does NOT call send_email, deduct_inventory directly.
		It has no imports for those. It just calls its subscriber list.
		"""
		print(f"Order placed: {order['id']}")
		self._notify(order)
	
	def _notify(self, data):
		"""Loop through subscribers and call each one."""
		for observer_fn in self._observers:
			observer_fn(data)


# ─────────────────────────────────────────────────────────────
# ROLE: Concrete Subscribers (plain functions here)
# Each does something completely different with the same event.
# ─────────────────────────────────────────────────────────────

def send_confirmation_email(order: dict):
	print(f"Email: Confirmation sent for order {order['id']}")

def deduct_inventory(order: dict):
	print(f"Inventory: Deducting items for order {order['id']}")

def notify_warehouse(order: dict):
	print(f"Slack: Warehouse notified for order {order['id']}")


# ─────────────────────────────────────────────────────────────
# ROLE: Client
# Creates the publisher, creates/references subscribers,
# wires them together, then triggers business logic.
# ─────────────────────────────────────────────────────────────

order_system = OrderSystem()
order_system.subscribe(send_confirmation_email)
order_system.subscribe(deduct_inventory)
order_system.subscribe(notify_warehouse)

# Trigger the event
order_system.place_order({'id': 'ORD-001', 'items': ['widget']})

# Output:
# Order placed: ORD-001
# Email: Confirmation sent for order ORD-001
# Inventory: Deducting items for order ORD-001
# Slack: Warehouse notified for order ORD-001