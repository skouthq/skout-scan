"""A small refund workflow using statically declared LangGraph routes."""

from typing import TypedDict

from langgraph.graph import StateGraph


class RefundState(TypedDict):
    order_id: str
    refund_amount: int
    route: str


def lookup_order(state: RefundState) -> RefundState:
    return state


def approve_refund(state: RefundState) -> RefundState:
    return {**state, "route": "approved"}


def review_refund(state: RefundState) -> RefundState:
    return state


def escalate_refund(state: RefundState) -> RefundState:
    return {**state, "route": "human_review"}


def reject_refund(state: RefundState) -> RefundState:
    return {**state, "route": "rejected"}


def select_review_route(state: RefundState) -> str:
    return "escalate" if state["refund_amount"] > 500 else "reject"


refund_graph = StateGraph(RefundState)
refund_graph.add_node("lookup_order", lookup_order)
refund_graph.add_node("approve_refund", approve_refund)
refund_graph.add_edge("lookup_order", "approve_refund")

review_graph = StateGraph(RefundState)
review_graph.add_node("review_refund", review_refund)
review_graph.add_node("escalate_refund", escalate_refund)
review_graph.add_node("reject_refund", reject_refund)
review_graph.add_conditional_edges(
    "review_refund",
    select_review_route,
    {
        "escalate": "escalate_refund",
        "reject": "reject_refund",
    },
)
