#!/usr/bin/env python3
"""Deterministic synthetic grokking eligibility winner's-curse experiment."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "figures"
CHECKPOINTS = np.arange(100, 5001, 100, dtype=int)
TAU = 5000
N_SEEDS = 48
SELECTION_IDS = tuple(range(24))
HELDOUT_IDS = tuple(range(24, 48))


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: str
    order: int
    deadline: int
    train_threshold: float
    validation_ceiling: float


BROAD_RULE = Rule("B", "broad", -1, 3000, 0.80, 0.50)
SEARCHABLE_RULES = tuple(
    Rule(
        rule_id=f"R{order + 1:02d}",
        kind="searchable",
        order=order,
        deadline=deadline,
        train_threshold=train_threshold,
        validation_ceiling=validation_ceiling,
    )
    for order, (deadline, train_threshold, validation_ceiling) in enumerate(
        product((1200, 1800, 2400), (0.90, 0.97), (0.20, 0.40))
    )
)
ALL_RULES = (BROAD_RULE,) + SEARCHABLE_RULES


def split_for_seed(seed_id: int) -> str:
    """Prospective split assignment, fixed before trajectory generation."""
    return "selection" if seed_id in SELECTION_IDS else "heldout"


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def grok_outcome(validation_accuracy: np.ndarray) -> dict[str, Any]:
    qualifying = validation_accuracy >= 0.90
    starts = np.flatnonzero(
        qualifying[:-2] & qualifying[1:-1] & qualifying[2:]
    )
    if starts.size:
        observed = int(CHECKPOINTS[int(starts[0])])
        return {"grokked": True, "observed_time": observed, "restricted_time": observed}
    return {"grokked": False, "observed_time": None, "restricted_time": TAU}


def eligibility(reference_rows: pd.DataFrame, rule: Rule) -> tuple[bool, int | None]:
    qualifying = reference_rows.loc[
        reference_rows["checkpoint"].between(400, rule.deadline)
        & (reference_rows["train_accuracy"] >= rule.train_threshold)
        & (reference_rows["validation_accuracy"] <= rule.validation_ceiling),
        "checkpoint",
    ]
    if qualifying.empty:
        return False, None
    return True, int(qualifying.iloc[0])


def json_scalar(value: Any) -> Any:
    """Return a strict-JSON scalar, spelling non-finite decision sentinels."""
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        if math.isnan(numeric):
            return "NaN"
        if math.isinf(numeric):
            return "Infinity" if numeric > 0 else "-Infinity"
        return numeric
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"Not a JSON scalar: {type(value).__name__}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def generate_trajectories() -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple[int, str], dict[str, Any]]]:
    trajectory_rows: list[dict[str, Any]] = []
    parameter_rows: list[dict[str, Any]] = []
    outcomes: dict[tuple[int, str], dict[str, Any]] = {}

    for seed_id in range(N_SEEDS):
        rng = np.random.default_rng(730000 + seed_id)
        d, m, g, h = rng.normal(size=4)

        m_ref = math.exp(math.log(700.0) + 0.25 * d + 0.12 * m)
        d_ref = math.exp(math.log(2200.0) + 0.50 * d + 0.35 * g)
        g_ref = m_ref + d_ref
        m_double = m_ref / (2.0**0.65)
        d_double = d_ref * math.exp(-0.35 + 0.35 * h)
        g_double = m_double + d_double

        # Protocol-mandated draw order: ref train, ref validation, double train,
        # then double validation, with exactly 50 draws in each block.
        ref_train_noise = rng.normal(0.0, 0.012, size=50)
        ref_validation_noise = rng.normal(0.0, 0.012, size=50)
        double_train_noise = rng.normal(0.0, 0.012, size=50)
        double_validation_noise = rng.normal(0.0, 0.012, size=50)

        parameter_rows.append(
            {
                "seed_id": seed_id,
                "prospective_split": split_for_seed(seed_id),
                "M_ref": m_ref,
                "G_ref": g_ref,
            }
        )

        arms = (
            ("reference", m_ref, g_ref, ref_train_noise, ref_validation_noise),
            ("double", m_double, g_double, double_train_noise, double_validation_noise),
        )
        for arm, memorization, transition, train_noise, validation_noise in arms:
            train_accuracy = np.clip(
                0.05 + 0.94 * sigmoid((CHECKPOINTS - memorization) / 120.0) + train_noise,
                0.0,
                1.0,
            )
            validation_accuracy = np.clip(
                0.10 + 0.88 * sigmoid((CHECKPOINTS - transition) / 180.0)
                + validation_noise,
                0.0,
                1.0,
            )
            outcomes[(seed_id, arm)] = grok_outcome(validation_accuracy)
            for checkpoint, train_value, validation_value in zip(
                CHECKPOINTS, train_accuracy, validation_accuracy, strict=True
            ):
                trajectory_rows.append(
                    {
                        "seed_id": seed_id,
                        "prospective_split": split_for_seed(seed_id),
                        "arm": arm,
                        "checkpoint": int(checkpoint),
                        "train_accuracy": float(train_value),
                        "validation_accuracy": float(validation_value),
                    }
                )

    trajectories = pd.DataFrame(trajectory_rows)
    parameters = pd.DataFrame(parameter_rows)
    assert len(trajectories) == N_SEEDS * 2 * len(CHECKPOINTS) == 4800
    assert len(parameters) == N_SEEDS
    assert set(parameters.loc[parameters["prospective_split"] == "selection", "seed_id"]) == set(SELECTION_IDS)
    assert set(parameters.loc[parameters["prospective_split"] == "heldout", "seed_id"]) == set(HELDOUT_IDS)
    return trajectories, parameters, outcomes


def build_and_write_ledger(
    trajectories: pd.DataFrame,
    parameters: pd.DataFrame,
    outcomes: dict[tuple[int, str], dict[str, Any]],
) -> tuple[pd.DataFrame, dict[tuple[int, str], bool]]:
    ledger_rows: list[dict[str, Any]] = []
    eligibility_map: dict[tuple[int, str], bool] = {}

    for seed_id in range(N_SEEDS):
        params = parameters.loc[parameters["seed_id"] == seed_id].iloc[0]
        reference = trajectories.loc[
            (trajectories["seed_id"] == seed_id) & (trajectories["arm"] == "reference")
        ].sort_values("checkpoint")
        reference_outcome = outcomes[(seed_id, "reference")]
        row: dict[str, Any] = {
            "seed_id": seed_id,
            "prospective_split": params["prospective_split"],
            "M_ref": float(params["M_ref"]),
            "G_ref": float(params["G_ref"]),
            "reference_grok_status": "GROKKED" if reference_outcome["grokked"] else "NON_GROKKING",
            "reference_observed_grok_time": (
                str(reference_outcome["observed_time"])
                if reference_outcome["grokked"]
                else "CENSORED"
            ),
            "reference_restricted_time": int(reference_outcome["restricted_time"]),
        }
        for rule in ALL_RULES:
            eligible, earliest = eligibility(reference, rule)
            eligibility_map[(seed_id, rule.rule_id)] = eligible
            prefix = "broad_rule" if rule.rule_id == "B" else rule.rule_id
            row[f"{prefix}_eligible"] = "TRUE" if eligible else "FALSE"
            row[f"{prefix}_earliest_checkpoint"] = str(earliest) if eligible else "NA"
        ledger_rows.append(row)

    ledger = pd.DataFrame(ledger_rows)
    assert len(ledger) == N_SEEDS
    assert ledger["seed_id"].nunique() == N_SEEDS
    assert set(ledger["seed_id"]) == set(range(N_SEEDS))
    expected_reference_non_grok = sum(
        not outcomes[(seed_id, "reference")]["grokked"] for seed_id in range(N_SEEDS)
    )
    assert int((ledger["reference_grok_status"] == "NON_GROKKING").sum()) == expected_reference_non_grok

    eligibility_columns = [
        "broad_rule_eligible",
        *(f"{rule.rule_id}_eligible" for rule in SEARCHABLE_RULES),
    ]
    all_rule_ineligible = (ledger[eligibility_columns] == "FALSE").all(axis=1)
    assert int(all_rule_ineligible.sum()) == sum(
        not any(eligibility_map[(seed_id, rule.rule_id)] for rule in ALL_RULES)
        for seed_id in range(N_SEEDS)
    )

    # Immutable attempted-reference record: this occurs before any paired sample
    # is formed and before any intervention effect is calculated.
    ledger.to_csv(ROOT / "attempted_reference_ledger.csv", index=False)
    return ledger, eligibility_map


def calculate_rule_results(
    outcomes: dict[tuple[int, str], dict[str, Any]],
    eligibility_map: dict[tuple[int, str], bool],
) -> pd.DataFrame:
    result_rows: list[dict[str, Any]] = []
    for rule in ALL_RULES:
        for split, split_ids in (("selection", SELECTION_IDS), ("heldout", HELDOUT_IDS)):
            eligible_ids = [
                seed_id for seed_id in split_ids if eligibility_map[(seed_id, rule.rule_id)]
            ]
            reference_times = np.array(
                [outcomes[(seed_id, "reference")]["restricted_time"] for seed_id in eligible_ids],
                dtype=float,
            )
            double_times = np.array(
                [outcomes[(seed_id, "double")]["restricted_time"] for seed_id in eligible_ids],
                dtype=float,
            )
            if eligible_ids:
                rmst_reference = float(reference_times.mean())
                rmst_double = float(double_times.mean())
                effect = (rmst_reference - rmst_double) / rmst_reference
            else:
                rmst_reference = math.nan
                rmst_double = math.nan
                effect = math.nan
            result_rows.append(
                {
                    "rule_id": rule.rule_id,
                    "rule_type": rule.kind,
                    "enumeration_order": rule.order,
                    "deadline": rule.deadline,
                    "train_threshold": rule.train_threshold,
                    "validation_ceiling": rule.validation_ceiling,
                    "split": split,
                    "eligible_pair_count": len(eligible_ids),
                    "reference_non_grok_count": sum(
                        not outcomes[(seed_id, "reference")]["grokked"] for seed_id in eligible_ids
                    ),
                    "double_non_grok_count": sum(
                        not outcomes[(seed_id, "double")]["grokked"] for seed_id in eligible_ids
                    ),
                    "RMST_reference": rmst_reference,
                    "RMST_double": rmst_double,
                    "relative_intervention_reduction": effect,
                }
            )

    results = pd.DataFrame(result_rows)
    assert len(results) == len(ALL_RULES) * 2 == 26
    return results


def result_row(rule_results: pd.DataFrame, rule_id: str, split: str) -> pd.Series:
    matches = rule_results.loc[
        (rule_results["rule_id"] == rule_id) & (rule_results["split"] == split)
    ]
    assert len(matches) == 1
    return matches.iloc[0]


def choose_rule(rule_results: pd.DataFrame) -> Rule | None:
    best_rule: Rule | None = None
    best_effect = -math.inf
    for rule in SEARCHABLE_RULES:
        row = result_row(rule_results, rule.rule_id, "selection")
        if int(row["eligible_pair_count"]) >= 6:
            effect = float(row["relative_intervention_reduction"])
            # Strict greater-than preserves protocol enumeration order on exact ties.
            if effect > best_effect:
                best_effect = effect
                best_rule = rule
    return best_rule


def create_figure(
    rule_results: pd.DataFrame,
    selected_rule: Rule,
    uplift: float,
    retention: float,
    selection_excess: float,
    heldout_excess: float,
) -> None:
    FIGURES.mkdir(exist_ok=True)
    labels = [rule.rule_id for rule in ALL_RULES]
    x_values = np.arange(len(labels), dtype=float)
    selected_index = labels.index(selected_rule.rule_id)

    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(18, 9), dpi=100, gridspec_kw={"width_ratios": [1.65, 1.0]}
    )

    for index, rule in enumerate(ALL_RULES):
        selection_effect = float(
            result_row(rule_results, rule.rule_id, "selection")["relative_intervention_reduction"]
        )
        heldout_effect = float(
            result_row(rule_results, rule.rule_id, "heldout")["relative_intervention_reduction"]
        )
        highlighted = rule.rule_id in {"B", selected_rule.rule_id}
        color = "#c43c39" if rule.rule_id == selected_rule.rule_id else (
            "#235789" if rule.rule_id == "B" else "#888888"
        )
        ax_left.plot(
            [index - 0.13, index + 0.13],
            [selection_effect, heldout_effect],
            color=color,
            linewidth=2.4 if highlighted else 0.8,
            alpha=1.0 if highlighted else 0.65,
            zorder=2,
        )
        ax_left.scatter(
            index - 0.13,
            selection_effect,
            marker="o",
            s=95 if highlighted else 42,
            color=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        ax_left.scatter(
            index + 0.13,
            heldout_effect,
            marker="s",
            s=95 if highlighted else 42,
            color=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )

    ax_left.axvline(0.5, color="black", linewidth=1.0)
    ax_left.axhline(0.0, color="black", linewidth=0.8, alpha=0.6)
    ax_left.set_xticks(x_values, labels)
    ax_left.set_xlabel("Reference-checkpoint eligibility rule")
    ax_left.set_ylabel("Relative RMST reduction, E")
    ax_left.set_title("Rule effects on prospective selection and held-out splits")
    ax_left.grid(axis="y", alpha=0.22)
    ax_left.scatter([], [], marker="o", color="#666666", label="Selection")
    ax_left.scatter([], [], marker="s", color="#666666", label="Held-out")
    ax_left.legend(loc="best", frameon=False)
    ax_left.text(0.0, 1.01, "Broad", transform=ax_left.get_xaxis_transform(), ha="center")
    ax_left.text(6.5, 1.01, "Searchable rules", transform=ax_left.get_xaxis_transform(), ha="center")

    bars = ax_right.bar(
        [0, 1],
        [selection_excess, heldout_excess],
        color=["#c43c39", "#4c78a8"],
        width=0.62,
    )
    ax_right.axhline(0.0, color="black", linewidth=1.0)
    ax_right.axhline(
        0.5 * selection_excess,
        color="#7a3e9d",
        linestyle="--",
        linewidth=1.5,
        label=r"$0.5D_{selection}$",
    )
    ax_right.set_xticks([0, 1], [r"$D_{selection}$", r"$D_{heldout}$"])
    ax_right.set_ylabel("Excess over broad-rule effect")
    ax_right.set_title("Selection excess and held-out retention")
    ax_right.grid(axis="y", alpha=0.22)
    ax_right.legend(loc="best", frameon=False)
    for bar, value in zip(bars, (selection_excess, heldout_excess), strict=True):
        vertical_offset = 5 if value >= 0 else -17
        ax_right.annotate(
            f"{value:.3f}",
            (bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, vertical_offset),
            textcoords="offset points",
            ha="center",
            va="bottom" if value >= 0 else "top",
            fontsize=11,
        )

    selection_n = int(result_row(rule_results, selected_rule.rule_id, "selection")["eligible_pair_count"])
    heldout_n = int(result_row(rule_results, selected_rule.rule_id, "heldout")["eligible_pair_count"])
    annotation = (
        f"Selected {selected_rule.rule_id}: D≤{selected_rule.deadline}, "
        f"A≥{selected_rule.train_threshold:.2f}, V≤{selected_rule.validation_ceiling:.2f}\n"
        f"U = {uplift:.3f}    R = {retention:.3f}\n"
        f"Eligible pairs: selection n={selection_n}, held-out n={heldout_n}"
    )
    ax_right.text(
        0.04,
        0.97,
        annotation,
        transform=ax_right.transAxes,
        va="top",
        ha="left",
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": "#bbbbbb", "alpha": 0.92},
    )

    fig.suptitle("Eligibility-rule winner's curse in paired synthetic grokking trajectories", fontsize=16)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    figure_path = FIGURES / "eligibility_winners_curse.png"
    fig.savefig(figure_path, dpi=100, metadata={"Software": "experiment.py"})
    plt.close(fig)
    shutil.copyfile(figure_path, ROOT / "eligibility_winners_curse.png")


def main() -> None:
    trajectories, parameters, outcomes = generate_trajectories()
    trajectories.to_csv(
        ROOT / "all_trajectories.csv.gz",
        index=False,
        compression={"method": "gzip", "compresslevel": 9, "mtime": 0},
    )

    # The ledger is finalized before calculate_rule_results forms paired samples.
    ledger, eligibility_map = build_and_write_ledger(trajectories, parameters, outcomes)
    rule_results = calculate_rule_results(outcomes, eligibility_map)
    rule_results.to_csv(ROOT / "rule_results.csv", index=False)

    selected_rule = choose_rule(rule_results)
    if selected_rule is None:
        raise RuntimeError("No searchable rule has at least 6 eligible selection pairs")

    broad_selection = result_row(rule_results, "B", "selection")
    broad_heldout = result_row(rule_results, "B", "heldout")
    chosen_selection = result_row(rule_results, selected_rule.rule_id, "selection")
    chosen_heldout = result_row(rule_results, selected_rule.rule_id, "heldout")

    e_broad_selection = float(broad_selection["relative_intervention_reduction"])
    e_broad_heldout = float(broad_heldout["relative_intervention_reduction"])
    e_chosen_selection = float(chosen_selection["relative_intervention_reduction"])
    e_chosen_heldout = float(chosen_heldout["relative_intervention_reduction"])
    selection_excess = e_chosen_selection - e_broad_selection
    heldout_excess = e_chosen_heldout - e_broad_heldout
    retention = heldout_excess / selection_excess if selection_excess > 0 else math.inf
    uplift = e_chosen_selection / e_broad_selection - 1.0 if e_broad_selection > 0 else -math.inf

    broad_selection_n = int(broad_selection["eligible_pair_count"])
    broad_heldout_n = int(broad_heldout["eligible_pair_count"])
    chosen_selection_n = int(chosen_selection["eligible_pair_count"])
    chosen_heldout_n = int(chosen_heldout["eligible_pair_count"])

    conditions = {
        "broad_selection_n_at_least_6": broad_selection_n >= 6,
        "broad_heldout_n_at_least_6": broad_heldout_n >= 6,
        "chosen_selection_n_at_least_6": chosen_selection_n >= 6,
        "chosen_heldout_n_at_least_6": chosen_heldout_n >= 6,
        "broad_selection_effect_positive": e_broad_selection > 0,
        "selection_uplift_at_least_30_percent": e_chosen_selection >= 1.30 * e_broad_selection,
        "selection_excess_positive": selection_excess > 0,
        "heldout_retention_at_most_half": heldout_excess <= 0.50 * selection_excess,
    }
    decision = "SUPPORTED" if all(conditions.values()) else "REFUTED"

    sample_sizes = {
        f"{row.rule_id}_{row.split}": int(row.eligible_pair_count)
        for row in rule_results.itertuples(index=False)
    }
    summary_metrics = {
        "r_star": selected_rule.rule_id,
        "r_star_thresholds": {
            "deadline": selected_rule.deadline,
            "train_threshold": selected_rule.train_threshold,
            "validation_ceiling": selected_rule.validation_ceiling,
        },
        "effects": {
            "broad_selection": e_broad_selection,
            "broad_heldout": e_broad_heldout,
            "chosen_selection": e_chosen_selection,
            "chosen_heldout": e_chosen_heldout,
        },
        "U": uplift,
        "D_selection": selection_excess,
        "D_holdout": heldout_excess,
        "R": retention,
        "ledger_row_count": len(ledger),
        "ledger_unique_seed_count": int(ledger["seed_id"].nunique()),
        "ledger_coverage": float(ledger["seed_id"].nunique() / N_SEEDS),
        "all_sample_sizes": sample_sizes,
        "broad_selection_n": broad_selection_n,
        "broad_heldout_n": broad_heldout_n,
        "chosen_selection_n": chosen_selection_n,
        "chosen_heldout_n": chosen_heldout_n,
        "decision_conditions": conditions,
        "decision": decision,
    }
    # Values are finite for this deterministic run; scalar conversion remains
    # robust to protocol-defined infinities in alternate re-runs.
    strict_summary = {
        key: (
            {nested_key: json_scalar(nested_value) for nested_key, nested_value in value.items()}
            if isinstance(value, dict) and all(not isinstance(v, dict) for v in value.values())
            else value
        )
        for key, value in summary_metrics.items()
    }
    write_json(ROOT / "summary_metrics.json", strict_summary)

    create_figure(
        rule_results,
        selected_rule,
        uplift,
        retention,
        selection_excess,
        heldout_excess,
    )

    eligibility_columns = [f"{rule.rule_id}_eligible" for rule in SEARCHABLE_RULES]
    all_searchable_ineligible_count = int((ledger[eligibility_columns] == "FALSE").all(axis=1).sum())
    reference_non_grok_count = int((ledger["reference_grok_status"] == "NON_GROKKING").sum())
    results = {
        "seed_count": N_SEEDS,
        "trajectory_row_count": len(trajectories),
        "ledger_row_count": len(ledger),
        "ledger_unique_seed_count": int(ledger["seed_id"].nunique()),
        "ledger_coverage": float(ledger["seed_id"].nunique() / N_SEEDS),
        "ledger_reference_non_grok_count": reference_non_grok_count,
        "ledger_all_searchable_rules_ineligible_count": all_searchable_ineligible_count,
        "rule_result_row_count": len(rule_results),
        "r_star": selected_rule.rule_id,
        "r_star_deadline": selected_rule.deadline,
        "r_star_train_threshold": selected_rule.train_threshold,
        "r_star_validation_ceiling": selected_rule.validation_ceiling,
        "broad_selection_effect": e_broad_selection,
        "broad_heldout_effect": e_broad_heldout,
        "chosen_selection_effect": e_chosen_selection,
        "chosen_heldout_effect": e_chosen_heldout,
        "post_hoc_selection_uplift_U": uplift,
        "selection_excess_D_selection": selection_excess,
        "heldout_excess_D_holdout": heldout_excess,
        "excess_retention_fraction_R": retention,
        "broad_selection_n": broad_selection_n,
        "broad_heldout_n": broad_heldout_n,
        "chosen_selection_n": chosen_selection_n,
        "chosen_heldout_n": chosen_heldout_n,
        "broad_selection_reference_non_grok_count": int(broad_selection["reference_non_grok_count"]),
        "broad_selection_double_non_grok_count": int(broad_selection["double_non_grok_count"]),
        "broad_heldout_reference_non_grok_count": int(broad_heldout["reference_non_grok_count"]),
        "broad_heldout_double_non_grok_count": int(broad_heldout["double_non_grok_count"]),
        "chosen_selection_reference_non_grok_count": int(chosen_selection["reference_non_grok_count"]),
        "chosen_selection_double_non_grok_count": int(chosen_selection["double_non_grok_count"]),
        "chosen_heldout_reference_non_grok_count": int(chosen_heldout["reference_non_grok_count"]),
        "chosen_heldout_double_non_grok_count": int(chosen_heldout["double_non_grok_count"]),
        **conditions,
        "decision": decision,
    }
    assert all(not isinstance(value, (dict, list, tuple)) for value in results.values())
    write_json(ROOT / "results.json", {key: json_scalar(value) for key, value in results.items()})

    print(
        "Ran 48 deterministic paired trajectories and evaluated 12 searchable eligibility rules "
        "against the broad rule."
    )
    print(
        f"Selected {selected_rule.rule_id} (D={selected_rule.deadline}, "
        f"A={selected_rule.train_threshold:.2f}, V={selected_rule.validation_ceiling:.2f}); "
        f"E broad/chosen selection={e_broad_selection:.4f}/{e_chosen_selection:.4f}, "
        f"E broad/chosen held-out={e_broad_heldout:.4f}/{e_chosen_heldout:.4f}."
    )
    print(
        f"U={uplift:.4f}, D_selection={selection_excess:.4f}, "
        f"D_holdout={heldout_excess:.4f}, R={retention:.4f}; "
        f"eligible n broad={broad_selection_n}/{broad_heldout_n}, "
        f"chosen={chosen_selection_n}/{chosen_heldout_n}."
    )
    print(f"Decision: {decision}.")


if __name__ == "__main__":
    main()
