"""STEP 1 - audit the TAWOS dump before any modelling.

    python ml/audit_tawos.py --source mysql+pymysql://root:root@localhost/tawos

Answers the questions from the project brief: size, columns, types, missing
values, duplicates, timestamps, target construction, class balance, feature
distributions, correlations and leakage red flags. Writes ml/reports/audit.md.
Decision gate at the end tells you whether the sprint-spillover formulation is viable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

from app.core.features import FEATURE_NAMES  # noqa: E402
from build_tawos_snapshots import build  # noqa: E402
from tawos_io import SCHEMA, _read_table, load_tawos  # noqa: E402

MIN_ROWS = 20_000
LATE_RATE_RANGE = (0.10, 0.70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None)
    ap.add_argument("--sample-projects", type=int, default=8, help="projects used for the snapshot dry run (0 = all)")
    args = ap.parse_args()
    out = []

    def p(line=""):
        print(line)
        out.append(line)

    import os
    source = args.source or os.environ.get("TAWOS_SOURCE", "mysql+pymysql://root:root@localhost:3306/tawos")
    p("# TAWOS audit\n")
    p("## 1. Raw tables and columns")
    for key, spec in SCHEMA.items():
        raw = _read_table(source, spec["table"])
        expected = [c for k, c in spec.items() if k != "table"]
        missing = [c for c in expected if c not in raw.columns]
        p(f"\n### {spec['table']}: {len(raw):,} rows, {raw.shape[1]} columns, {raw.duplicated().sum():,} duplicate rows")
        p("| column | dtype | missing % |")
        p("|---|---|---|")
        for c in raw.columns:
            p(f"| {c} | {raw[c].dtype} | {raw[c].isna().mean() * 100:.1f} |")
        if missing:
            p(f"\n**MISSING expected columns: {missing} -> fix SCHEMA in ml/tawos_io.py**")
    tables = load_tawos(source)
    iss, spr, cl, lk = tables["issue"], tables["sprint"], tables["change_log"], tables["issue_link"]

    p("\n## 2. Coverage")
    p(f"- projects: {iss['project'].nunique()}, issues: {len(iss):,}, sprints: {len(spr):,}")
    p(f"- issues with a (final) Sprint_ID: {iss['sprint'].notna().mean() * 100:.1f}%")
    p(f"- issues with story points: {iss['story_points'].notna().mean() * 100:.1f}%")
    p(f"- issues resolved: {iss['resolved'].notna().mean() * 100:.1f}%")
    spr_days = (spr["end"] - spr["start"]).dt.total_seconds() / 86400
    p(f"- sprint length (days): median {spr_days.median():.1f}, p10 {spr_days.quantile(.1):.1f}, p90 {spr_days.quantile(.9):.1f}")
    p(f"- sprints with valid start/end: {spr_days.notna().mean() * 100:.1f}%")
    p("\n### Change-log fields (top 15)")
    for f, n in cl["field"].astype(str).str.lower().value_counts().head(15).items():
        p(f"- {f}: {n:,}")
    p("\n### Issue link names")
    for f, n in lk["name"].astype(str).value_counts().head(10).items():
        p(f"- {f}: {n:,}")
    p("\n### Priorities / types")
    p(str(iss["priority"].value_counts().head(10).to_dict()))
    p(str(iss["type"].value_counts().head(10).to_dict()))

    p("\n## 3. Snapshot dry run")
    if args.sample_projects:
        keep = iss["project"].value_counts().head(args.sample_projects).index
        tables = {**tables,
                  "issue": iss[iss["project"].isin(keep)],
                  "sprint": spr[spr["project"].isin(keep)]}
        p(f"(largest {args.sample_projects} projects only - use --sample-projects 0 for all)")
    df = build(tables, verbose=False)
    if df.empty:
        p("\n**No snapshot rows produced. Check sprint membership parsing (Sprint change-log field).**")
    else:
        p(f"- rows: {len(df):,}, sprints: {df['sprint_id'].nunique():,}, projects: {df['project_id'].nunique()}")
        p(f"- late (spillover) rate: {df['late'].mean():.3f}")
        p("- late rate by snapshot point: " + str(df.groupby('snapshot_frac')['late'].mean().round(3).to_dict()))
        p("\n| feature | missing % | mean | corr with late |")
        p("|---|---|---|---|")
        for c in FEATURE_NAMES:
            corr = df[[c, "late"]].corr().iloc[0, 1]
            p(f"| {c} | {df[c].isna().mean() * 100:.1f} | {df[c].mean():.3f} | {corr:+.3f} |")
        suspicious = [c for c in FEATURE_NAMES if abs(df[[c, 'late']].corr().iloc[0, 1]) > 0.6]
        if suspicious:
            p(f"\n**Leakage red flag: very high correlation for {suspicious}. Investigate before training.**")

        p("\n## 4. Decision gate")
        rate = df["late"].mean()
        est_total = len(df) if not args.sample_projects else len(df) * iss["project"].nunique() / max(args.sample_projects, 1)
        ok_rows = est_total >= MIN_ROWS
        ok_rate = LATE_RATE_RANGE[0] <= rate <= LATE_RATE_RANGE[1]
        p(f"- enough rows (>= {MIN_ROWS:,}, estimated {est_total:,.0f}): {'PASS' if ok_rows else 'FAIL'}")
        p(f"- usable class balance ({LATE_RATE_RANGE}): {'PASS' if ok_rate else 'FAIL'}")
        p("- VERDICT: " + ("proceed with sprint-spillover formulation (python ml/train.py)" if ok_rows and ok_rate
                           else "switch to the Montgomery Public Jira dataset or a due-date target; see docs/ML.md"))

    rep = ROOT / "ml" / "reports" / "audit.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join(out))
    print(f"\nreport -> {rep}")


if __name__ == "__main__":
    main()
