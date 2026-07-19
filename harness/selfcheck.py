"""Offline self-check gate: can this checkout of the harness be trusted to run?

``python -m harness selfcheck`` validates the copy of the code it is run from
(cwd wins module resolution; the root is RESEARCHAI_ROOT or the parent of this
package): every module imports, config.yaml parses, the model policy is intact,
the CLI exposes its required commands, every prompt template exists, and the
test suite (if one exists) passes. Exit 0 = trustworthy.

This is the gate ``harness.self_improve`` applies to every self-generated
change before adopting it, and it doubles as a smoke test after manual edits.

PROTECTED: this file is on the self-improvement protected-paths list -- the
automated improver may never edit the gate that judges its own changes. In the
same spirit, the model policy is pinned *here*, not just in config.yaml:
changing which models the harness may call is a human decision. Every check
must stay offline (no proxy, no network) and fast.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import traceback
from pathlib import Path

# Human-pinned model policy (see PLAN.md): exactly the three gpt-5.6 variants.
EXPECTED_ALLOWED_MODELS = {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
REQUIRED_ROLES = {"reasoning", "coding", "reviewer", "polish", "utility"}

REQUIRED_COMMANDS = {"run", "supervise", "drain", "serve", "improve", "selfcheck"}

MODULES = [
    "harness.config", "harness.state", "harness.lockfile", "harness.llm",
    "harness.literature", "harness.journal", "harness.codex_runner",
    "harness.stages", "harness.stages.intake", "harness.stages.survey",
    "harness.stages.ideate", "harness.stages.design", "harness.stages.implement",
    "harness.stages.analyze", "harness.stages.writeup", "harness.stages.review",
    "harness.stages.archive", "harness.pipeline", "harness.supervisor",
    "harness.self_improve", "harness.web.app", "harness.__main__",
]

REQUIRED_PROMPTS = [
    "analyze", "design", "digest", "ideate", "implement_codex", "intake_propose",
    "journal_context", "lessons", "polish", "review", "self_improve",
    "survey_queries", "survey_triage", "survey_write", "writeup", "writeup_revise",
]

TESTS_TIMEOUT_SECONDS = 600


def _check_imports() -> str | None:
    failed = []
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            failed.append(f"{name}:\n{traceback.format_exc(limit=3)}")
    return "\n".join(failed) if failed else None


def _check_config(root: Path) -> str | None:
    from harness.config import load_config
    cfg = load_config(root)
    if set(cfg.models.allowed) != EXPECTED_ALLOWED_MODELS:
        return (f"model allowlist changed: {sorted(cfg.models.allowed)} != "
                f"{sorted(EXPECTED_ALLOWED_MODELS)} (model policy is human-only)")
    missing_roles = REQUIRED_ROLES - set(cfg.models.roles)
    if missing_roles:
        return f"missing model roles: {sorted(missing_roles)}"
    stray = {m for m in cfg.models.roles.values() if m not in EXPECTED_ALLOWED_MODELS}
    if stray:
        return f"roles reference disallowed models: {sorted(stray)}"
    return None


def _check_cli() -> str | None:
    import argparse
    from harness.__main__ import build_parser
    parser = build_parser()
    sub = next(
        (a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None
    )
    if sub is None:
        return "CLI has no subcommands"
    missing = REQUIRED_COMMANDS - set(sub.choices)
    return f"CLI lost required commands: {sorted(missing)}" if missing else None


def _check_prompts(root: Path) -> str | None:
    missing = [
        n for n in REQUIRED_PROMPTS
        if not (root / "prompts" / f"{n}.md").is_file()
        or not (root / "prompts" / f"{n}.md").read_text(encoding="utf-8").strip()
    ]
    return f"missing/empty prompt templates: {missing}" if missing else None


def _check_tests(root: Path) -> str | None:
    if not (root / "tests").is_dir():
        return None  # no suite yet; imports/config checks are the floor
    try:
        importlib.import_module("pytest")
    except ImportError:
        return "tests/ exists but pytest is not installed (add it to the dev deps)"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "tests"],
        cwd=root, capture_output=True, text=True, timeout=TESTS_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        return "pytest failed:\n" + (proc.stdout + proc.stderr)[-1500:]
    return None


def main() -> int:
    from harness.config import find_root
    root = find_root()
    print(f"selfcheck: checking harness at {root}")

    checks = [
        ("imports", _check_imports),
        ("config+model-policy", lambda: _check_config(root)),
        ("cli-commands", _check_cli),
        ("prompt-templates", lambda: _check_prompts(root)),
        ("tests", lambda: _check_tests(root)),
    ]
    failures = 0
    for name, fn in checks:
        try:
            err = fn()
        except Exception:
            err = traceback.format_exc(limit=5)
        if err is None:
            print(f"selfcheck: {name}: ok")
        else:
            failures += 1
            indented = "\n".join("    " + line for line in err.splitlines())
            print(f"selfcheck: {name}: FAIL\n{indented}")

    print(f"selfcheck: {'PASS' if not failures else f'FAIL ({failures} check(s))'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
