"""Model loading, prediction and explanation.

Explanation method: *reference perturbation* (a simple counterfactual attribution).
For each feature we replace the task's value with a "typical" reference value
(the training median) and measure how much the predicted probability changes:

    impact_f = p(x) - p(x with feature f set to its typical value)

A positive impact means "this factor is pushing the risk UP compared with a
typical task". It works with ANY model (including calibrated ones), needs no
extra library, and can be read by a judge in plain language:
"if this task had a typical number of blockers, its risk would drop by 22 points".
We deliberately prefer this over SHAP for the UI; see docs/ML.md.
"""
from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from ..core.features import FEATURE_NAMES, HistoryStats, compute_features, describe_feature
from ..core.state import ProjectState

log = logging.getLogger(__name__)

MIN_IMPACT = 0.02  # ignore factors that move the probability by < 2 points


@dataclass
class Factor:
    feature: str
    label: str
    impact: float  # change in probability (0..1 scale) vs typical value
    value: Optional[float]

    def as_dict(self) -> dict:
        v = None if self.value is None or (isinstance(self.value, float) and math.isnan(self.value)) else round(self.value, 3)
        return {"feature": self.feature, "label": self.label, "impact": round(self.impact, 3), "value": v}


@dataclass
class RiskResult:
    task_id: int
    probability: float
    level: str
    factors: list[Factor] = field(default_factory=list)       # push risk up
    mitigating: list[Factor] = field(default_factory=list)    # push risk down
    features: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "probability": round(self.probability, 3),
            "level": self.level,
            "factors": [f.as_dict() for f in self.factors],
            "mitigating": [f.as_dict() for f in self.mitigating],
        }


class Predictor:
    def __init__(self, artifact: dict, path: Optional[Path] = None):
        self.model = artifact["model"]
        self.feature_names: list[str] = artifact["feature_names"]
        if self.feature_names != FEATURE_NAMES:
            raise ValueError(
                "Model was trained with a different feature list. Retrain it with the current features.py."
            )
        self.reference: dict[str, float] = artifact["reference"]
        self.thresholds: dict[str, float] = artifact.get("thresholds", {"high": 0.6, "medium": 0.35})
        self.card: dict = artifact.get("model_card", {})
        self.metrics: dict = artifact.get("metrics", {})
        self.global_prior: float = float(artifact.get("global_late_rate", 0.3))
        self.path = path

    @property
    def version(self) -> str:
        return self.card.get("version", "unknown")

    def level_for(self, p: float) -> str:
        if p >= self.thresholds["high"]:
            return "high"
        if p >= self.thresholds["medium"]:
            return "medium"
        return "low"

    def _proba(self, rows: list[dict[str, float]]) -> np.ndarray:
        X = pd.DataFrame(rows, columns=self.feature_names).astype(float)
        return self.model.predict_proba(X)[:, 1]

    def predict_state(self, state: ProjectState, explain: bool = True) -> dict[int, RiskResult]:
        """Predict delay risk for every open task that has a deadline."""
        history = HistoryStats.from_state(state, global_prior=self.global_prior)
        results: dict[int, RiskResult] = {}
        # Already overdue: the outcome is known, so we do not "predict" it.
        for t in state.open_tasks():
            if t.deadline is not None and state.is_overdue(t):
                late_by = -compute_features(state, t, history)["days_to_deadline"]
                results[t.id] = RiskResult(
                    task_id=t.id, probability=1.0, level="overdue",
                    factors=[Factor("days_to_deadline", f"deadline passed {late_by:.1f} days ago", 1.0, -late_by)],
                )
        targets = [t for t in state.open_tasks() if t.deadline is not None and not state.is_overdue(t)]
        if not targets:
            return results
        feats = [compute_features(state, t, history) for t in targets]
        base = self._proba(feats)

        impacts = None
        if explain:
            perturbed = []
            for f in feats:
                for name in self.feature_names:
                    g = dict(f)
                    g[name] = self.reference[name]
                    perturbed.append(g)
            pp = self._proba(perturbed).reshape(len(feats), len(self.feature_names))
            impacts = base[:, None] - pp

        for i, t in enumerate(targets):
            p = float(base[i])
            r = RiskResult(task_id=t.id, probability=p, level=self.level_for(p), features=feats[i])
            if impacts is not None:
                for j, name in enumerate(self.feature_names):
                    imp = float(impacts[i, j])
                    if abs(imp) < MIN_IMPACT:
                        continue
                    fac = Factor(name, describe_feature(name, feats[i][name], self.reference[name]), imp, feats[i][name])
                    (r.factors if imp > 0 else r.mitigating).append(fac)
                r.factors.sort(key=lambda f: -f.impact)
                r.mitigating.sort(key=lambda f: f.impact)
                r.factors, r.mitigating = r.factors[:4], r.mitigating[:2]
            results[t.id] = r
        return results


# ---------------------------------------------------------------------------
# Loading (with self-healing fallback to the demo model)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_cached: Optional[Predictor] = None


def load_predictor(path: Path) -> Predictor:
    artifact = joblib.load(path)
    return Predictor(artifact, path)


def get_predictor(model_path: Path, demo_path: Path) -> Predictor:
    """Load the configured model; fall back to (re)building the synthetic demo model."""
    global _cached
    with _lock:
        if _cached is not None:
            return _cached
        for candidate in (model_path, demo_path):
            if candidate and Path(candidate).exists():
                try:
                    _cached = load_predictor(Path(candidate))
                    log.info("Loaded model %s (%s)", candidate, _cached.card.get("data_source"))
                    return _cached
                except Exception as exc:  # version mismatch, corrupt file...
                    log.warning("Could not load model %s: %s", candidate, exc)
        log.warning("No usable model found - training the synthetic DEMO model now (takes a few seconds).")
        from .demo_model import build_demo_model

        build_demo_model(Path(demo_path))
        _cached = load_predictor(Path(demo_path))
        return _cached


def reset_predictor_cache() -> None:
    global _cached
    with _lock:
        _cached = None
