from external import adapter
from langchain_core.tools import tool


def fallback(value):
    return value


def handler(value):
    return value


HANDLERS = {"run": handler}
HANDLERS.setdefault("late", handler)


@tool
def dispatch(key, value):
    return HANDLERS[key](value)


@tool
def delegate(value):
    return adapter.execute(value)


@tool
def catch_all(value):
    try:
        return adapter.execute(value)
    except Exception:
        return fallback(value)


@tool
def catch_bare(value):
    try:
        return adapter.execute(value)
    except:  # noqa: E722 - deliberately unsupported catch-all audit control
        return fallback(value)
