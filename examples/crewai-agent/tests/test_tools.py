"""The ordinary order lookup is covered; escalation is intentionally absent."""

from crew import lookup_order


def test_lookup_order_returns_paid_order() -> None:
    result = lookup_order("order-100")
    assert result == {"order_id": "order-100", "status": "paid"}
