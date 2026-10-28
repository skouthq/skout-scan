import crewai as crew
import pydantic_ai
from langchain_core.tools import tool as exposed
from pydantic_ai import Agent as Assistant


@exposed
def fetch(key: str) -> str:
    return key


alias_agent = Assistant("test", tools=(fetch,))
qualified_agent = pydantic_ai.Agent("test", tools={fetch})
crew_agent = crew.Agent(role="reader", tools=[fetch])


@alias_agent.tool_plain
def report(key: str) -> str:
    return key
