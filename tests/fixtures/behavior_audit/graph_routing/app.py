from langgraph.graph import StateGraph


def start_task(state):
    return state


def choose_route(state):
    return "retry" if state["attempt"] < 2 else "fallback"


def retry_task(state):
    return state


def fallback_task(state):
    return {**state, "status": "fallback"}


pipeline = StateGraph(dict)
pipeline.add_node("start", start_task)
pipeline.add_node("retry", retry_task)
pipeline.add_node("fallback", fallback_task)
pipeline.add_edge("retry", "start")
pipeline.add_conditional_edges("start", choose_route, {"retry": "retry", "fallback": "fallback"})
