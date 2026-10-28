from pydantic_ai import Agent


class Palette:
    def __init__(self, tools):
        self.buttons = tools


def tool(function):
    return function


@tool
def encode(value: str) -> str:
    return value.upper()


palette = Palette(tools=[encode])
Agent = Palette  # noqa: F811 - deliberate import rebinding negative control
shadowed = Agent(tools=[encode])
