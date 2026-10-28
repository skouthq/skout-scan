from langchain_core.tools import tool
from remote_store import remote_lookup


def cached(value):
    return value


def unavailable(value):
    return value


@tool
def read_record(value):
    try:
        return remote_lookup(value)
    except TimeoutError:
        return cached(value)
    except (ConnectionError, FileNotFoundError):
        return unavailable(value)
