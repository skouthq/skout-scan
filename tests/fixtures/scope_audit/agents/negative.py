"""Names and unrelated APIs cannot establish selectable roots."""


class Workflow:
    def __init__(self, tools):
        self.tools = tools


def agent(value):
    return value


def execute(value):
    return value


workflow = Workflow(tools=[agent, execute])
