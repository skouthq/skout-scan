class Palette:
    def __init__(self, tools):
        self.buttons = tools


def format_label(value: str) -> str:
    return value.upper()


palette = Palette(tools=[format_label])


def tool(function):
    return function


@tool
def encode_label(value: str) -> str:
    return value.encode().hex()


def unused(value):
    return value
