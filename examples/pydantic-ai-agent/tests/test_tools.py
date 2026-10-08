"""The registered lookup tool is covered; validator retry is intentionally absent."""

from types import SimpleNamespace

from agent import RefundDependencies, lookup_order


def test_lookup_order_reads_dependency() -> None:
    context = SimpleNamespace(deps=RefundDependencies(orders={"order-100": "paid"}))
    result = lookup_order(context, "order-100")
    assert result == "paid"
