from agent_contract import create_agent
from langchain_core.tools import tool
from remote_store import remote_lookup


def cached_record(key: str) -> str:
    return key


@tool
def read_record(key: str) -> str:
    if not key:
        raise ValueError("key required")
    try:
        return remote_lookup(key)
    except TimeoutError:
        return cached_record(key)


agent = create_agent(tools=[read_record])
