"""Keep historical structural identity bytes across supported Python interpreters."""

import ast

import pytest

from agentguard.ast_compat import stable_ast_dump


@pytest.mark.parametrize(
    "source, mode, expected",
    [
        (
            "refund()",
            "eval",
            "Expression(body=Call(func=Name(id='refund', ctx=Load()), args=[], keywords=[]))",
        ),
        (
            "def refund():\n    return None\n",
            "exec",
            "Module(body=[FunctionDef(name='refund', args=arguments(posonlyargs=[], args=[], "
            "kwonlyargs=[], kw_defaults=[], defaults=[]), "
            "body=[Return(value=Constant(value=None))], "
            "decorator_list=[], type_params=[])], type_ignores=[])",
        ),
    ],
)
def test_dump_preserves_python312_canonical_empty_fields(source, mode, expected):
    assert stable_ast_dump(ast.parse(source, mode=mode)) == expected
