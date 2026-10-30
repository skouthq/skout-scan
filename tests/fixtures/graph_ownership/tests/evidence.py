"""Static evidence only; never import or execute this fixture."""

from workflow import other_graph, review_graph
from workflow import review_graph as reviewed


def test_direct():
    result = review_graph.compile().invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"


def test_import_alias():
    result = reviewed.compile().invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"


async def test_async():
    result = await review_graph.compile().ainvoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"


def test_wrong_graph():
    result = other_graph.compile().invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"


def test_wrong_condition():
    result = review_graph.compile().invoke({"choose": "reject", "amount": 100})
    assert result["route"] == "escalate"


def test_wrong_target():
    result = review_graph.compile().invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "reject"


def test_no_outcome():
    review_graph.compile().invoke({"choose": "escalate", "amount": 900})


def test_conflicting_calls():
    review_graph.compile().invoke({"choose": "escalate", "amount": 900})
    result = other_graph.compile().invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"


def test_unresolved_alias():
    alias = review_graph
    result = alias.invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"


def test_shadowed_import(review_graph):
    result = review_graph.invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"
