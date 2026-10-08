"""A Pydantic AI refund assistant with a deterministic validation rule."""

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext


@dataclass
class RefundDependencies:
    orders: dict[str, str]


class RefundDecision(BaseModel):
    order_id: str
    approved: bool
    refund_amount: int


refund_agent = Agent(
    "test",
    deps_type=RefundDependencies,
    output_type=RefundDecision,
    instructions="Approve eligible routine refunds and flag high-value requests for review.",
)


@refund_agent.tool
def lookup_order(ctx: RunContext[RefundDependencies], order_id: str) -> str:
    return ctx.deps.orders.get(order_id, "missing")


@refund_agent.output_validator
def validate_refund(
    ctx: RunContext[RefundDependencies], decision: RefundDecision
) -> RefundDecision:
    if decision.refund_amount > 500:
        raise ModelRetry("High-value refunds require human review")
    return decision
