"""Model training, comparison, calibration and evaluation.

Used by:
  * ml/train.py          -> real training on TAWOS snapshots
  * app/ml/demo_model.py -> synthetic demo model (clearly labelled as such)

Methodology (see docs/ML.md):
  1. Time-ordered split by *group* (sprint / window) so that snapshots of the
     same sprint never appear on both sides of a split: 70% train / 15% valid / 15% test.
  2. Candidates: heuristic baseline, logistic regression, random forest,
     histogram gradient boosting.
  3. Select on VALIDATION PR-AUC (the positive class 'late' is the one we care about).
  4. Calibrate the winner on the validation set (probabilities are shown to users).
  5. Choose risk thresholds on validation, report everything ONCE on the untouched test set.
  6. Optional leave-project-out check for generalisation to unseen teams.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..core.features import DEFAULT_GLOBAL_LATE_RATE, FEATURE_NAMES

RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

class HeuristicBaseline:
    """What a sensible manager would do without ML: count obvious warning signs."""

    def fit(self, X, y):
        self.sp_median_ = float(np.nanmedian(X["story_points"])) if X["story_points"].notna().any() else 3.0
        self.load_median_ = float(np.nanmedian(X["assignee_open_points"]))
        return self

    def predict_proba(self, X):
        score = (
            (X["open_blockers"].fillna(0) > 0).astype(float)
            + (X["story_points"].fillna(self.sp_median_) > self.sp_median_).astype(float)
            + (X["elapsed_frac"].fillna(0) > 0.6).astype(float)
            + (X["assignee_open_points"].fillna(0) > self.load_median_).astype(float)
            + (X["days_to_deadline"].fillna(99) < 2).astype(float)
        ) / 5.0
        score = score.to_numpy()
        return np.column_stack([1 - score, score])


def candidate_models() -> dict[str, object]:
    return {
        "heuristic_baseline": HeuristicBaseline(),
        "logistic_regression": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced"),
        ),
        "random_forest": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=300, min_samples_leaf=20, class_weight="balanced_subsample",
                n_jobs=-1, random_state=RANDOM_STATE,
            ),
        ),
        "gradient_boosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=40,
            l2_regularization=1.0, early_stopping=True, random_state=RANDOM_STATE,
        ),
    }


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def temporal_group_split(df: pd.DataFrame, time_col: str, group_col: str, fractions=(0.70, 0.15)):
    """Assign whole groups to train/valid/test in chronological order."""
    g = df.groupby(group_col)[time_col].min().sort_values()
    sizes = df.groupby(group_col).size().reindex(g.index)
    cum = sizes.cumsum() / sizes.sum()
    train_groups = set(cum.index[cum <= fractions[0]])
    valid_groups = set(cum.index[(cum > fractions[0]) & (cum <= fractions[0] + fractions[1])])
    split = np.where(
        df[group_col].isin(train_groups), "train",
        np.where(df[group_col].isin(valid_groups), "valid", "test"),
    )
    return pd.Series(split, index=df.index)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _safe(fn, *a, **k):
    try:
        v = fn(*a, **k)
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    except ValueError:
        return None


def evaluate(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "n": int(len(y)),
        "late_rate": float(np.mean(y)),
        "roc_auc": _safe(roc_auc_score, y, p),
        "pr_auc": _safe(average_precision_score, y, p),
        "brier": _safe(brier_score_loss, y, p),
        "threshold": float(threshold),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "accuracy": float((pred == y).mean()),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def choose_thresholds(y: np.ndarray, p: np.ndarray, target_precision: float = 0.6, target_recall: float = 0.8):
    """HIGH = lowest threshold that still reaches the target precision (few false alarms);
    MEDIUM = highest threshold that still catches `target_recall` of late tasks."""
    prec, rec, thr = precision_recall_curve(y, p)
    prec, rec = prec[:-1], rec[:-1]
    ok = np.where(prec >= target_precision)[0]
    high = float(thr[ok[0]]) if len(ok) else float(np.quantile(p, 0.85))
    ok_r = np.where(rec >= target_recall)[0]
    medium = float(thr[ok_r[-1]]) if len(ok_r) else float(np.quantile(p, 0.5))
    high = min(max(high, 0.35), 0.9)
    medium = min(max(medium, 0.15), high - 0.1)
    return {"high": round(high, 3), "medium": round(medium, 3)}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def train_and_select(
    df: pd.DataFrame,
    *,
    label_col: str,
    time_col: str,
    group_col: str,
    out_path: Path,
    model_card: dict,
    project_col: Optional[str] = None,
    verbose: bool = True,
) -> dict:
    df = df.reset_index(drop=True)
    X = df[FEATURE_NAMES].astype(float)
    y = df[label_col].astype(int).to_numpy()
    split = temporal_group_split(df, time_col, group_col)
    tr, va, te = (split == "train").to_numpy(), (split == "valid").to_numpy(), (split == "test").to_numpy()
    if min(tr.sum(), va.sum(), te.sum()) < 20:
        raise ValueError(f"Split too small: train={tr.sum()} valid={va.sum()} test={te.sum()}")

    def say(*a):
        if verbose:
            print(*a)

    say(f"rows: train={tr.sum()} valid={va.sum()} test={te.sum()} | late rate train={y[tr].mean():.3f}")

    comparison = {}
    fitted = {}
    for name, model in candidate_models().items():
        model.fit(X[tr], y[tr])
        p_va = model.predict_proba(X[va])[:, 1]
        comparison[name] = {
            "valid_pr_auc": _safe(average_precision_score, y[va], p_va),
            "valid_roc_auc": _safe(roc_auc_score, y[va], p_va),
            "valid_brier": _safe(brier_score_loss, y[va], p_va),
        }
        fitted[name] = model
        say(f"  {name:22s} valid PR-AUC={comparison[name]['valid_pr_auc']:.3f}  ROC-AUC={comparison[name]['valid_roc_auc']:.3f}")

    ml_names = [n for n in comparison if n != "heuristic_baseline"]
    best_name = max(ml_names, key=lambda n: comparison[n]["valid_pr_auc"] or 0)
    say(f"selected: {best_name}")

    method = "isotonic" if va.sum() >= 1000 else "sigmoid"
    calibrated = CalibratedClassifierCV(FrozenEstimator(fitted[best_name]), method=method)
    calibrated.fit(X[va], y[va])

    p_va_cal = calibrated.predict_proba(X[va])[:, 1]
    thresholds = choose_thresholds(y[va], p_va_cal)

    # ---- final, one-time evaluation on the untouched test set ----
    p_te = calibrated.predict_proba(X[te])[:, 1]
    p_te_base = fitted["heuristic_baseline"].predict_proba(X[te])[:, 1]
    p_te_uncal = fitted[best_name].predict_proba(X[te])[:, 1]
    test = {
        "selected_model": evaluate(y[te], p_te, thresholds["high"]),
        "selected_model_uncalibrated_brier": _safe(brier_score_loss, y[te], p_te_uncal),
        "heuristic_baseline": evaluate(y[te], p_te_base, 0.6),
        "majority_class_accuracy": float(max(y[te].mean(), 1 - y[te].mean())),
    }
    frac_pos, mean_pred = calibration_curve(y[te], p_te, n_bins=8, strategy="quantile")
    test["calibration_curve"] = {"mean_predicted": mean_pred.round(4).tolist(), "observed_late_rate": frac_pos.round(4).tolist()}

    # ---- permutation-free global importance: mean |reference impact| on test ----
    reference = {c: float(np.nanmedian(X.loc[tr, c])) if X.loc[tr, c].notna().any() else 0.0 for c in FEATURE_NAMES}
    global_importance = {}
    Xte = X[te].copy()
    for c in FEATURE_NAMES:
        Xr = Xte.copy()
        Xr[c] = reference[c]
        global_importance[c] = float(np.mean(np.abs(p_te - calibrated.predict_proba(Xr)[:, 1])))
    global_importance = dict(sorted(global_importance.items(), key=lambda kv: -kv[1]))

    # ---- optional leave-project-out generalisation check ----
    lpo = None
    if project_col and df[project_col].nunique() >= 3:
        scores = []
        for proj in df[project_col].unique():
            hold = (df[project_col] == proj).to_numpy()
            if hold.sum() < 50 or len(np.unique(y[hold])) < 2:
                continue
            m = candidate_models()[best_name]
            m.fit(X[~hold], y[~hold])
            ph = m.predict_proba(X[hold])[:, 1]
            scores.append({"project": str(proj), "n": int(hold.sum()),
                           "pr_auc": _safe(average_precision_score, y[hold], ph),
                           "roc_auc": _safe(roc_auc_score, y[hold], ph),
                           "late_rate": float(y[hold].mean())})
        if scores:
            lpo = {
                "per_project": scores,
                "mean_pr_auc": float(np.mean([s["pr_auc"] for s in scores if s["pr_auc"] is not None])),
                "mean_roc_auc": float(np.mean([s["roc_auc"] for s in scores if s["roc_auc"] is not None])),
            }

    card = dict(model_card)
    card.update({
        "algorithm": best_name,
        "calibration": method,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows": int(len(df)),
        "n_train": int(tr.sum()), "n_valid": int(va.sum()), "n_test": int(te.sum()),
    })
    metrics = {
        "model_comparison_validation": comparison,
        "test": test,
        "thresholds": thresholds,
        "global_importance": global_importance,
        "leave_project_out": lpo,
    }
    artifact = {
        "model": calibrated,
        "feature_names": FEATURE_NAMES,
        "reference": reference,
        "thresholds": thresholds,
        "global_late_rate": DEFAULT_GLOBAL_LATE_RATE,  # same prior the snapshot builder used
        "model_card": card,
        "metrics": metrics,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, out_path)
    (out_path.parent / "metrics.json").write_text(json.dumps({"model_card": card, **metrics}, indent=2))
    sm = test["selected_model"]
    say(f"TEST ({best_name}, calibrated): PR-AUC={sm['pr_auc']:.3f} ROC-AUC={sm['roc_auc']:.3f} "
        f"Brier={sm['brier']:.3f} P={sm['precision']:.2f} R={sm['recall']:.2f} | "
        f"baseline PR-AUC={test['heuristic_baseline']['pr_auc']:.3f}")
    say(f"saved -> {out_path}")
    return {"model_card": card, **metrics}
