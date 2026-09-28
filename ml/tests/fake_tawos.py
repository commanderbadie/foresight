"""Generate a tiny FAKE dataset with the TAWOS table layout.

Only for testing the pipeline code (tests/test_pipeline.py). It is random data,
never use it for results.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def make_fake_tawos(out_dir: Path, n_projects: int = 3, sprints_per_project: int = 30, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    issues, sprints, changes, links = [], [], [], []
    iid, sid, cid = 1, 1, 1
    base = datetime(2019, 1, 1, tzinfo=timezone.utc)
    for proj in range(1, n_projects + 1):
        users = list(range(proj * 100, proj * 100 + 6))
        load = {u: rng.uniform(0.1, 0.6) for u in users}
        prev_open = []
        for k in range(sprints_per_project):
            start = base + timedelta(days=14 * k + proj)
            end = start + timedelta(days=14)
            jira_sid = 1000 * proj + k
            sprints.append({"ID": sid, "Jira_ID": jira_sid, "Name": f"P{proj} Sprint {k}", "Start_Date": start,
                            "End_Date": end, "Complete_Date": end + timedelta(hours=3), "Project_ID": proj,
                            "JIRA_Board_ID": proj, "State": "closed"})
            carried = prev_open
            prev_open = []
            new = []
            for _ in range(int(rng.integers(6, 15))):
                u = int(rng.choice(users))
                sp = float(rng.choice([1, 2, 3, 5, 8]))
                created = start - timedelta(days=float(rng.uniform(0, 10)))
                p_late = min(0.9, load[u] + 0.04 * sp)
                late = rng.random() < p_late
                resolved = end + timedelta(days=float(rng.uniform(1, 12))) if late else start + timedelta(days=float(rng.uniform(1, 13)))
                issues.append({"ID": iid, "Issue_Key": f"P{proj}-{iid}", "Title": "t", "Description_Text": "x" * int(rng.integers(0, 800)),
                               "Type": rng.choice(["Story", "Bug", "Task"]), "Priority": rng.choice(["Minor", "Major", "Critical"]),
                               "Creation_Date": created, "Resolution_Date": resolved, "Story_Point": sp,
                               "Assignee_ID": u, "Project_ID": proj, "Sprint_ID": sid})
                changes.append({"ID": cid, "Issue_ID": iid, "Field": "Sprint", "From_Value": "", "To_Value": str(jira_sid),
                                "From_String": "", "To_String": f"P{proj} Sprint {k}", "Creation_Date": start - timedelta(hours=2)})
                cid += 1
                if rng.random() < 0.15:  # reassignment mid-sprint
                    changes.append({"ID": cid, "Issue_ID": iid, "Field": "assignee", "From_Value": f"user{u}",
                                    "To_Value": f"user{int(rng.choice(users))}", "From_String": "", "To_String": "",
                                    "Creation_Date": start + timedelta(days=3)})
                    cid += 1
                if new and rng.random() < 0.2:
                    links.append({"ID": len(links) + 1, "Issue_ID": iid, "Target_Issue_ID": int(rng.choice(new)),
                                  "Name": "Blocker", "Direction": "Inward"})
                if late:
                    prev_open.append((iid, jira_sid))
                new.append(iid)
                iid += 1
            # carried-over issues move into this sprint (spillover) - Sprint_ID ends as the LAST sprint
            for (cid_issue, old_sid) in carried:
                changes.append({"ID": cid, "Issue_ID": cid_issue, "Field": "Sprint", "From_Value": str(old_sid),
                                "To_Value": f"{old_sid},{jira_sid}", "From_String": "", "To_String": "",
                                "Creation_Date": start + timedelta(hours=1)})
                cid += 1
                for row in issues:
                    if row["ID"] == cid_issue:
                        row["Sprint_ID"] = sid
            sid += 1
    pd.DataFrame(issues).to_csv(out_dir / "Issue.csv", index=False)
    pd.DataFrame(sprints).to_csv(out_dir / "Sprint.csv", index=False)
    pd.DataFrame(changes).to_csv(out_dir / "Change_Log.csv", index=False)
    pd.DataFrame(links).to_csv(out_dir / "Issue_Link.csv", index=False)
    return out_dir


if __name__ == "__main__":
    print(make_fake_tawos(Path(__file__).parent / "fake_tawos"))
