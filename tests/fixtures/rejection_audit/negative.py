from external import CustomFactory, choose
from langchain_core.tools import tool
from pydantic_ai import Agent


@tool
def refund(amount: int):
    if amount < 0:
        raise ValueError("same name, no agent")
    return amount


@tool
def unknown(amount: int):
    if amount < 0:
        raise ValueError("unknown factory")
    return amount


unknown_agent = CustomFactory(tools=[unknown])


def uncertain(amount: int):
    if amount < 0:
        raise ValueError("ambiguous agent")
    return amount


rebound = Agent("test:model", tools=[uncertain])
rebound = object()


class Storage:
    def read(self, amount):
        if amount < 0:
            raise LookupError("adapter only")
        return amount


storage = Storage()
other = Storage()
ambiguous = storage if choose else other
bound = Agent("test:model", tools=[ambiguous.read])
