from pydantic_ai import Agent, ModelRetry

alpha = Agent("test:model")
beta = Agent("test:model")


@alpha.tool_plain
def refund(amount: int):
    if amount < 0:
        raise ValueError("negative")
    if amount > 1000:
        raise RuntimeError("too large")
    return amount


def shared(amount: int):
    if amount < 0:
        raise ValueError("negative")
    return amount


# Existing extraction supports constructor lists, not method-call registration.
first = Agent("test:model", tools=[shared])
second = Agent("test:model", tools=[shared])


@alpha.output_validator
def validate_refund(ctx, output):
    if output.amount > 500:
        raise ModelRetry("review required")
    return output


@alpha.tool_plain
def partial(amount: int):
    if amount < 0:
        raise ValueError("negative")
    return amount


@alpha.tool_plain
def plain(amount: int):
    return amount
