"""SYNTHETIC demo model.

Purpose: let the application run end-to-end *before* the real TAWOS model is
trained (e.g. on a fresh laptop). Its data is generated from a hand-written
rule plus noise, so its metrics say NOTHING about real-world performance.
The UI shows a visible "Demo model - synthetic data" badge whenever it is used.

Replace it by running:  python ml/train.py  (see docs/ML.md)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core.features import FEATURE_NAMES
from .training import train_and_select

GENERATING_RULE = (
    "logit = -3.0 + 0.16*story_points + 0.85*open_blockers + 0.07*assignee_open_points "
    "+ 1.6*elapsed_frac - 0.05*min(days_to_deadline, 20) + 2.2*(assignee_hist_late_rate-0.3) "
    "+ 0.35*is_bug + 0.25*reassign_count + 0.6*is_unassigned + noise(sd=0.6)"
)


def generate_synthetic(n_groups: int = 900, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_groups):
        window = float(rng.choice([7, 10, 14, 14, 21]))
        project = int(rng.integers(0, 6))
        proj_rate = float(np.clip(rng.normal(0.3, 0.08), 0.05, 0.7))
        for _ in range(int(rng.integers(6, 14))):
            elapsed = float(rng.choice([0.0, 0.5, 0.75]))
            sp = float(rng.choice([1, 2, 3, 3, 5, 5, 8, 13]))
            blockers = float(rng.poisson(0.35))
            load = float(max(rng.normal(8, 5), 0))
            hist = float(np.clip(rng.normal(proj_rate, 0.12), 0.02, 0.9))
            days = window * (1 - elapsed)
            bug = float(rng.random() < 0.25)
            reassign = float(rng.poisson(0.2))
            unassigned = float(rng.random() < 0.05)
            logit = (-3.0 + 0.16 * sp + 0.85 * blockers + 0.07 * load + 1.6 * elapsed
                     - 0.05 * min(days, 20) + 2.2 * (hist - 0.3) + 0.35 * bug + 0.25 * reassign
                     + 0.6 * unassigned + rng.normal(0, 0.6))
            late = int(rng.random() < 1 / (1 + np.exp(-logit)))
            rows.append({
                "story_points": sp if rng.random() > 0.08 else np.nan,
                "priority_rank": float(rng.choice([1, 2, 2, 3, 3, 4])),
                "is_bug": bug,
                "days_to_deadline": days,
                "window_days": window,
                "elapsed_frac": elapsed,
                "assignee_open_points": load,
                "assignee_open_count": float(round(load / 3.5)),
                "open_blockers": blockers,
                "assignee_hist_late_rate": hist,
                "project_hist_late_rate": proj_rate,
                "age_days": float(window * elapsed + rng.exponential(6)),
                "reassign_count": reassign,
                "desc_len_log": float(np.log1p(rng.integers(0, 1500))),
                "is_unassigned": unassigned,
                "late": late,
                "group": g,
                "window_start": g,  # chronological order
                "project": project,
            })
    df = pd.DataFrame(rows)
    assert set(FEATURE_NAMES).issubset(df.columns)
    return df


def build_demo_model(out_path: Path, verbose: bool = False) -> dict:
    df = generate_synthetic()
    card = {
        "version": "demo-synthetic-1",
        "data_source": "SYNTHETIC_DEMO",
        "is_synthetic": True,
        "target": "task not finished by its deadline",
        "warning": "Trained on synthetic data generated from a hand-written rule. "
                   "Metrics are NOT evidence of real-world accuracy. Train on TAWOS with ml/train.py.",
        "generating_rule": GENERATING_RULE,
    }
    return train_and_select(
        df, label_col="late", time_col="window_start", group_col="group",
        out_path=out_path, model_card=card, project_col="project", verbose=verbose,
    )
