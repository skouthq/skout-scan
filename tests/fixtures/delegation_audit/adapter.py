from langchain_core.tools import tool
from langgraph.graph import StateGraph


def internal_helper(value):
    return value


class Storage:
    def fetch(self, value):
        if not value:
            raise LookupError(value)
        return internal_helper(value)


class Other:
    def fetch(self, value):
        return value


storage = Storage()
other = Other()


@tool
def read_record(value):
    return storage.fetch(value)


@tool
def read_other(value):
    return other.fetch(value)


async def callback(value):
    return await storage.fetch(value)


graph = StateGraph(dict)
graph.add_node("read", callback)
