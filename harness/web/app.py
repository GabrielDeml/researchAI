"""FastAPI monitoring dashboard.

Read-only over the same on-disk state the supervisor writes (``projects/*/state.json``,
``logs/usage.jsonl``, ``queue/``, ``journal/``, ``digests/``, ``logs/``) plus a small
set of write paths limited to the pause/resume/skip/enqueue controls described in
PLAN.md. The dashboard holds no state of its own and can restart freely.

Exposed for `python -m harness serve` (or any ASGI runner):
    harness.web.app:app    -- module-level FastAPI instance (built from the config
                               resolved at import time, honoring RESEARCHAI_ROOT)
    harness.web.app:main   -- zero-arg entrypoint that re-loads config and runs
                               uvicorn on cfg.dashboard.host/port
    harness.web.app:create_app(cfg=None) -- factory, for tests / custom wiring
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
import markdown as md_lib
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import Config, load_config
from ..state import STAGE_ORDER, ProjectState, now_iso, slugify

STATIC_DIR = Path(__file__).resolve().parent / "static"
_MD_EXTENSIONS = ["fenced_code", "tables", "toc", "sane_lists", "nl2br"]

# --- module-level config handle -------------------------------------------
# Set once by create_app(); readable by request handlers via get_cfg(). A
# single-process dashboard has exactly one active config at a time.
_cfg: Config | None = None


def get_cfg() -> Config:
    if _cfg is None:
        raise RuntimeError("dashboard app not initialized (create_app() was not called)")
    return _cfg


# --- rendering helpers ------------------------------------------------------

def render_markdown(text: str) -> str:
    return md_lib.markdown(text, extensions=_MD_EXTENSIONS)


def render_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return render_markdown(text)


def tail_lines(path: Path, n: int, max_bytes: int = 2_000_000) -> list[str]:
    if not path.is_file():
        return []
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        data = f.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[-n:]


# --- health -------------------------------------------------------------

def heartbeat_status(cfg: Config) -> tuple[bool, float | None]:
    hb = cfg.heartbeat_file
    if not hb.exists():
        return False, None
    age = time.time() - hb.stat().st_mtime
    return age < 3 * cfg.supervisor.heartbeat_seconds, age


async def proxy_status(cfg: Config) -> bool:
    url = cfg.proxy.base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {cfg.proxy.api_key}"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, headers=headers)
        return resp.status_code == 200
    except Exception:
        return False


# --- project helpers ------------------------------------------------------

def project_summary(s: ProjectState) -> dict[str, Any]:
    return {
        "slug": s.slug,
        "topic": s.topic,
        "stage": s.stage.value,
        "status": s.status,
        "verdict": s.verdict.value,
        "reviewer_score": s.reviewer_score,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "iteration_count": len(s.iterations),
        "completed_stages": [st.value for st in s.completed_stages],
        "error": s.error,
    }


_ITER_RE = re.compile(r"codex_iter(\d+)\.log$")


def list_codex_logs(pdir: Path) -> list[str]:
    logs_dir = pdir / "logs"
    if not logs_dir.is_dir():
        return []
    items: list[tuple[int, str]] = []
    for f in logs_dir.glob("codex_iter*.log"):
        m = _ITER_RE.search(f.name)
        items.append((int(m.group(1)) if m else 0, f.name))
    items.sort()
    return [f"logs/{name}" for _, name in items]


def list_figures(pdir: Path) -> list[str]:
    fig_dir = pdir / "workspace" / "figures"
    if not fig_dir.is_dir():
        return []
    return [f"workspace/figures/{f.name}" for f in sorted(fig_dir.glob("*.png"))]


def project_detail(cfg: Config, s: ProjectState) -> dict[str, Any]:
    pdir = s.dir(cfg.root)
    return {
        "state": s.model_dump(mode="json"),
        "html": {
            "topic": render_file(pdir / "topic.md"),
            "survey": render_file(pdir / "survey.md"),
            "design": render_file(pdir / "design.md"),
            "report": render_file(pdir / "report.md"),
            "review": render_file(pdir / "review.md"),
        },
        "figures": list_figures(pdir),
        "codex_logs": list_codex_logs(pdir),
    }


class QueueItem(BaseModel):
    text: str


def find_active_project(cfg: Config) -> ProjectState | None:
    running = [s for s in ProjectState.load_all(cfg.root) if s.status == "running"]
    if not running:
        return None
    running.sort(key=lambda s: s.updated_at, reverse=True)
    return running[0]


# --- app factory ------------------------------------------------------------

def create_app(cfg: Config | None = None) -> FastAPI:
    global _cfg
    _cfg = cfg or load_config()

    app = FastAPI(title="researchAI dashboard")

    def require_auth(request: Request) -> None:
        c = get_cfg()
        token = c.dashboard.auth_token
        if not token:
            return
        auth = request.headers.get("authorization", "")
        supplied = auth[7:] if auth.lower().startswith("bearer ") else None
        if not supplied:
            # EventSource cannot set headers, so SSE (and anything else) may
            # also authenticate via ?token=... when a token is configured.
            supplied = request.query_params.get("token")
        if supplied != token:
            raise HTTPException(status_code=401, detail="unauthorized")

    api = APIRouter(dependencies=[Depends(require_auth)])

    # --- overview ---
    @api.get("/overview")
    async def get_overview() -> dict:
        cfg = get_cfg()
        alive, age = heartbeat_status(cfg)
        proxy_ok = await proxy_status(cfg)
        states = ProjectState.load_all(cfg.root)
        active = [project_summary(s) for s in states if s.status in ("running", "paused")]
        totals: dict[str, int] = {}
        for s in states:
            totals[s.verdict.value] = totals.get(s.verdict.value, 0) + 1
        queue_len = len(list(cfg.queue_dir.glob("*.md"))) if cfg.queue_dir.is_dir() else 0
        return {
            "supervisor_alive": alive,
            "heartbeat_age_s": age,
            "proxy_ok": proxy_ok,
            "paused": cfg.stop_file.exists(),
            "skip_requested": cfg.skip_file.exists(),
            "active": active,
            "totals_by_verdict": totals,
            "queue_len": queue_len,
            "stages": [st.value for st in STAGE_ORDER],
            "server_time": now_iso(),
        }

    # --- projects ---
    @api.get("/projects")
    def get_projects() -> list[dict]:
        cfg = get_cfg()
        return [project_summary(s) for s in ProjectState.load_all(cfg.root)]

    @api.get("/projects/{slug}")
    def get_project(slug: str) -> dict:
        cfg = get_cfg()
        try:
            s = ProjectState.load(cfg.root, slug)
        except FileNotFoundError:
            raise HTTPException(404, "project not found")
        except Exception:
            raise HTTPException(500, "corrupt project state")
        return project_detail(cfg, s)

    @api.get("/projects/{slug}/files/{path:path}")
    def get_project_file(slug: str, path: str):
        cfg = get_cfg()
        if "/" in slug or slug in ("..", "."):
            raise HTTPException(400, "invalid slug")
        pdir = (cfg.projects_dir / slug).resolve()
        if not pdir.is_dir():
            raise HTTPException(404, "project not found")
        rel = PurePosixPath(path)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise HTTPException(403, "invalid path")
        target = (pdir / Path(*rel.parts)).resolve()
        try:
            target.relative_to(pdir)
        except ValueError:
            raise HTTPException(403, "invalid path")
        if not target.is_file():
            raise HTTPException(404, "file not found")
        return FileResponse(str(target))

    # --- usage ---
    @api.get("/usage")
    def get_usage(hours: int = 24) -> dict:
        cfg = get_cfg()
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
        totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        per_model: dict[str, dict] = {}
        per_hour: dict[str, dict] = {}
        path = cfg.usage_log
        if path.is_file():
            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue  # tolerate malformed lines
                    try:
                        ts = dt.datetime.fromisoformat(str(rec.get("ts")))
                    except (TypeError, ValueError):
                        continue
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=dt.timezone.utc)
                    if ts < cutoff:
                        continue
                    pt = int(rec.get("prompt_tokens") or 0)
                    ct = int(rec.get("completion_tokens") or 0)
                    tt = int(rec.get("total_tokens") or (pt + ct))
                    model = str(rec.get("model") or "unknown")
                    hour_key = ts.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:00")

                    totals["calls"] += 1
                    totals["prompt_tokens"] += pt
                    totals["completion_tokens"] += ct
                    totals["total_tokens"] += tt

                    m = per_model.setdefault(
                        model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    )
                    m["calls"] += 1
                    m["prompt_tokens"] += pt
                    m["completion_tokens"] += ct
                    m["total_tokens"] += tt

                    h = per_hour.setdefault(hour_key, {"calls": 0, "total_tokens": 0})
                    h["calls"] += 1
                    h["total_tokens"] += tt
        return {
            "hours": hours,
            "totals": totals,
            "per_model": per_model,
            "per_hour": [{"hour": k, **v} for k, v in sorted(per_hour.items())],
        }

    # --- queue ---
    @api.get("/queue")
    def get_queue() -> list[dict]:
        cfg = get_cfg()
        if not cfg.queue_dir.is_dir():
            return []
        out = []
        for f in sorted(cfg.queue_dir.glob("*.md")):
            title = ""
            try:
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip().lstrip("#").strip()
                    if line:
                        title = line
                        break
            except OSError:
                pass
            out.append({"file": f.name, "title": title, "mtime": f.stat().st_mtime})
        return out

    @api.post("/queue")
    def post_queue(item: QueueItem) -> dict:
        cfg = get_cfg()
        text = item.text.strip()
        if not text:
            raise HTTPException(400, "text is required")
        cfg.queue_dir.mkdir(parents=True, exist_ok=True)
        first_line = text.splitlines()[0].lstrip("#").strip()
        slug = slugify(first_line, max_len=40) if first_line else "topic"
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        fname = f"{ts}-{slug}.md"
        body = text if text.endswith("\n") else text + "\n"
        (cfg.queue_dir / fname).write_text(body, encoding="utf-8")
        return {"file": fname}

    # --- controls (only write paths besides queue enqueue) ---
    @api.post("/control/pause")
    def control_pause() -> dict:
        cfg = get_cfg()
        cfg.stop_file.parent.mkdir(parents=True, exist_ok=True)
        cfg.stop_file.touch(exist_ok=True)
        return {"paused": True}

    @api.post("/control/resume")
    def control_resume() -> dict:
        cfg = get_cfg()
        if cfg.stop_file.exists():
            cfg.stop_file.unlink()
        return {"paused": False}

    @api.post("/control/skip")
    def control_skip() -> dict:
        cfg = get_cfg()
        cfg.skip_file.parent.mkdir(parents=True, exist_ok=True)
        cfg.skip_file.touch(exist_ok=True)
        return {"skip_requested": True}

    # --- logs ---
    @api.get("/logs/tail")
    def get_logs_tail(name: str = "supervisor", slug: str = "", n: int = 200) -> dict:
        cfg = get_cfg()
        n = max(1, min(n, 2000))
        if name == "supervisor":
            return {
                "name": "supervisor",
                "slug": "",
                "path": "logs/supervisor.log",
                "lines": tail_lines(cfg.supervisor_log, n),
            }
        if name == "codex":
            s: ProjectState | None = None
            if slug:
                try:
                    s = ProjectState.load(cfg.root, slug)
                except Exception:
                    s = None
            else:
                s = find_active_project(cfg)
            if s is None:
                return {"name": "codex", "slug": slug, "path": "", "lines": []}
            logs = list_codex_logs(s.dir(cfg.root))
            if not logs:
                return {"name": "codex", "slug": s.slug, "path": "", "lines": []}
            latest_rel = logs[-1]
            return {
                "name": "codex",
                "slug": s.slug,
                "path": f"projects/{s.slug}/{latest_rel}",
                "lines": tail_lines(s.dir(cfg.root) / latest_rel, n),
            }
        raise HTTPException(400, "name must be 'supervisor' or 'codex'")

    # --- journal / digests ---
    @api.get("/journal")
    def get_journal() -> dict:
        cfg = get_cfg()
        jpath = cfg.journal_dir / "journal.md"
        ideas_path = cfg.journal_dir / "ideas.jsonl"
        ideas_count = 0
        if ideas_path.is_file():
            with ideas_path.open(encoding="utf-8", errors="replace") as f:
                ideas_count = sum(1 for line in f if line.strip())
        return {
            "html": render_file(jpath),
            "ideas_count": ideas_count,
            "updated_at": jpath.stat().st_mtime if jpath.is_file() else None,
        }

    @api.get("/digests")
    def get_digests() -> dict:
        cfg = get_cfg()
        if not cfg.digests_dir.is_dir():
            return {"digests": [], "latest": None}
        files = sorted(cfg.digests_dir.glob("*.md"))
        items = [{"file": f.name, "mtime": f.stat().st_mtime} for f in files]
        latest = None
        if files:
            latest_file = files[-1]
            latest = {"file": latest_file.name, "html": render_file(latest_file)}
        return {"digests": items, "latest": latest}

    # --- SSE ---
    @api.get("/events")
    async def sse_events(request: Request) -> StreamingResponse:
        cfg = get_cfg()

        async def gen():
            last_hb_mtime: float | None = None
            last_project_mtimes: dict[str, float] = {}
            last_sup_size = cfg.supervisor_log.stat().st_size if cfg.supervisor_log.is_file() else 0
            last_queue_sig: tuple = ()
            last_keepalive = time.monotonic()

            yield "retry: 3000\n\n"

            while True:
                if await request.is_disconnected():
                    break

                hb = cfg.heartbeat_file
                hb_mtime = hb.stat().st_mtime if hb.exists() else None
                if hb_mtime != last_hb_mtime:
                    last_hb_mtime = hb_mtime
                    alive, age = heartbeat_status(cfg)
                    payload = {"supervisor_alive": alive, "heartbeat_age_s": age, "paused": cfg.stop_file.exists()}
                    yield f"event: health\ndata: {json.dumps(payload)}\n\n"

                try:
                    pdir = cfg.projects_dir
                    current_slugs: set[str] = set()
                    if pdir.is_dir():
                        for f in pdir.glob("*/state.json"):
                            slug = f.parent.name
                            current_slugs.add(slug)
                            mtime = f.stat().st_mtime
                            if last_project_mtimes.get(slug) != mtime:
                                last_project_mtimes[slug] = mtime
                                try:
                                    s = ProjectState.load(cfg.root, slug)
                                    yield f"event: state\ndata: {json.dumps(project_summary(s))}\n\n"
                                except Exception:
                                    pass
                    for slug in list(last_project_mtimes):
                        if slug not in current_slugs:
                            del last_project_mtimes[slug]
                except Exception:
                    pass

                try:
                    sp = cfg.supervisor_log
                    if sp.is_file():
                        size = sp.stat().st_size
                        if size < last_sup_size:
                            last_sup_size = 0  # rotated/truncated
                        if size > last_sup_size:
                            with sp.open("rb") as f:
                                f.seek(last_sup_size)
                                data = f.read()
                            last_sup_size = size
                            new_lines = data.decode("utf-8", errors="replace").splitlines()
                            if new_lines:
                                yield f"event: log\ndata: {json.dumps({'source': 'supervisor', 'lines': new_lines})}\n\n"
                except Exception:
                    pass

                try:
                    qdir = cfg.queue_dir
                    sig = (
                        tuple(sorted((f.name, f.stat().st_mtime) for f in qdir.glob("*.md")))
                        if qdir.is_dir()
                        else ()
                    )
                    if sig != last_queue_sig:
                        last_queue_sig = sig
                        yield f"event: queue\ndata: {json.dumps({'queue_len': len(sig)})}\n\n"
                except Exception:
                    pass

                if time.monotonic() - last_keepalive > 15:
                    last_keepalive = time.monotonic()
                    yield ": keepalive\n\n"

                await asyncio.sleep(1.0)

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)

    app.include_router(api, prefix="/api")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app


def main() -> None:
    """Entrypoint for `python -m harness serve`."""
    cfg = load_config()
    uvicorn.run(create_app(cfg), host=cfg.dashboard.host, port=cfg.dashboard.port, log_level="info")


# Module-level ASGI app, built from config resolved at import time (honors
# RESEARCHAI_ROOT). Lets `uvicorn harness.web.app:app` work directly.
app = create_app()


if __name__ == "__main__":
    main()
