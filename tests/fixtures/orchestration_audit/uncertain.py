from crewai import Agent, Task
from external_callbacks import callback, imported_agent, make_agent, unknown
from langgraph.graph import StateGraph
from pydantic_ai import Agent as Assistant


def node_name():
    return "runtime"


def local(state):
    return state


graph = StateGraph(dict)
graph.add_node("external", callback)
graph.add_node(node_name(), local)
graph.add_node("generated", lambda state: state)
rebound = StateGraph(dict)
rebound = unknown
rebound.add_node("uncertain", local)
worker = Agent(role="reader")
worker = imported_agent
assigned = Task(agent=worker)
computed = Task(agent=make_agent())
external = Task(agent=imported_agent)
assistant = Assistant("test")
assistant = unknown


@assistant.output_validator
def validate(ctx, output):
    return output
