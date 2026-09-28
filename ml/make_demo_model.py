"""Rebuild the SYNTHETIC demo model (used until you train on TAWOS).

    python ml/make_demo_model.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.demo_model import build_demo_model  # noqa: E402

if __name__ == "__main__":
    build_demo_model(ROOT / "backend" / "models" / "demo" / "model.joblib", verbose=True)
