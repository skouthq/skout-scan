from external import create_agent, imported_tool, load_tools
from langchain_core.tools import tool
from pydantic_ai import Agent


def local(value):
    return value


@tool
def registered(value):
    return value


selected = Agent("test", tools=[registered])
dynamic = Agent("test", tools=load_tools())
external = Agent("test", tools=[imported_tool])
rebound = Agent("test", tools=[local])
rebound = selected
custom = create_agent(tools=[local])
