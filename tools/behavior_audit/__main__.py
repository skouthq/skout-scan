"""Run with python -m tools.behavior_audit; not a production skout command."""

import argparse
from pathlib import Path

from tools.behavior_audit.runner import (
    DEFAULT_INVENTORY,
    PROJECT_ROOT,
    load_corpus,
    run_audit,
    serialize_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Development-only behavior discovery audit")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    corpus = load_corpus(args.inventory)
    report = serialize_report(run_audit(corpus))
    if args.output:
        output = args.output.resolve()
        if (
            output == args.inventory.resolve()
            or ".agentguard" in output.parts
            or any(
                output.is_relative_to((PROJECT_ROOT / repository.path).resolve())
                for repository in corpus.repositories
            )
        ):
            parser.error(
                "Audit output must not overwrite an inventory or audited repository/state."
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
