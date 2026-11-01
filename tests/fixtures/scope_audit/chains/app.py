from langchain_core.tools import tool
from pydantic_ai import Agent


def search(value):
    return value


def retrieve(value):
    return value


HANDLERS = {"search": search, "retrieve": retrieve}


class Storage:
    def fetch(self, value):
        return value


storage = Storage()


def primary(value):
    return value


def cached(value):
    return value


@tool
def dispatch(key, value):
    return HANDLERS[key](value)


@tool
def lookup(value):
    return storage.fetch(value)


@tool
def resilient(value):
    try:
        return primary(value)
    except TimeoutError:
        return cached(value)


selected = Agent("test", tools=[dispatch, lookup, resilient])
other = Agent("test")
