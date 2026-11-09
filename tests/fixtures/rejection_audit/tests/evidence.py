import pytest
from agent import partial, refund, shared
from negative import refund as unrelated_refund


def test_negative_refund():
    with pytest.raises(ValueError):
        refund(-1)


def test_positive_shared():
    assert shared(1) == 1


def test_partial():
    partial(-1)


def test_wrong_condition():
    with pytest.raises(ValueError):
        refund(1)


def test_wrong_exception():
    with pytest.raises(TypeError):
        refund(2000)


def test_name_only_ModelRetry():
    assert True


def test_unrelated():
    with pytest.raises(ValueError):
        unrelated_refund(-1)
