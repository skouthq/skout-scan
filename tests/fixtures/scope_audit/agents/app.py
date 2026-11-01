from langchain_core.tools import tool
from pydantic_ai import Agent


@tool
def only_alpha(value):
    if not value:
        raise ValueError("alpha needs a value")
    return value


@tool
def only_beta(value):
    if not value:
        raise TypeError("beta needs a value")
    return value


@tool
def shared(value):
    if value == "bad":
        raise LookupError(value)
    return value


@tool
def unregistered(value):
    if not value:
        raise RuntimeError(value)
    return value


alpha = Agent("test", tools=[only_alpha, shared])
beta = Agent("test", tools=[only_beta, shared])
