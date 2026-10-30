from langgraph.graph import StateGraph


def start(state):
    return state


def choose(state):
    return "escalate" if state["amount"] > 500 else "reject"


def finish(state):
    return {**state, "route": state["choose"]}


review_graph = StateGraph(dict)
other_graph = StateGraph(dict)
review_graph.add_node("start", start)
review_graph.add_node("escalate", finish)
review_graph.add_node("reject", finish)
other_graph.add_node("start", start)
other_graph.add_node("escalate", finish)
other_graph.add_node("reject", finish)
review_graph.add_conditional_edges("start", choose, {"escalate": "escalate", "reject": "reject"})
other_graph.add_conditional_edges("start", choose, {"escalate": "escalate", "reject": "reject"})

# Explicit entry/finish configuration keeps the positive source controls realistic.
review_graph.set_entry_point("start")
review_graph.set_finish_point("escalate")
review_graph.set_finish_point("reject")
other_graph.set_entry_point("start")
other_graph.set_finish_point("escalate")
other_graph.set_finish_point("reject")
