"""The only way the harness talks to models.

Enforces the model policy (allowlist: gpt-5.6 sol/terra/luna; reasoning → sol
via the `reasoning` role), retries transient failures with backoff, honors the
STOP kill switch, and appends one JSON line per call to logs/usage.jsonl:

    {"ts", "model", "role", "stage", "project",
     "prompt_tokens", "completion_tokens", "total_tokens", "duration_ms"}

Usage:
    llm = LLM(cfg, project="my-slug")
    text = llm.chat("reasoning", "prompt...", system="...", stage="ideate")
    data = llm.chat_json("reasoning", "reply in JSON ...", stage="ideate")
"""
from __future__ import annotations

import json
import random
import time
import datetime as dt
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from .config import Config


class ModelNotAllowed(ValueError):
    pass


class Paused(RuntimeError):
    """Raised when the STOP file exists; callers checkpoint and unwind."""


class LLMUnavailable(RuntimeError):
    """Raised after retries exhaust on a transient model-service failure."""


class LLM:
    def __init__(self, cfg: Config, project: str = ""):
        self.cfg = cfg
        self.project = project
        self._client = OpenAI(base_url=cfg.proxy.base_url, api_key=cfg.proxy.api_key,
                              timeout=600.0, max_retries=0)

    def resolve(self, role_or_model: str) -> str:
        model = self.cfg.models.roles.get(role_or_model, role_or_model)
        if model not in self.cfg.models.allowed:
            raise ModelNotAllowed(
                f"{model!r} is not in the allowed model list {self.cfg.models.allowed}")
        return model

    def chat(
        self,
        role: str,
        prompt: str | None = None,
        *,
        messages: list[dict] | None = None,
        system: str | None = None,
        stage: str = "",
        max_tokens: int | None = None,
        retries: int = 4,
    ) -> str:
        if self.cfg.stop_file.exists():
            raise Paused("STOP file present")
        model = self.resolve(role)
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages or [])
        if prompt is not None:
            msgs.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {"model": model, "messages": msgs}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            start = time.monotonic()
            try:
                resp = self._client.chat.completions.create(**kwargs)
                self._log_usage(model, role, stage, resp, time.monotonic() - start)
                return resp.choices[0].message.content or ""
            except (RateLimitError, APIConnectionError) as e:
                last_err = e
            except APIStatusError as e:
                if e.status_code < 500:
                    raise
                last_err = e
            if attempt < retries:
                time.sleep(min(60.0, 2.0 ** attempt + random.random()))
        raise LLMUnavailable(
            f"LLM call failed after {retries + 1} attempts: {last_err}"
        ) from last_err

    def chat_json(self, role: str, prompt: str, **kw) -> Any:
        text = self.chat(role, prompt, **kw)
        return extract_json(text)

    def _log_usage(self, model: str, role: str, stage: str, resp, duration: float) -> None:
        u = getattr(resp, "usage", None)
        rec = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "model": model,
            "role": role,
            "stage": stage,
            "project": self.project,
            "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
            "total_tokens": getattr(u, "total_tokens", 0) or 0,
            "duration_ms": int(duration * 1000),
        }
        self.cfg.usage_log.parent.mkdir(parents=True, exist_ok=True)
        with self.cfg.usage_log.open("a") as f:
            f.write(json.dumps(rec) + "\n")


def extract_json(text: str) -> Any:
    """Parse JSON out of a model reply that may include prose or code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                return obj
            except ValueError:
                continue
    raise ValueError(f"no JSON found in model reply: {text[:200]!r}")
