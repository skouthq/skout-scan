from agent_contract import create_agent
from langchain_core.tools import tool


class StorageAdapter:
    def fetch(self, key: str) -> str:
        if key == "missing":
            raise LookupError(key)
        return key


adapter = StorageAdapter()


@tool
def read_record(key: str) -> str:
    return adapter.fetch(key)


agent = create_agent(tools=[read_record])
