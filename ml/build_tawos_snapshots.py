"""Build leakage-safe training snapshots from TAWOS.

    python ml/build_tawos_snapshots.py --source mysql+pymysql://root:root@localhost/tawos \
                                       --out ml/data/snapshots.csv.gz

ML problem ("sprint spillover"):
    For an issue committed to a sprint, at snapshot time T (sprint start, 50% and
    75% of the sprint), predict whether it will NOT be resolved by the sprint's
    planned end date. In the app, the sprint end corresponds to the task deadline.

Leakage controls (see docs/ML.md):
  * Sprint membership is reconstructed from the change log. Issue.Sprint_ID only
    stores the LAST sprint, so issues that spilled over would otherwise look
    on-time in the sprint where they were eventually finished.
  * Assignee and story points are reconstructed AS OF time T from the change log.
  * An issue enters a snapshot only if it was already in the sprint at T.
  * Historical late rates only use sprints that ENDED before this sprint STARTED.
  * Resolution date / time spent / final status are used for the LABEL only.
Every feature is computed by backend/app/core/features.py - the same code the
live application uses.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

from app.core.features import FEATURE_NAMES, HistoryStats, JIRA_PRIORITY_RANK, compute_features  # noqa: E402
from app.core.state import MemberState, ProjectState, TaskState  # noqa: E402
from tawos_io import (ASSIGNEE_FIELDS, BLOCKING_LINK_NAMES, SPRINT_FIELDS,  # noqa: E402
                      STORY_POINT_FIELDS, load_tawos)

SNAPSHOT_FRACTIONS = (0.0, 0.5, 0.75)
MAX_SPRINT_DAYS = 42
MIN_SPRINT_ISSUES = 3
RANK_TO_APP_PRIORITY = {1: "low", 2: "medium", 3: "high", 4: "critical"}


def _tokens(v) -> set[str]:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return set()
    return {t.strip() for t in str(v).replace("[", "").replace("]", "").split(",") if t.strip()}


def _float(v):
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


class History:
    """Change-log lookups: value of a field as of time T."""

    def __init__(self, change_log: pd.DataFrame):
        cl = change_log.copy()
        cl["field_l"] = cl["field"].astype(str).str.lower().str.strip()
        cl = cl.sort_values("created")
        self.by_field: dict[str, dict[int, list[tuple]]] = {}
        for name, fields in (("sprint", SPRINT_FIELDS), ("assignee", ASSIGNEE_FIELDS), ("points", STORY_POINT_FIELDS)):
            sub = cl[cl["field_l"].isin(fields)]
            d: dict[int, list[tuple]] = defaultdict(list)
            for row in sub.itertuples(index=False):
                d[int(row.issue)].append((row.created, row.from_value, row.to_value))
            self.by_field[name] = d

    def value_at(self, field: str, issue_id: int, T, final):
        """Value just before T: from_value of the first change after T, else final value."""
        for created, from_v, _to_v in self.by_field[field].get(issue_id, []):
            if pd.notna(created) and created > T:
                return from_v
        return final

    def changes_before(self, field: str, issue_id: int, T) -> int:
        return sum(1 for c, *_ in self.by_field[field].get(issue_id, []) if pd.notna(c) and c <= T)


def sprint_membership(issues: pd.DataFrame, sprints: pd.DataFrame, hist: History) -> dict[int, dict[int, pd.Timestamp]]:
    """sprint_id -> {issue_id: time the issue was added to the sprint}."""
    jira_to_sprint = defaultdict(list)
    for s in sprints.itertuples(index=False):
        jira_to_sprint[str(int(s.jira_id)) if pd.notna(s.jira_id) else ""].append((int(s.id), s.project))
    issue_project = issues["project"].to_dict()
    member: dict[int, dict[int, pd.Timestamp]] = defaultdict(dict)

    for issue_id, events in hist.by_field["sprint"].items():
        if issue_id not in issue_project:
            continue
        for created, from_v, to_v in events:
            added = _tokens(to_v) - _tokens(from_v)
            for tok in added:
                for sid, sproj in jira_to_sprint.get(tok, []):
                    if len(jira_to_sprint[tok]) > 1 and sproj != issue_project[issue_id]:
                        continue  # ambiguous Jira id across repositories
                    member[sid].setdefault(issue_id, created)
    # Issues whose final Sprint_ID has no change-log entry: added at creation.
    for iid, row in issues.iterrows():
        sid = row["sprint"]
        if pd.notna(sid) and iid not in member.get(int(sid), {}):
            member[int(sid)][iid] = row["created"]
    return member


def prerequisites(links: pd.DataFrame) -> dict[int, set[int]]:
    prereq: dict[int, set[int]] = defaultdict(set)
    lk = links[links["name"].astype(str).str.lower().str.strip().isin(BLOCKING_LINK_NAMES)]
    for r in lk.itertuples(index=False):
        if pd.isna(r.issue) or pd.isna(r.target):
            continue
        d = str(r.direction).lower()
        a, b = int(r.issue), int(r.target)
        if d.startswith("in"):      # issue "is blocked by" target
            prereq[a].add(b)
        elif d.startswith("out"):   # issue "blocks" target
            prereq[b].add(a)
    return prereq


def build(tables: dict[str, pd.DataFrame], fractions=SNAPSHOT_FRACTIONS, verbose=True) -> pd.DataFrame:
    issues = tables["issue"].drop_duplicates("id").set_index("id")
    sprints = tables["sprint"].dropna(subset=["start", "end"]).copy()
    sprints["days"] = (sprints["end"] - sprints["start"]).dt.total_seconds() / 86400
    sprints = sprints[(sprints["days"] >= 3) & (sprints["days"] <= MAX_SPRINT_DAYS)]
    hist = History(tables["change_log"])
    member = sprint_membership(issues, sprints, hist)
    prereq = prerequisites(tables["issue_link"])

    # Map change-log assignee values -> Issue.Assignee_ID where we can, for stable keys.
    value_to_id = {}
    for iid, evs in hist.by_field["assignee"].items():
        if evs and iid in issues.index and pd.notna(issues.at[iid, "assignee"]):
            value_to_id.setdefault(str(evs[-1][2]), int(issues.at[iid, "assignee"]))

    def assignee_key(iid, T):
        final = issues.at[iid, "assignee"]
        final_key = None if pd.isna(final) else int(final)
        v = hist.value_at("assignee", iid, T, final="__final__")
        if v == "__final__":
            return final_key
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in ("", "None", "nan"):
            return None
        return value_to_id.get(str(v), f"cl:{v}")

    rows = []
    n_sprints = 0
    for project, psprints in sprints.sort_values("start").groupby("project"):
        history = HistoryStats()
        finished: list[tuple] = []  # (end, sprint_id, outcomes)
        for s in psprints.itertuples(index=False):
            # flush sprints that ended before this one started
            still = []
            for end, _sid, outcomes in finished:
                if end <= s.start:
                    for key, late in outcomes:
                        history.record(key, late)
                else:
                    still.append((end, _sid, outcomes))
            finished = still

            sm = {i: t for i, t in member.get(int(s.id), {}).items() if i in issues.index}
            if len(sm) < MIN_SPRINT_ISSUES:
                continue
            n_sprints += 1
            end = s.end
            outcomes = []
            for f in fractions:
                T = s.start + (end - s.start) * f
                present = [i for i, added in sm.items() if pd.notna(added) and added <= T
                           and pd.notna(issues.at[i, "created"]) and issues.at[i, "created"] <= T]
                if not present:
                    continue
                keys, tasks = {}, {}
                for i in present:
                    res = issues.at[i, "resolved"]
                    done = pd.notna(res) and res <= T
                    k = assignee_key(i, T)
                    keys[i] = k
                    sp = _float(hist.value_at("points", i, T, issues.at[i, "story_points"]))
                    prio = JIRA_PRIORITY_RANK.get(str(issues.at[i, "priority"]).lower().strip(), 2)
                    desc = issues.at[i, "description"]
                    tasks[i] = TaskState(
                        id=i, title="", status="done" if done else "todo",
                        priority=RANK_TO_APP_PRIORITY[prio],
                        task_type="bug" if str(issues.at[i, "type"]).lower() == "bug" else "feature",
                        story_points=sp, assignee_id=k, created_at=issues.at[i, "created"].to_pydatetime(),
                        deadline=end.to_pydatetime(), start_date=s.start.to_pydatetime(),
                        completed_at=res.to_pydatetime() if done else None,
                        description_len=0 if pd.isna(desc) else len(str(desc)),
                        reassign_count=hist.changes_before("assignee", i, T),
                        blocked_by=sorted(prereq.get(i, ())),
                    )
                # prerequisite stubs outside the sprint (status as of T, no owner, no deadline)
                for i in list(tasks):
                    for b in tasks[i].blocked_by:
                        if b not in tasks and b in issues.index:
                            r = issues.at[b, "resolved"]
                            tasks[b] = TaskState(id=b, title="", status="done" if (pd.notna(r) and r <= T) else "todo",
                                                 priority="medium", task_type="feature", story_points=None,
                                                 assignee_id=None, created_at=T.to_pydatetime(), deadline=None)
                state = ProjectState(project_id=int(project), name="", now=T.to_pydatetime(),
                                     members={}, tasks=tasks)
                for i in present:
                    if tasks[i].is_done:
                        continue
                    res = issues.at[i, "resolved"]
                    late = int(pd.isna(res) or res > end)
                    feats = compute_features(state, tasks[i], history, exclude_self_from_history=False)
                    feats.update({"late": late, "issue_id": i, "sprint_id": int(s.id), "project_id": int(project),
                                  "snapshot_frac": f, "snapshot_time": T, "sprint_start": s.start})
                    rows.append(feats)
                    if f == 0.0:
                        outcomes.append((keys[i], bool(late)))
            finished.append((end, int(s.id), outcomes))
        if verbose:
            print(f"project {project}: {len(psprints)} sprints processed, rows so far {len(rows)}")

    df = pd.DataFrame(rows)
    if verbose and len(df):
        print(f"\n{n_sprints} usable sprints, {len(df)} snapshot rows, late rate {df['late'].mean():.3f}")
        print(df.groupby("snapshot_frac")["late"].agg(["count", "mean"]))
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=None, help="MySQL URL or directory of CSV exports (default: $TAWOS_SOURCE)")
    ap.add_argument("--out", default=str(ROOT / "ml" / "data" / "snapshots.csv.gz"))
    args = ap.parse_args()
    tables = load_tawos(args.source)
    df = build(tables)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df[FEATURE_NAMES + ["late", "issue_id", "sprint_id", "project_id", "snapshot_frac",
                        "snapshot_time", "sprint_start"]].to_csv(out, index=False)
    print(f"saved {len(df)} rows -> {out}")


if __name__ == "__main__":
    main()
