from pydantic_ai import Agent as Assistant
from pydantic_ai import ModelRetry

assistant = Assistant("test")


@assistant.output_validator
def validate(ctx, output):
    if output.amount > 500:
        raise ModelRetry("review required")
    return output


@assistant.output_validator
async def validate_async(ctx, output):
    return output
