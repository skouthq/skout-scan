from langchain_core.tools import tool


@tool
def utility(value):
    return value
