from pydantic_evals import Case, Dataset

cases = Dataset(
    cases=[
        Case(
            name="retry",
            inputs={"amount": 501},
            expected_output="ModelRetry",
            metadata={"tools": ["validate_refund"]},
        )
    ]
)
