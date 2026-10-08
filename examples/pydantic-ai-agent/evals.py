"""A Pydantic Evals dataset associated with the known refund agent."""

from agent import refund_agent
from pydantic_evals import Case, Dataset

routine_refund = Case(
    name="routine refund decision",
    inputs={"order_id": "order-100", "refund_amount": 125},
    expected_output={"approved": True, "refund_amount": 125},
    metadata={"policy": "automatic refund limit"},
)

refund_dataset = Dataset(
    name="refund decisions",
    cases=[routine_refund],
)


def run_refund_case(inputs: dict[str, object]) -> object:
    return refund_agent.run_sync(str(inputs))


refund_dataset.evaluate_sync(run_refund_case)
