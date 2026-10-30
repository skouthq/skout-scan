from pydantic_evals import Case

correct = Case(
    name="pydantic_bound",
    inputs={"choose": "escalate", "amount": 900},
    expected_output={"route": "escalate"},
    metadata={"graph_owner": {"source_file": "workflow.py", "symbol": "review_graph"}},
)
wrong = Case(
    name="pydantic_wrong",
    inputs={"choose": "escalate", "amount": 900},
    expected_output={"route": "escalate"},
    metadata={"graph_owner": {"source_file": "workflow.py", "symbol": "other_graph"}},
)
