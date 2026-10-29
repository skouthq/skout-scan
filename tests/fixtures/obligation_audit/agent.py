"""Source-only audit fixture, never executed by the audit."""

from pydantic_ai import Agent

first = Agent("test")


@first.tool_plain
def refund(amount: int) -> int:
    if amount < 0:
        raise ValueError("negative amount")
    return amount


second = Agent("test", tools=[refund])


def helper(amount: int) -> int:
    return amount
