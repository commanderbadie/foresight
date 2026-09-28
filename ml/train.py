"""STEP 3 - train, compare, calibrate and evaluate the delay model on TAWOS snapshots.

    python ml/train.py --data ml/data/snapshots.csv.gz --out backend/models/tawos/model.joblib

Then point the backend at it:  MODEL_PATH=models/tawos/model.joblib  (see backend/.env.example)
Writes metrics.json next to the model and plots into ml/reports/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.training import train_and_select  # noqa: E402


def plots(metrics: dict, out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed - skipping plots")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    cc = metrics["test"]["calibration_curve"]
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot([0, 1], [0, 1], "--", color="#999", label="perfect")
    ax.plot(cc["mean_predicted"], cc["observed_late_rate"], "o-", color="#1f5f8b", label="model")
    ax.set_xlabel("predicted delay probability")
    ax.set_ylabel("observed late rate")
    ax.set_title("Calibration (test set)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "calibration.png", dpi=150)

    gi = metrics["global_importance"]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    names = list(gi)[:10][::-1]
    ax.barh(names, [gi[n] for n in names], color="#1f5f8b")
    ax.set_xlabel("mean |change in probability| when set to typical value")
    ax.set_title("What drives the predictions (test set)")
    fig.tight_layout()
    fig.savefig(out_dir / "importance.png", dpi=150)

    comp = metrics["model_comparison_validation"]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(list(comp), [comp[k]["valid_pr_auc"] for k in comp], color=["#bbb"] + ["#1f5f8b"] * (len(comp) - 1))
    ax.set_ylabel("PR-AUC (validation)")
    ax.set_title("Model comparison")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(out_dir / "model_comparison.png", dpi=150)
    print(f"plots -> {out_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "ml" / "data" / "snapshots.csv.gz"))
    ap.add_argument("--out", default=str(ROOT / "backend" / "models" / "tawos" / "model.joblib"))
    args = ap.parse_args()

    df = pd.read_csv(args.data, parse_dates=["sprint_start"])
    card = {
        "version": "tawos-1",
        "data_source": "TAWOS",
        "is_synthetic": False,
        "dataset": "TAWOS (Tawosi et al., MSR 2022), DOI 10.5522/04/21308124, Apache-2.0",
        "target": "issue not resolved by the planned end of its sprint (sprint spillover)",
        "snapshot_points": sorted(df["snapshot_frac"].unique().tolist()),
        "limitations": [
            "Trained on open-source teams; the app's teams may behave differently (domain shift).",
            "Priority and issue type are taken at their final values (small leakage risk).",
            "Issues removed from a sprint before it ended are still labelled against that sprint.",
        ],
    }
    metrics = train_and_select(
        df, label_col="late", time_col="sprint_start", group_col="sprint_id",
        out_path=Path(args.out), model_card=card, project_col="project_id",
    )
    plots(metrics, ROOT / "ml" / "reports")
    print(json.dumps(metrics["test"]["selected_model"], indent=2))


if __name__ == "__main__":
    main()
