from pydantic_ai import Agent


def lookup_order(order_id: str) -> str:
    return order_id


first = Agent("test", tools=[lookup_order, lookup_order])
second = Agent("test", tools=[lookup_order])
