"""Readable policy checks; Skout also uses the JSONL graph evidence."""

from workflow import approve_refund


def test_small_refund_is_approved() -> None:
    result = approve_refund({"order_id": "order-100", "refund_amount": 125, "route": "pending"})
    assert result["route"] == "approved"
