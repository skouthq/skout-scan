"""A small, statically declared CrewAI refund-analysis crew."""

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool


@tool
def lookup_order(order_id: str) -> dict[str, str]:
    """Return the status needed to evaluate a refund request."""
    return {"order_id": order_id, "status": "paid"}


@tool
def escalate_refund(order_id: str, reason: str) -> dict[str, str]:
    """Send a high-value refund to a human reviewer."""
    return {"order_id": order_id, "status": "escalated", "reason": reason}


refund_analyst = Agent(
    role="Refund Analyst",
    goal="Resolve valid refunds and escalate high-value requests",
    backstory="A support specialist following deterministic refund policy.",
    tools=[lookup_order, escalate_refund],
)

inspect_request = Task(
    description="Look up the order and verify that it is eligible for a refund.",
    expected_output="An order eligibility record.",
    agent=refund_analyst,
    tools=[lookup_order],
)

decide_refund = Task(
    description="Approve routine refunds or escalate high-value requests.",
    expected_output="An approval or escalation decision.",
    agent=refund_analyst,
    context=[inspect_request],
    tools=[escalate_refund],
)

refund_crew = Crew(
    agents=[refund_analyst],
    tasks=[inspect_request, decide_refund],
    process=Process.sequential,
)
