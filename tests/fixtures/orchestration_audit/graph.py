import langgraph.graph as lg
from langgraph.graph import StateGraph as Builder


def choose_route(state):
    return "yes"


def review(state):
    return state


async def approve(state):
    return state


first = Builder(dict)
second = lg.StateGraph(dict)
first.add_node("review", review)
first.add_node("copy", review)
second.add_node("review", approve)
second.add_node("again", review)
first.add_edge("review", "copy")
first.add_conditional_edges("review", choose_route, {"yes": "copy"})
