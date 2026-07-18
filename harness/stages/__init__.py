"""Science-pipeline stages.

Each stage module exposes ``run(state, cfg, llm) -> ProjectState`` and mutates
the passed state in place (writing its own artifacts under projects/<slug>/),
returning it for the pipeline to checkpoint. Stages never call ``state.save`` —
that is the pipeline's job so there is exactly one writer per stage boundary.

This package root also hosts the prompt-template loader shared by every stage
(and by ``harness.literature`` / ``harness.journal``). Templates live in
``prompts/<name>.md`` and use ``{{placeholder}}`` markers so that literal single
braces in JSON schema examples pass through untouched.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..config import Config

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def render(template: str, **kw: object) -> str:
    """Substitute ``{{key}}`` markers; leave every other brace untouched."""
    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in kw:
            raise KeyError(f"prompt template references undefined variable {key!r}")
        return str(kw[key])
    return _PLACEHOLDER.sub(_sub, template)


@lru_cache(maxsize=64)
def _read_template(path: str) -> str:
    from pathlib import Path
    return Path(path).read_text(encoding="utf-8")


def load_prompt(cfg: Config, name: str, **kw: object) -> str:
    """Read ``prompts/<name>.md`` and render its ``{{...}}`` placeholders."""
    template = _read_template(str(cfg.prompts_dir / f"{name}.md"))
    return render(template, **kw) if kw else template
