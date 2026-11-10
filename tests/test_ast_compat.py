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


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "import fallback",
            "Module(body=[Import(names=[alias(name='fallback')])], type_ignores=[])",
        ),
        (
            "from fallback import cached",
            "Module(body=[ImportFrom(module='fallback', names=[alias(name='cached')], "
            "level=0)], type_ignores=[])",
        ),
    ],
)
def test_eager_import_preserves_canonical_bytes_without_mutating_tree(source, expected):
    tree = ast.parse(source)
    node = tree.body[0]
    # Reproduce Python 3.15's additional field on older test interpreters too.
    if "is_lazy" not in node._fields:
        node._fields = (*node._fields, "is_lazy")
    node.is_lazy = 0
    fields = node._fields

    assert stable_ast_dump(tree) == expected
    assert node._fields == fields
    assert node.is_lazy == 0


def test_explicit_lazy_import_is_not_collapsed_into_eager_import():
    tree = ast.parse("import fallback")
    node = tree.body[0]
    if "is_lazy" not in node._fields:
        node._fields = (*node._fields, "is_lazy")
    node.is_lazy = 1

    assert "is_lazy=1" in stable_ast_dump(tree)
