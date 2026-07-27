"""Command-line interface for Citation Chaos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

from . import __version__
from .adapters import load_adapter
from .io import read_json, write_json, write_text
from .operators import generate_suite, operator_infos
from .reporters import render_operator_list, render_report
from .runner import run_suite
from .schemas import Answer, Corpus, MutationSuite
from .seeds import starter_project


_SAMPLE_ADAPTER = '''"""Example Citation Chaos adapter.

Replace the body with a call to your retrieval/generation pipeline.  Importing
this file executes trusted local code in the Citation Chaos process.
"""
from citation_chaos import Answer


def run_pipeline(question, corpus):
    # A real adapter should build an Answer from `question` and `corpus`.
    # This explicit abstention keeps the starter safe until you connect one.
    return Answer(status="abstained", claims=(), reason="adapter not connected")
'''


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="citation-chaos",
        description="Deterministic mutation testing for grounded AI output pipelines.",
        epilog="Mutation scores test response behavior; they do not prove semantic truth.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a synthetic starter project")
    init.add_argument("directory", nargs="?", default="citation-chaos-starter")
    init.add_argument("--force", action="store_true", help="overwrite generated starter files")

    mutate = commands.add_parser("mutate", help="generate deterministic mutation cases")
    mutate.add_argument("corpus", help="baseline corpus JSON path")
    mutate.add_argument("--answer", required=True, help="baseline structured answer JSON path")
    mutate.add_argument("--question", help="question; defaults to corpus metadata.question")
    mutate.add_argument(
        "--operator",
        action="append",
        dest="operators",
        help="operator name; repeat to select several (default: all)",
    )
    mutate.add_argument("--seed", type=int, default=0, help="non-negative deterministic seed")
    mutate.add_argument("--strict", action="store_true", help="fail if any selected operator is inapplicable")
    mutate.add_argument("--output", "-o", default="mutations.json", help="manifest path or '-' for stdout")

    run = commands.add_parser("run", help="execute and score a mutation manifest")
    run.add_argument("manifest", help="mutation suite JSON path or '-' for stdin")
    run.add_argument(
        "--adapter",
        default="reference",
        help="'reference' or trusted MODULE:OBJECT / PATH.py:OBJECT",
    )
    run.add_argument(
        "--format",
        choices=("text", "json", "junit", "sarif"),
        default="text",
        dest="output_format",
    )
    run.add_argument("--output", "-o", default="-", help="report path or '-' for stdout")
    run.add_argument("--traceback", action="store_true", help="include adapter tracebacks in error results")

    operators = commands.add_parser("operators", help="inspect the operator registry")
    operator_commands = operators.add_subparsers(dest="operator_command", required=True)
    operator_list = operator_commands.add_parser("list", help="list deterministic mutation operators")
    operator_list.add_argument("--format", choices=("text", "json"), default="text", dest="output_format")

    return parser


def _init(directory: str, force: bool) -> int:
    destination = Path(directory)
    if destination.exists() and not destination.is_dir():
        raise ValueError("init destination is not a directory: %s" % destination)
    destination.mkdir(parents=True, exist_ok=True)
    corpus, answer, question = starter_project()
    generated = {
        "corpus.json": json.dumps(corpus.to_dict(), indent=2, sort_keys=True) + "\n",
        "answer.json": json.dumps(answer.to_dict(), indent=2, sort_keys=True) + "\n",
        "question.txt": question + "\n",
        "adapter.py": _SAMPLE_ADAPTER,
    }
    conflicts = [name for name in generated if (destination / name).exists()]
    if conflicts and not force:
        raise ValueError(
            "refusing to overwrite %s (use --force)" % ", ".join(str(destination / name) for name in conflicts)
        )
    for name, content in generated.items():
        (destination / name).write_text(content, encoding="utf-8")
    sys.stdout.write("Initialized Citation Chaos starter in %s\n" % destination)
    sys.stdout.write("Next: citation-chaos mutate %s --answer %s\n" % (destination / "corpus.json", destination / "answer.json"))
    return 0


def _mutate(args: argparse.Namespace) -> int:
    if args.seed < 0:
        raise ValueError("--seed must be non-negative")
    corpus = Corpus.from_dict(read_json(args.corpus))
    answer = Answer.from_dict(read_json(args.answer))
    question = args.question
    if question is None:
        candidate = corpus.metadata.get("question")
        question = candidate if isinstance(candidate, str) else None
    if question is None or not question.strip():
        raise ValueError("provide --question or corpus metadata.question")
    suite, skipped = generate_suite(
        corpus,
        answer,
        question,
        operator_names=args.operators,
        seed=args.seed,
        strict=args.strict,
    )
    if not suite.mutations:
        raise ValueError("no mutations were generated" + ((": " + "; ".join(skipped)) if skipped else ""))
    write_json(args.output, suite.to_dict())
    if args.output != "-":
        sys.stdout.write("Wrote %d mutations to %s\n" % (len(suite.mutations), args.output))
    for message in skipped:
        sys.stderr.write("skipped %s\n" % message)
    return 0


def _run(args: argparse.Namespace) -> int:
    suite = MutationSuite.from_dict(read_json(args.manifest))
    adapter = load_adapter(args.adapter)
    report = run_suite(suite, adapter, include_traceback=args.traceback)
    write_text(args.output, render_report(report, args.output_format))
    return 0 if report.successful else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return _init(args.directory, args.force)
        if args.command == "mutate":
            return _mutate(args)
        if args.command == "run":
            return _run(args)
        if args.command == "operators" and args.operator_command == "list":
            sys.stdout.write(render_operator_list(operator_infos(), args.output_format))
            return 0
        parser.error("unknown command")
    except Exception as exc:
        sys.stderr.write("citation-chaos: error: %s\n" % exc)
        return 2
    return 2
