"""CLI entrypoint: `uv run python -m harness <command>`.

All subcommand implementations are imported lazily (inside the branch that
needs them) so `--help`/argument-parsing errors never pay the cost of
importing the pipeline, Codex, or web stack, and so this module can be
imported for testing even before those pieces exist.
"""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="researchAI harness CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run one research project end-to-end")
    target = p_run.add_mutually_exclusive_group(required=True)
    target.add_argument("--topic", help="topic text to research")
    target.add_argument("--resume", metavar="SLUG", help="resume an existing project by slug")

    sub.add_parser("supervise", help="run the 24/7 supervisor loop (queue -> project -> digest)")
    sub.add_parser("drain", help="work through the queue (and resume crashed projects), then exit")
    sub.add_parser("serve", help="run the monitoring dashboard")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        from .config import load_config
        from .lockfile import RunnerActive, acquire_runner_lock
        from . import pipeline
        cfg = load_config()
        try:
            runner_lock = acquire_runner_lock(cfg.root)  # noqa: F841 — held for process lifetime
        except RunnerActive as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if args.resume:
            pipeline.run_project(cfg, resume_slug=args.resume)
        else:
            pipeline.run_project(cfg, topic=args.topic)
        return 0

    if args.command == "supervise":
        from . import supervisor
        supervisor.main()
        return 0

    if args.command == "drain":
        from . import supervisor
        supervisor.main(drain=True)
        return 0

    if args.command == "serve":
        from .web import app
        app.main()
        return 0

    parser.error(f"unknown command {args.command!r}")
    return 2  # pragma: no cover - argparse.error() exits before this


if __name__ == "__main__":
    sys.exit(main())
