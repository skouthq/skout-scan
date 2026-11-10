"""Preserve the established Python 3.12 AST representation on newer interpreters."""

import ast
import sys
from copy import deepcopy


def stable_ast_dump(
    node: ast.AST, *, annotate_fields: bool = True, include_attributes: bool = False
) -> str:
    """Keep empty fields in structural identities/fingerprints, as Python 3.12 did.

    Python 3.13 introduced show_empty=False as the default. Explicitly restoring
    empty fields preserves existing canonical records; it changes no parsed facts.
    """
    # Python 3.15 adds is_lazy=0 to ordinary imports. Keep their historical
    # representation, but retain nonzero values so lazy imports remain distinct.
    # Work on a copy: extraction must still see the untouched parsed tree.
    if any(
        isinstance(child, ast.Import | ast.ImportFrom) and getattr(child, "is_lazy", None) == 0
        for child in ast.walk(node)
    ):
        node = deepcopy(node)
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Import | ast.ImportFrom)
                and getattr(child, "is_lazy", None) == 0
            ):
                child.__dict__["_fields"] = tuple(
                    field for field in child._fields if field != "is_lazy"
                )
    options = {"annotate_fields": annotate_fields, "include_attributes": include_attributes}
    if sys.version_info >= (3, 13):
        options["show_empty"] = True
    return ast.dump(node, **options)
