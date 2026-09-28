"""End-to-end test of the ML pipeline on a FAKE TAWOS-shaped dataset."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "ml" / "tests"))

from app.core.features import FEATURE_NAMES  # noqa: E402
from app.ml.predictor import load_predictor  # noqa: E402
from app.ml.training import train_and_select  # noqa: E402
from build_tawos_snapshots import build  # noqa: E402
from fake_tawos import make_fake_tawos  # noqa: E402
from tawos_io import load_tawos  # noqa: E402


def test_pipeline(tmp_path):
    src = make_fake_tawos(tmp_path / "tawos")
    df = build(load_tawos(str(src)), verbose=False)
    assert len(df) > 500
    assert set(FEATURE_NAMES) <= set(df.columns)
    # no future info: every snapshot is taken before the sprint's deadline
    assert (df["days_to_deadline"] > 0).all()
    # spilled-over issues exist (membership reconstructed from the change log, not Issue.Sprint_ID)
    assert 0.1 < df["late"].mean() < 0.9
    out = tmp_path / "m" / "model.joblib"
    m = train_and_select(df, label_col="late", time_col="sprint_start", group_col="sprint_id",
                         out_path=out, model_card={"version": "t", "data_source": "FAKE"},
                         project_col="project_id", verbose=False)
    assert m["test"]["selected_model"]["roc_auc"] > 0.5
    p = load_predictor(out)
    assert p.feature_names == FEATURE_NAMES
