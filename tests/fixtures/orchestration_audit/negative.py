from unrelated_api import Graph, Task, Validator


def helper(state):
    return state


fake_graph = Graph()
fake_graph.add_node("helper", helper)
fake_task = Task(agent=helper)
fake_validator = Validator()


@fake_validator.output_validator
def validate(ctx, output):
    return output
