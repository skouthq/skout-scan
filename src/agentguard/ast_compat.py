"""Preserve the established Python 3.12 AST representation on newer interpreters."""

import ast
import sys


def stable_ast_dump(
    node: ast.AST, *, annotate_fields: bool = True, include_attributes: bool = False
) -> str:
    """Keep empty fields in structural identities/fingerprints, as Python 3.12 did.

    Python 3.13 introduced show_empty=False as the default. Explicitly restoring
    empty fields preserves existing canonical records; it changes no parsed facts.
    """
    options = {"annotate_fields": annotate_fields, "include_attributes": include_attributes}
    if sys.version_info >= (3, 13):
        options["show_empty"] = True
    return ast.dump(node, **options)
