#!/usr/bin/env python3
"""Deterministic modular-addition grokking intervention experiment.

The implementation follows the supplied preregistered protocol: ordered
baseline search, a threshold fitted only from successful ordinary runs,
checkpoint and float64 invariance audits, and paired no-decay/intervention
forks.  Training is CPU-only float32; norm and intervention audits are float64.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import platform
import random
import shutil
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

# These must be in place before NumPy/PyTorch load their BLAS runtimes.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ.setdefault("PYTHONHASHSEED", "0")
ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


EVAL_EVERY = 20
MEM_WINDOW = 5
GROK_WINDOW = 10
FORK_MAX_STEPS = 5_000
SEEDS = (11, 22, 33, 44)


@dataclass(frozen=True)
class Config:
    name: str
    p: int
    f: float
    h: int
    learning_rate: float
    weight_decay: float
    max_steps: int

    def label(self) -> str:
        return (
            f"{self.name}(p={self.p},f={self.f:.2f},h={self.h},"
            f"lr={self.learning_rate},wd={self.weight_decay},max={self.max_steps})"
        )


CONFIGS = (
    Config("A", 17, 0.40, 128, 0.01, 1.0, 40_000),
    Config("B", 23, 0.50, 128, 0.01, 1.0, 40_000),
    Config("C", 23, 0.40, 256, 0.005, 1.0, 50_000),
)


@dataclass
class Dataset:
    all_x: torch.Tensor
    all_y: torch.Tensor
    train_x: torch.Tensor
    train_y: torch.Tensor
    test_x: torch.Tensor
    test_y: torch.Tensor


@dataclass
class EvalRecord:
    step: int
    train_accuracy: float
    train_cross_entropy: float
    test_accuracy: float
    centered_logit_rms: float
    total_parameter_norm: float


@dataclass
class OrdinaryRun:
    seed: int
    config: Config
    history: list[EvalRecord]
    memorization_step: int | None
    grokking_step: int | None
    valid: bool
    failure: str
    checkpoint_dir: Path


@dataclass
class InterventionAudit:
    alpha0: float
    v: torch.Tensor
    checkpoint_squared_norm: float
    intervention_squared_norm: float
    intervention_norm: float
    norm_doubling_relative_error: float
    softmax_invariance_error: float
    centered_logit_invariance_error: float
    cross_entropy_invariance_error: float
    accuracy_invariance_error: float
    centered_logit_rms_invariance_error: float
    orthogonality_error: float


@dataclass
class ForkEval:
    step: int
    test_accuracy: float
    train_accuracy: float
    train_cross_entropy: float
    centered_logit_rms: float
    effective_total_norm: float
    alpha: float
    base_parameter_discrepancy: float = 0.0
    base_centered_logit_discrepancy: float = 0.0


@dataclass
class ForkRun:
    history: list[ForkEval]
    grokking_step: int | None
    threshold_crossing_step: int | None
    max_parameter_discrepancy: float
    max_centered_logit_discrepancy: float
    decay_steps: int | None
    retried_decay: bool
    param_snapshots: list[np.ndarray]
    centered_snapshots: list[np.ndarray]
    final_model_state: dict[str, torch.Tensor]
    final_optimizer_state: dict[str, Any]


class MLP(nn.Module):
    def __init__(self, p: int, h: int) -> None:
        super().__init__()
        self.fc1 = nn.Linear(2 * p, h, bias=False)
        self.fc2 = nn.Linear(h, h, bias=False)
        self.output = nn.Linear(h, p, bias=False)

    def hidden(self, x: torch.Tensor) -> torch.Tensor:
        return F.relu(self.fc2(F.relu(self.fc1(x))))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.output(self.hidden(x))


def configure_determinism() -> None:
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    torch.use_deterministic_algorithms(True)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def make_dataset(config: Config, seed: int) -> Dataset:
    p = config.p
    pairs = np.array([(a, b) for a in range(p) for b in range(p)], dtype=np.int64)
    labels = (pairs[:, 0] + pairs[:, 1]) % p
    x = np.concatenate(
        [np.eye(p, dtype=np.float32)[pairs[:, 0]], np.eye(p, dtype=np.float32)[pairs[:, 1]]],
        axis=1,
    )
    permutation = np.random.Generator(np.random.PCG64(seed)).permutation(p * p)
    n_train = math.floor(config.f * p * p)
    train_idx, test_idx = permutation[:n_train], permutation[n_train:]
    all_x = torch.from_numpy(x)
    all_y = torch.from_numpy(labels).long()
    return Dataset(
        all_x=all_x,
        all_y=all_y,
        train_x=all_x[train_idx],
        train_y=all_y[train_idx],
        test_x=all_x[test_idx],
        test_y=all_y[test_idx],
    )


def build_optimizer(model: nn.Module, config: Config) -> torch.optim.AdamW:
    # A single group guarantees that every tensor receives the listed decay.
    return torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        betas=(0.9, 0.98),
        eps=1e-8,
        weight_decay=config.weight_decay,
    )


def centered(logits: torch.Tensor) -> torch.Tensor:
    return logits - logits.mean(dim=-1, keepdim=True)


def squared_parameter_norm(model: nn.Module) -> float:
    with torch.no_grad():
        total = torch.zeros((), dtype=torch.float64)
        for parameter in model.parameters():
            total += parameter.detach().double().square().sum()
        return float(total.item())


def total_parameter_norm(model: nn.Module) -> float:
    return math.sqrt(squared_parameter_norm(model))


@torch.no_grad()
def evaluate(model: MLP, data: Dataset, step: int) -> EvalRecord:
    model.eval()
    train_logits = centered(model(data.train_x))
    test_logits = centered(model(data.test_x))
    all_logits = centered(model(data.all_x))
    return EvalRecord(
        step=step,
        train_accuracy=float((train_logits.argmax(1) == data.train_y).double().mean().item()),
        train_cross_entropy=float(F.cross_entropy(train_logits, data.train_y).item()),
        test_accuracy=float((test_logits.argmax(1) == data.test_y).double().mean().item()),
        centered_logit_rms=float(all_logits.square().mean().sqrt().item()),
        total_parameter_norm=total_parameter_norm(model),
    )


def optimizer_step(model: MLP, optimizer: torch.optim.AdamW, data: Dataset) -> None:
    model.train()
    optimizer.zero_grad(set_to_none=True)
    loss = F.cross_entropy(centered(model(data.train_x)), data.train_y)
    loss.backward()
    optimizer.step()


def first_window_step(
    history: list[Any], window: int, predicate: Any
) -> int | None:
    for start in range(len(history) - window + 1):
        candidate = history[start : start + window]
        if all(predicate(record) for record in candidate):
            return int(candidate[0].step)
    return None


def memorization_step(history: list[EvalRecord]) -> int | None:
    return first_window_step(
        history,
        MEM_WINDOW,
        lambda record: record.train_accuracy == 1.0 and record.train_cross_entropy <= 0.001,
    )


def sustained_grokking_step(history: list[Any]) -> int | None:
    return first_window_step(
        history, GROK_WINDOW, lambda record: record.test_accuracy >= 0.95
    )


def clone_state(model: MLP, optimizer: torch.optim.AdamW, record: EvalRecord) -> dict[str, Any]:
    return {
        "model_state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
        "optimizer_state": copy.deepcopy(optimizer.state_dict()),
        "metrics": asdict(record),
    }


def save_checkpoint(path: Path, state: dict[str, Any], config: Config, seed: int) -> None:
    payload = dict(state)
    payload["config"] = asdict(config)
    payload["seed"] = seed
    torch.save(payload, path)


def write_dataclass_csv(path: Path, rows: Iterable[Any], extra: dict[str, Any] | None = None) -> None:
    rows = list(rows)
    if not rows:
        return
    extra = extra or {}
    fields = [*extra.keys(), *asdict(rows[0]).keys()]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**extra, **asdict(row)})


def run_ordinary(config: Config, seed: int, config_dir: Path) -> OrdinaryRun:
    seed_everything(seed)
    data = make_dataset(config, seed)
    model = MLP(config.p, config.h)
    optimizer = build_optimizer(model, config)
    checkpoint_dir = config_dir / f"seed_{seed}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    history: list[EvalRecord] = []
    pending: deque[tuple[int, dict[str, Any]]] = deque(maxlen=MEM_WINDOW)
    m: int | None = None
    g: int | None = None

    for step in range(config.max_steps + 1):
        if step % EVAL_EVERY == 0:
            record = evaluate(model, data, step)
            history.append(record)
            state = clone_state(model, optimizer, record)
            if m is None:
                pending.append((step, state))
                detected_m = memorization_step(history)
                if detected_m is not None:
                    m = detected_m
                    for saved_step, saved_state in pending:
                        if saved_step >= m:
                            save_checkpoint(
                                checkpoint_dir / f"step_{saved_step:06d}.pt",
                                saved_state,
                                config,
                                seed,
                            )
            else:
                save_checkpoint(checkpoint_dir / f"step_{step:06d}.pt", state, config, seed)

            g = sustained_grokking_step(history)
            if m is not None and g is not None and step >= g + (GROK_WINDOW - 1) * EVAL_EVERY:
                break
        if step < config.max_steps:
            optimizer_step(model, optimizer, data)

    delayed = m is not None and g is not None and g - m >= 200
    low_between = (
        m is not None
        and g is not None
        and any(m <= record.step < g and record.test_accuracy < 0.90 for record in history)
    )
    valid = bool(delayed and low_between)
    reasons: list[str] = []
    if m is None:
        reasons.append("no memorization window")
    if g is None:
        reasons.append("no sustained grokking window")
    if m is not None and g is not None and g - m < 200:
        reasons.append("grokking delay below 200 steps")
    if m is not None and g is not None and not low_between:
        reasons.append("no sub-0.90 test evaluation between M and G")
    write_dataclass_csv(
        config_dir / f"ordinary_history_seed_{seed}.csv",
        history,
        {"configuration": config.label(), "seed": seed},
    )
    return OrdinaryRun(seed, config, history, m, g, valid, "; ".join(reasons), checkpoint_dir)


def load_checkpoint(config: Config, seed: int, path: Path) -> tuple[MLP, torch.optim.AdamW, dict[str, Any]]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = MLP(config.p, config.h)
    optimizer = build_optimizer(model, config)
    model.load_state_dict(payload["model_state"])
    optimizer.load_state_dict(payload["optimizer_state"])
    return model, optimizer, payload


def audit_reload(config: Config, seed: int, path: Path, recorded: EvalRecord) -> dict[str, float]:
    model, _, _ = load_checkpoint(config, seed, path)
    reloaded = evaluate(model, make_dataset(config, seed), recorded.step)
    return {
        "train_accuracy": abs(reloaded.train_accuracy - recorded.train_accuracy),
        "train_cross_entropy": abs(reloaded.train_cross_entropy - recorded.train_cross_entropy),
        "test_accuracy": abs(reloaded.test_accuracy - recorded.test_accuracy),
        "centered_logit_rms": abs(reloaded.centered_logit_rms - recorded.centered_logit_rms),
        "total_parameter_norm": abs(reloaded.total_parameter_norm - recorded.total_parameter_norm),
    }


@torch.no_grad()
def construct_and_audit_intervention(model: MLP, data: Dataset) -> InterventionAudit:
    model64 = copy.deepcopy(model).double()
    x64 = data.all_x.double()
    y = data.all_y
    w = model64.output.weight.detach()
    p, h = w.shape
    u = torch.ones(p, dtype=torch.float64)
    s = w.T @ u
    ss = torch.dot(s, s)
    if float(ss.item()) < 1e-20:
        v = torch.zeros(h, dtype=torch.float64)
        v[0] = 1.0
    else:
        residuals = torch.eye(h, dtype=torch.float64) - torch.outer(s, s / ss)
        norms = torch.linalg.vector_norm(residuals, dim=1)
        j = int(torch.argmax(norms).item())
        v = residuals[j] / norms[j]

    checkpoint_squared = squared_parameter_norm(model64)
    alpha0 = math.sqrt(checkpoint_squared / p)
    hidden = model64.hidden(x64)
    z = model64.output(hidden)
    common = alpha0 * (hidden @ v)
    zp = z + common[:, None] * u[None, :]
    effective_w = w + alpha0 * torch.outer(u, v)
    other_squared = checkpoint_squared - float(w.square().sum().item())
    intervention_squared = other_squared + float(effective_w.square().sum().item())
    zc, zpc = centered(z), centered(zp)
    ce = F.cross_entropy(z, y, reduction="none")
    cep = F.cross_entropy(zp, y, reduction="none")
    pred_diff = (z.argmax(1) == y).double() - (zp.argmax(1) == y).double()
    return InterventionAudit(
        alpha0=alpha0,
        v=v,
        checkpoint_squared_norm=checkpoint_squared,
        intervention_squared_norm=intervention_squared,
        intervention_norm=math.sqrt(intervention_squared),
        norm_doubling_relative_error=abs(intervention_squared - 2 * checkpoint_squared)
        / (2 * checkpoint_squared),
        softmax_invariance_error=float((torch.softmax(z, 1) - torch.softmax(zp, 1)).abs().max().item()),
        centered_logit_invariance_error=float((zc - zpc).abs().max().item()),
        cross_entropy_invariance_error=float((ce - cep).abs().max().item()),
        accuracy_invariance_error=float(pred_diff.abs().max().item()),
        centered_logit_rms_invariance_error=abs(
            float(zc.square().mean().sqrt().item()) - float(zpc.square().mean().sqrt().item())
        ),
        orthogonality_error=abs(float(torch.dot(s, v).item())),
    )


def flatten_parameters(model: MLP) -> np.ndarray:
    with torch.no_grad():
        return torch.cat([parameter.detach().reshape(-1).cpu() for parameter in model.parameters()]).numpy().copy()


@torch.no_grad()
def all_centered_logits(model: MLP, data: Dataset) -> np.ndarray:
    return centered(model(data.all_x)).cpu().numpy().copy()


@torch.no_grad()
def fork_eval(
    model: MLP,
    data: Dataset,
    step: int,
    effective_norm: float,
    alpha: float,
    intervention_v: torch.Tensor | None = None,
) -> ForkEval:
    model.eval()
    base_train = model(data.train_x)
    base_test = model(data.test_x)
    if intervention_v is None:
        train_logits = centered(base_train)
        test_logits = centered(base_test)
    else:
        v32 = intervention_v.to(dtype=torch.float32)
        train_common = alpha * (model.hidden(data.train_x) @ v32)
        test_common = alpha * (model.hidden(data.test_x) @ v32)
        train_logits = base_train + train_common[:, None]
        test_logits = base_test + test_common[:, None]
    all_base_centered = centered(model(data.all_x))
    return ForkEval(
        step=step,
        test_accuracy=float((test_logits.argmax(1) == data.test_y).double().mean().item()),
        train_accuracy=float((train_logits.argmax(1) == data.train_y).double().mean().item()),
        train_cross_entropy=float(F.cross_entropy(centered(base_train), data.train_y).item()),
        centered_logit_rms=float(all_base_centered.square().mean().sqrt().item()),
        effective_total_norm=effective_norm,
        alpha=alpha,
    )


def zero_optimizer_decay(optimizer: torch.optim.AdamW) -> None:
    for group in optimizer.param_groups:
        group["weight_decay"] = 0.0


def run_no_decay_fork(config: Config, seed: int, checkpoint_path: Path) -> ForkRun:
    model, optimizer, _ = load_checkpoint(config, seed, checkpoint_path)
    zero_optimizer_decay(optimizer)
    data = make_dataset(config, seed)
    history: list[ForkEval] = []
    params: list[np.ndarray] = []
    logits: list[np.ndarray] = []
    g: int | None = None
    for step in range(FORK_MAX_STEPS + 1):
        if step % EVAL_EVERY == 0:
            history.append(fork_eval(model, data, step, total_parameter_norm(model), 0.0))
            params.append(flatten_parameters(model))
            logits.append(all_centered_logits(model, data))
            g = sustained_grokking_step(history)
            if g is not None:
                break
        if step < FORK_MAX_STEPS:
            optimizer_step(model, optimizer, data)
    return ForkRun(
        history=history,
        grokking_step=g,
        threshold_crossing_step=None,
        max_parameter_discrepancy=0.0,
        max_centered_logit_discrepancy=0.0,
        decay_steps=None,
        retried_decay=False,
        param_snapshots=params,
        centered_snapshots=logits,
        final_model_state={k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
        final_optimizer_state=copy.deepcopy(optimizer.state_dict()),
    )


def effective_squared_norm(model: MLP, alpha: float, v: torch.Tensor) -> float:
    with torch.no_grad():
        base_squared = squared_parameter_norm(model)
        w = model.output.weight.detach().double()
        u = torch.ones(w.shape[0], dtype=torch.float64)
        cross = float(torch.dot(w.T @ u, v).item())
        added_squared = alpha * alpha * w.shape[0] * float(torch.dot(v, v).item())
        return base_squared + 2.0 * alpha * cross + added_squared


def run_intervention_once(
    config: Config,
    seed: int,
    checkpoint_path: Path,
    audit: InterventionAudit,
    threshold: float,
    decay_steps: int,
    baseline: ForkRun,
    retried: bool,
) -> ForkRun:
    model, optimizer, _ = load_checkpoint(config, seed, checkpoint_path)
    zero_optimizer_decay(optimizer)
    data = make_dataset(config, seed)
    history: list[ForkEval] = []
    params: list[np.ndarray] = []
    logits: list[np.ndarray] = []
    crossing: int | None = None
    previous_norm = math.sqrt(effective_squared_norm(model, audit.alpha0, audit.v))
    g: int | None = None
    max_param_diff = 0.0
    max_logit_diff = 0.0

    for step in range(FORK_MAX_STEPS + 1):
        alpha = audit.alpha0 * max(1.0 - step / decay_steps, 0.0)
        current_norm = math.sqrt(effective_squared_norm(model, alpha, audit.v))
        if step > 0 and crossing is None and previous_norm > threshold and current_norm <= threshold:
            crossing = step
        previous_norm = current_norm

        if step % EVAL_EVERY == 0:
            record = fork_eval(model, data, step, current_norm, alpha, audit.v)
            parameter_snapshot = flatten_parameters(model)
            centered_snapshot = all_centered_logits(model, data)
            index = len(history)
            if index < len(baseline.history) and baseline.history[index].step == step:
                parameter_diff = float(np.max(np.abs(parameter_snapshot - baseline.param_snapshots[index])))
                logit_diff = float(np.max(np.abs(centered_snapshot - baseline.centered_snapshots[index])))
                record.base_parameter_discrepancy = parameter_diff
                record.base_centered_logit_discrepancy = logit_diff
                max_param_diff = max(max_param_diff, parameter_diff)
                max_logit_diff = max(max_logit_diff, logit_diff)
            history.append(record)
            params.append(parameter_snapshot)
            logits.append(centered_snapshot)
            g = sustained_grokking_step(history)
            if g is not None:
                break

        if step < FORK_MAX_STEPS:
            # The common component is kept outside W and is absent from this loss.
            optimizer_step(model, optimizer, data)

    return ForkRun(
        history=history,
        grokking_step=g,
        threshold_crossing_step=crossing,
        max_parameter_discrepancy=max_param_diff,
        max_centered_logit_discrepancy=max_logit_diff,
        decay_steps=decay_steps,
        retried_decay=retried,
        param_snapshots=params,
        centered_snapshots=logits,
        final_model_state={k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
        final_optimizer_state=copy.deepcopy(optimizer.state_dict()),
    )


def round_to_multiple_20(value: float) -> int:
    # Python round is the preregistered nearest-integer operation (ties-to-even).
    return max(20, 20 * round(value / 20))


def save_fork_trajectory(
    seed: int, baseline: ForkRun, intervention: ForkRun, output_dir: Path
) -> None:
    matched = min(len(baseline.param_snapshots), len(intervention.param_snapshots))
    baseline_params = np.stack(baseline.param_snapshots[:matched])
    intervention_params = np.stack(intervention.param_snapshots[:matched])
    baseline_logits = np.stack(baseline.centered_snapshots[:matched])
    intervention_logits = np.stack(intervention.centered_snapshots[:matched])
    np.savez_compressed(
        output_dir / f"paired_base_trajectory_seed_{seed}.npz",
        steps=np.array([r.step for r in baseline.history[:matched]], dtype=np.int32),
        baseline_parameters=baseline_params,
        intervention_parameter_delta=intervention_params - baseline_params,
        baseline_centered_logits=baseline_logits,
        intervention_centered_logit_delta=intervention_logits - baseline_logits,
    )
    torch.save(
        {
            "baseline_model_state": baseline.final_model_state,
            "baseline_optimizer_state": baseline.final_optimizer_state,
            "intervention_base_model_state": intervention.final_model_state,
            "intervention_base_optimizer_state": intervention.final_optimizer_state,
        },
        output_dir / f"fork_final_states_seed_{seed}.pt",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_figure(
    rows: list[dict[str, Any]],
    baseline_forks: dict[int, ForkRun],
    intervention_forks: dict[int, ForkRun],
    threshold: float | None,
    status: str,
    ordinary_runs: list[OrdinaryRun] | None = None,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), dpi=100)
    ax0, ax1 = axes
    finite = [row for row in rows if row.get("G0_i", -1) >= 0 and row.get("G1_i", -1) >= 0]
    if finite:
        values = [float(row["G0_i"]) for row in finite] + [float(row["G1_i"]) for row in finite]
        upper = max(values) * 1.12 + 20
        line = np.linspace(0, upper, 200)
        ax0.plot(line, line, color="black", label="identity")
        ax0.plot(line, 0.9 * line, "--", color="gray", label="0.9× / 1.1×")
        ax0.plot(line, 1.1 * line, "--", color="gray")
        for row in finite:
            ax0.scatter(row["G0_i"], row["G1_i"], s=65)
            ax0.annotate(str(row["seed"]), (row["G0_i"], row["G1_i"]), xytext=(5, 5), textcoords="offset points")
        ax0.set_xlim(0, upper)
        ax0.set_ylim(0, upper)
        ax0.set_xlabel("No-decay sustained grokking step $G_0$")
        ax0.set_ylabel("Intervention sustained grokking step $G_1$")
        ax0.set_title("Paired fork grokking times")
        ax0.legend()

        worst = max(finite, key=lambda row: float(row["R_i"]))
        seed = int(worst["seed"])
        b, i = baseline_forks[seed], intervention_forks[seed]
        bx = [record.step for record in b.history]
        ix = [record.step for record in i.history]
        ax1.plot(bx, [record.test_accuracy for record in b.history], color="C0", label="No-decay accuracy")
        ax1.plot(ix, [record.test_accuracy for record in i.history], color="C1", linestyle="--", label="Intervention accuracy")
        ax1.axhline(0.95, color="black", linestyle=":", label="95% accuracy")
        ax1.set_xlabel("Fork-relative optimizer step")
        ax1.set_ylabel("Test accuracy")
        ax1.set_ylim(-0.02, 1.03)
        norm_ax = ax1.twinx()
        norm_ax.plot(bx, [record.effective_total_norm for record in b.history], color="C0", alpha=0.35, label="No-decay norm")
        norm_ax.plot(ix, [record.effective_total_norm for record in i.history], color="C1", alpha=0.55, label="Intervention norm")
        if threshold is not None:
            norm_ax.axhline(threshold, color="purple", linestyle=":", label="Threshold T")
        if worst.get("X_i", -1) >= 0:
            ax1.axvline(worst["X_i"], color="purple", linestyle="--", label="$X_i$")
        ax1.axvline(worst["G0_i"], color="C0", linestyle=":", label="$G_{0i}$")
        ax1.axvline(worst["G1_i"], color="C1", linestyle=":", label="$G_{1i}$")
        ax1.set_title(f"Largest-shift seed {seed}: accuracy and norm")
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = norm_ax.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="center right", fontsize=8)
        norm_ax.set_ylabel("Effective total parameter norm")
    else:
        ax0.axis("off")
        ax0.text(0.5, 0.55, status, ha="center", va="center", fontsize=18)
        ax0.text(0.5, 0.43, "No valid paired fork result", ha="center", va="center")
        if ordinary_runs:
            for run in ordinary_runs:
                ax1.plot(
                    [record.step for record in run.history],
                    [record.test_accuracy for record in run.history],
                    label=f"{run.config.name}, seed {run.seed}",
                )
            ax1.axhline(0.95, color="black", linestyle=":")
            ax1.set_xlabel("Ordinary optimizer step")
            ax1.set_ylabel("Test accuracy")
            ax1.set_title("Baseline diagnostic")
            ax1.legend(fontsize=7)
        else:
            ax1.axis("off")
    fig.suptitle(f"Softmax-invisible norm intervention — {status}")
    fig.tight_layout()
    figures = ROOT / "figures"
    figures.mkdir(exist_ok=True)
    figure_path = figures / "key_result.png"
    fig.savefig(figure_path, dpi=100)
    plt.close(fig)
    shutil.copyfile(figure_path, ROOT / "key_result.png")


def scalar(value: Any, missing: Any = -1) -> Any:
    return missing if value is None else value


def write_outputs(
    flat_results: dict[str, Any],
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    with (ROOT / "results.json").open("w") as handle:
        json.dump(flat_results, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    with (ROOT / "summary.json").open("w") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    if rows:
        fields = list(rows[0].keys())
        with (ROOT / "results.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def invalid_outputs(
    status: str,
    reason: str,
    started: float,
    selected: Config | None,
    flags: dict[str, bool],
    rows: list[dict[str, Any]],
    ordinary_runs: list[OrdinaryRun] | None = None,
) -> None:
    elapsed = time.perf_counter() - started
    config_label = selected.label() if selected else "none"
    flat: dict[str, Any] = {
        "decision": status,
        "error": reason,
        "selected_configuration": config_label,
        "R_max": -1.0,
        "mean_R": -1.0,
        "median_R": -1.0,
        "elapsed_seconds": elapsed,
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "matplotlib_version": matplotlib.__version__,
        **flags,
    }
    summary = {
        "decision": status,
        "error": reason,
        "selected_configuration": config_label,
        "R_max": None,
        "mean_R": None,
        "median_R": None,
        "validity_flags": flags,
        "elapsed_seconds": elapsed,
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
    }
    write_outputs(flat, summary, rows)
    create_figure(rows, {}, {}, None, status, ordinary_runs)
    print(f"Ran deterministic modular-addition baseline search; {status}: {reason}")
    print(f"Selected configuration: {config_label}; elapsed: {elapsed:.1f} s")


def smoke_test() -> None:
    configure_determinism()
    config = Config("smoke", 7, 0.40, 16, 0.01, 1.0, 20)
    seed_everything(11)
    data = make_dataset(config, 11)
    model = MLP(config.p, config.h)
    optimizer = build_optimizer(model, config)
    before = evaluate(model, data, 0)
    optimizer_step(model, optimizer, data)
    after = evaluate(model, data, 1)
    assert math.isfinite(after.train_cross_entropy)
    assert before.total_parameter_norm != after.total_parameter_norm
    audit = construct_and_audit_intervention(model, data)
    assert audit.norm_doubling_relative_error <= 1e-8
    assert audit.softmax_invariance_error <= 1e-10
    print("Smoke test passed: deterministic update and float64 intervention audit.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        smoke_test()
        return

    started = time.perf_counter()
    configure_determinism()
    (ROOT / "checkpoints").mkdir(exist_ok=True)
    (ROOT / "histories").mkdir(exist_ok=True)
    (ROOT / "trajectories").mkdir(exist_ok=True)
    flags = {
        "valid_baseline": False,
        "valid_checkpoint": False,
        "valid_invariance": False,
        "valid_fork": False,
        "valid_crossing": False,
    }

    selected: Config | None = None
    selected_runs: list[OrdinaryRun] = []
    search_rows: list[dict[str, Any]] = []
    last_runs: list[OrdinaryRun] = []
    for config in CONFIGS:
        print(f"Baseline search: configuration {config.label()}", flush=True)
        config_dir = ROOT / "checkpoints" / f"config_{config.name}"
        if config_dir.exists():
            shutil.rmtree(config_dir)
        config_dir.mkdir(parents=True)
        runs: list[OrdinaryRun] = []
        for seed in SEEDS:
            run_started = time.perf_counter()
            run = run_ordinary(config, seed, config_dir)
            runs.append(run)
            search_rows.append(
                {
                    "configuration": config.label(),
                    "seed": seed,
                    "M": scalar(run.memorization_step),
                    "G": scalar(run.grokking_step),
                    "valid": run.valid,
                    "failure": run.failure,
                    "elapsed_seconds": time.perf_counter() - run_started,
                }
            )
            print(
                f"  seed {seed}: M={run.memorization_step}, G={run.grokking_step}, "
                f"valid={run.valid} ({time.perf_counter() - run_started:.1f}s)",
                flush=True,
            )
        last_runs = runs
        if all(run.valid for run in runs):
            selected, selected_runs = config, runs
            flags["valid_baseline"] = True
            break
        shutil.rmtree(config_dir)
        for path in config_dir.parent.glob(f"config_{config.name}/ordinary_history_*.csv"):
            path.unlink(missing_ok=True)

    with (ROOT / "baseline_search.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(search_rows[0].keys()))
        writer.writeheader()
        writer.writerows(search_rows)

    if selected is None:
        invalid_outputs(
            "INVALID_BASELINE",
            "No ordered configuration satisfied the four-seed delayed-grokking criteria.",
            started,
            None,
            flags,
            [],
            last_runs,
        )
        return

    # Fit T solely from the 40 preregistered sustained-grokking norms.
    threshold_norms: dict[int, list[float]] = {}
    for run in selected_runs:
        assert run.grokking_step is not None
        lookup = {record.step: record for record in run.history}
        threshold_norms[run.seed] = [
            lookup[run.grokking_step + offset].total_parameter_norm
            for offset in range(0, 200, EVAL_EVERY)
        ]
    threshold = 1.05 * max(value for values in threshold_norms.values() for value in values)
    print(f"Selected {selected.label()}; fitted threshold T={threshold:.9f}", flush=True)

    selected_checkpoints: dict[int, tuple[int, EvalRecord, Path]] = {}
    reload_audits: dict[int, dict[str, float]] = {}
    rows: list[dict[str, Any]] = []
    for run in selected_runs:
        assert run.memorization_step is not None and run.grokking_step is not None
        candidates = [
            record
            for record in run.history
            if record.step >= run.memorization_step
            and record.step < run.grokking_step
            and record.train_accuracy == 1.0
            and record.train_cross_entropy <= 0.001
            and record.test_accuracy < 0.90
            and record.total_parameter_norm < threshold
        ]
        if not candidates:
            invalid_outputs(
                "INVALID_CHECKPOINT",
                f"Seed {run.seed} has no checkpoint satisfying the preregistered constraints.",
                started,
                selected,
                flags,
                rows,
                selected_runs,
            )
            return
        record = candidates[0]
        path = run.checkpoint_dir / f"step_{record.step:06d}.pt"
        reload_error = audit_reload(selected, run.seed, path, record)
        reload_audits[run.seed] = reload_error
        reload_ok = (
            reload_error["train_cross_entropy"] < 1e-7
            and reload_error["centered_logit_rms"] < 1e-7
            and reload_error["total_parameter_norm"] < 1e-6
            and reload_error["train_accuracy"] < 1e-6
            and reload_error["test_accuracy"] < 1e-6
        )
        if not reload_ok:
            invalid_outputs(
                "INVALID_CHECKPOINT",
                f"Seed {run.seed} failed the checkpoint reload audit: {reload_error}",
                started,
                selected,
                flags,
                rows,
                selected_runs,
            )
            return
        selected_checkpoints[run.seed] = (record.step, record, path)
    flags["valid_checkpoint"] = True

    intervention_audits: dict[int, InterventionAudit] = {}
    for seed in SEEDS:
        _, _, checkpoint_path = selected_checkpoints[seed]
        model, _, _ = load_checkpoint(selected, seed, checkpoint_path)
        audit = construct_and_audit_intervention(model, make_dataset(selected, seed))
        intervention_audits[seed] = audit
        invariant = (
            audit.norm_doubling_relative_error <= 1e-8
            and audit.softmax_invariance_error <= 1e-10
            and audit.centered_logit_invariance_error <= 1e-10
            and audit.cross_entropy_invariance_error <= 1e-10
            and audit.accuracy_invariance_error == 0.0
            and audit.centered_logit_rms_invariance_error <= 1e-10
        )
        if not invariant:
            invalid_outputs(
                "INVALID_INVARIANCE",
                f"Seed {seed} failed the float64 intervention audit: {asdict(audit) | {'v': 'omitted'}}",
                started,
                selected,
                flags,
                rows,
                selected_runs,
            )
            return
    flags["valid_invariance"] = True

    baseline_forks: dict[int, ForkRun] = {}
    for seed in SEEDS:
        print(f"No-decay fork seed {seed}", flush=True)
        baseline_forks[seed] = run_no_decay_fork(selected, seed, selected_checkpoints[seed][2])
        print(f"  G0={baseline_forks[seed].grokking_step}", flush=True)
        if baseline_forks[seed].grokking_step is None:
            invalid_outputs(
                "INVALID_FORK",
                f"Seed {seed} no-decay fork did not sustain 95% test accuracy within 5000 steps.",
                started,
                selected,
                flags,
                rows,
                selected_runs,
            )
            return
    flags["valid_fork"] = True

    intervention_forks: dict[int, ForkRun] = {}
    for seed in SEEDS:
        baseline = baseline_forks[seed]
        assert baseline.grokking_step is not None
        decay_steps = round_to_multiple_20(0.5 * baseline.grokking_step)
        audit = intervention_audits[seed]
        if audit.intervention_norm <= threshold:
            invalid_outputs(
                "INVALID_CROSSING",
                f"Seed {seed} intervention norm is not above T at fork step 0.",
                started,
                selected,
                flags,
                rows,
                selected_runs,
            )
            return
        print(f"Intervention fork seed {seed}, D={decay_steps}", flush=True)
        fork = run_intervention_once(
            selected,
            seed,
            selected_checkpoints[seed][2],
            audit,
            threshold,
            decay_steps,
            baseline,
            False,
        )
        crossing_valid = fork.threshold_crossing_step is not None and fork.threshold_crossing_step <= decay_steps
        if not crossing_valid:
            retry_decay = max(20, (math.floor(decay_steps / 2) // 20) * 20)
            print(f"  no crossing; one retry with D={retry_decay}", flush=True)
            fork = run_intervention_once(
                selected,
                seed,
                selected_checkpoints[seed][2],
                audit,
                threshold,
                retry_decay,
                baseline,
                True,
            )
            crossing_valid = fork.threshold_crossing_step is not None and fork.threshold_crossing_step <= retry_decay
        if not crossing_valid:
            invalid_outputs(
                "INVALID_CROSSING",
                f"Seed {seed} did not cross T during the preregistered decay or retry.",
                started,
                selected,
                flags,
                rows,
                selected_runs,
            )
            return
        intervention_forks[seed] = fork
        print(f"  X={fork.threshold_crossing_step}, G1={fork.grokking_step}", flush=True)
    flags["valid_crossing"] = True

    # Persist fork histories, compressed parameter/logit trajectories, and final states.
    trajectory_dir = ROOT / "trajectories"
    for seed in SEEDS:
        write_dataclass_csv(
            ROOT / "histories" / f"no_decay_fork_seed_{seed}.csv",
            baseline_forks[seed].history,
            {"seed": seed, "fork": "no_decay"},
        )
        write_dataclass_csv(
            ROOT / "histories" / f"intervention_fork_seed_{seed}.csv",
            intervention_forks[seed].history,
            {"seed": seed, "fork": "intervention"},
        )
        save_fork_trajectory(seed, baseline_forks[seed], intervention_forks[seed], trajectory_dir)

    relative_shifts: list[float] = []
    run_by_seed = {run.seed: run for run in selected_runs}
    for seed in SEEDS:
        run = run_by_seed[seed]
        checkpoint_step, checkpoint_record, _ = selected_checkpoints[seed]
        audit = intervention_audits[seed]
        baseline = baseline_forks[seed]
        intervention = intervention_forks[seed]
        assert run.memorization_step is not None and run.grokking_step is not None
        assert baseline.grokking_step is not None
        if intervention.grokking_step is None:
            relative = math.inf
        else:
            relative = abs(intervention.grokking_step - baseline.grokking_step) / baseline.grokking_step
        relative_shifts.append(relative)
        rows.append(
            {
                "seed": seed,
                "configuration": selected.label(),
                "M_i": run.memorization_step,
                "ordinary_G_i": run.grokking_step,
                "C_i": checkpoint_step,
                "checkpoint_train_accuracy": checkpoint_record.train_accuracy,
                "checkpoint_train_cross_entropy": checkpoint_record.train_cross_entropy,
                "checkpoint_test_accuracy": checkpoint_record.test_accuracy,
                "checkpoint_centered_logit_rms": checkpoint_record.centered_logit_rms,
                "checkpoint_norm": checkpoint_record.total_parameter_norm,
                "T": threshold,
                "doubled_intervention_squared_norm": audit.intervention_squared_norm,
                "doubled_intervention_norm": audit.intervention_norm,
                "norm_doubling_relative_error": audit.norm_doubling_relative_error,
                "softmax_invariance_error": audit.softmax_invariance_error,
                "centered_logit_invariance_error": audit.centered_logit_invariance_error,
                "cross_entropy_invariance_error": audit.cross_entropy_invariance_error,
                "accuracy_invariance_error": audit.accuracy_invariance_error,
                "centered_logit_rms_invariance_error": audit.centered_logit_rms_invariance_error,
                "reload_loss_error": reload_audits[seed]["train_cross_entropy"],
                "reload_norm_error": reload_audits[seed]["total_parameter_norm"],
                "G0_i": baseline.grokking_step,
                "G1_i": scalar(intervention.grokking_step),
                "D_i": intervention.decay_steps,
                "decay_retried": intervention.retried_decay,
                "X_i": intervention.threshold_crossing_step,
                "R_i": "inf" if math.isinf(relative) else relative,
                "max_base_parameter_discrepancy": intervention.max_parameter_discrepancy,
                "max_base_centered_logit_discrepancy": intervention.max_centered_logit_discrepancy,
                "final_status": "pending",
            }
        )

    r_max = max(relative_shifts)
    mean_r = float(np.mean(relative_shifts))
    median_r = float(np.median(relative_shifts))
    all_interventions_grok = all(fork.grokking_step is not None for fork in intervention_forks.values())
    decision = "SUPPORTED" if all_interventions_grok and r_max < 0.10 else "REFUTED"
    for row in rows:
        row["final_status"] = decision

    elapsed = time.perf_counter() - started
    flat_results: dict[str, Any] = {
        "decision": decision,
        "hypothesis_supported": decision == "SUPPORTED",
        "selected_configuration": selected.label(),
        "R_max": r_max if math.isfinite(r_max) else "inf",
        "mean_R": mean_r if math.isfinite(mean_r) else "inf",
        "median_R": median_r if math.isfinite(median_r) else "inf",
        "threshold_T": threshold,
        "elapsed_seconds": elapsed,
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "matplotlib_version": matplotlib.__version__,
        "omp_num_threads": int(os.environ["OMP_NUM_THREADS"]),
        "mkl_num_threads": int(os.environ["MKL_NUM_THREADS"]),
        "torch_num_threads": torch.get_num_threads(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        **flags,
    }
    for seed in SEEDS:
        row = next(item for item in rows if item["seed"] == seed)
        for key in ("M_i", "ordinary_G_i", "C_i", "checkpoint_norm", "G0_i", "G1_i", "D_i", "X_i"):
            flat_results[f"seed_{seed}_{key}"] = row[key]
        flat_results[f"seed_{seed}_R_i"] = row["R_i"]
        flat_results[f"seed_{seed}_max_base_parameter_discrepancy"] = row["max_base_parameter_discrepancy"]
        flat_results[f"seed_{seed}_max_base_centered_logit_discrepancy"] = row["max_base_centered_logit_discrepancy"]
        for index, norm in enumerate(threshold_norms[seed]):
            flat_results[f"threshold_norm_seed_{seed}_window_index_{index}"] = norm

    summary = {
        "decision": decision,
        "selected_configuration": asdict(selected),
        "R_max": r_max if math.isfinite(r_max) else "inf",
        "mean_R": mean_r if math.isfinite(mean_r) else "inf",
        "median_R": median_r if math.isfinite(median_r) else "inf",
        "threshold_T": threshold,
        "threshold_underlying_norms": threshold_norms,
        "validity_flags": flags,
        "elapsed_seconds": elapsed,
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "per_seed": {str(row["seed"]): row for row in rows},
    }
    write_outputs(flat_results, summary, rows)
    create_figure(rows, baseline_forks, intervention_forks, threshold, decision)

    # Add hashes after all required artifacts exist, without making results.json nested.
    artifact_hashes = {
        "results_csv_sha256": sha256_file(ROOT / "results.csv"),
        "summary_json_sha256": sha256_file(ROOT / "summary.json"),
        "key_result_png_sha256": sha256_file(ROOT / "key_result.png"),
    }
    flat_results.update(artifact_hashes)
    with (ROOT / "results.json").open("w") as handle:
        json.dump(flat_results, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")

    print(
        f"Ran {selected.label()} on seeds {','.join(map(str, SEEDS))}; "
        f"T={threshold:.6f}, R_max={r_max}, mean_R={mean_r}, median_R={median_r}."
    )
    print(f"Decision: {decision}; elapsed wall time {elapsed:.1f} s.")


if __name__ == "__main__":
    main()
