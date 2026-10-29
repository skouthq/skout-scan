"""Pydantic Evals artifacts are evidence candidates, not automatic exception/route proof."""

from pydantic_evals import Case

failure_case = Case(
    name="pydantic_failure_expected_exception",
    inputs={"amount": -1},
    expected_output={"exception": "ValueError"},
    metadata={"tools": ["refund"]},
)
route_case = Case(
    name="pydantic_route_wrong_owner",
    inputs={"select_review_route": "escalate", "refund_amount": 900},
    expected_output={"path": ["escalate_refund"]},
    metadata={"tools": ["unrelated_graph"]},
)
