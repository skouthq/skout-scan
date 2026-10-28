from agent_contract import create_agent
from langchain_core.tools import tool


@tool
def read_record(key: str) -> str:
    return key


agent = create_agent(tools=[read_record])


@tool
def catalogued_export(key: str) -> str:
    return key
