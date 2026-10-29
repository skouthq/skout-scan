"""Pytest-shaped evidence controls; this module is inspected, never imported."""

import pytest
from agent import helper, refund
from dispatch import HANDLERS, dispatch_skill, search
from fallback import cached, read_record
from fixtures_api import Decision, unrelated, validate
from pydantic_ai import ModelRetry


def test_failure_verified():
    with pytest.raises(ValueError):
        refund(-1)


def test_failure_no_outcome():
    refund(-1)


def test_failure_wrong_condition():
    with pytest.raises(ValueError):
        refund(1)


def test_failure_wrong_callable():
    with pytest.raises(ValueError):
        unrelated(-1)


def test_failure_helper_only():
    with pytest.raises(ValueError):
        helper(-1)


def test_refund_negative_valueerror_name_only():
    pass


def test_validator_verified():
    decision = Decision(amount=900)
    assert max(decision.amount, 500) == 900
    with pytest.raises(ModelRetry):
        validate(None, decision)


def test_validator_no_outcome():
    decision = Decision(amount=900)
    assert max(decision.amount, 500) == 900
    validate(None, decision)


def test_validator_wrong_condition():
    decision = Decision(amount=100)
    with pytest.raises(ModelRetry):
        validate(None, decision)


def test_validator_wrong_callable():
    with pytest.raises(ModelRetry):
        unrelated(900)


def test_validator_helper_only():
    with pytest.raises(ModelRetry):
        helper(900)


def test_validate_modelretry_similar_name_only():
    pass


def test_dispatch_selection_spy(monkeypatch):
    seen = []

    def spy(value):
        seen.append(value)
        return value

    monkeypatch.setitem(HANDLERS, "search", spy)
    dispatch_skill("search", "query")
    assert seen == ["query"]


def test_dispatch_no_outcome():
    dispatch_skill("search", "query")


def test_dispatch_adjacent_route():
    assert dispatch_skill("retrieve", "query") == "query"


def test_dispatch_helper_only():
    assert search("query") == "query"


def test_dispatch_wrong_callable():
    assert unrelated("search", "query") == "query"


def test_dispatch_search_similar_name_only():
    pass


def test_fallback_spy(monkeypatch):
    import fallback

    seen = []

    def fail(value):
        raise TimeoutError(value)

    def spy(value):
        seen.append(value)
        return value

    monkeypatch.setattr(fallback, "remote_lookup", fail)
    monkeypatch.setattr(fallback, "cached", spy)
    read_record("query")
    assert seen == ["query"]


def test_fallback_no_outcome():
    read_record("query")


def test_fallback_wrong_exception():
    with pytest.raises(ConnectionError):
        read_record("query")


def test_fallback_helper_only():
    assert cached("query") == "query"


def test_fallback_wrong_callable():
    assert unrelated("query") == "query"


def test_read_record_timeouterror_cached_similar_name_only():
    pass
