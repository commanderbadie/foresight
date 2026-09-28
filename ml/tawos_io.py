"""Loading the TAWOS dataset (MySQL dump or CSV exports) into pandas.

TAWOS: Tawosi, Moussa, Sarro. "A Versatile Dataset of Agile Open Source
Software Projects", MSR 2022. DOI 10.5522/04/21308124. Apache-2.0.

!!! VERIFY BEFORE TRAINING !!!
The column names below follow the TAWOS paper/README as closely as we could
without the dump in hand. Run `python ml/audit_tawos.py` first: it prints the
real columns of every table and fails loudly if something in SCHEMA is missing.
Fix SCHEMA here (only here) if names differ.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

SCHEMA = {
    "issue": {
        "table": "Issue",
        "id": "ID",
        "key": "Issue_Key",
        "title": "Title",
        "description": "Description_Text",
        "type": "Type",
        "priority": "Priority",
        "created": "Creation_Date",
        "resolved": "Resolution_Date",
        "story_points": "Story_Point",
        "assignee": "Assignee_ID",
        "project": "Project_ID",
        "sprint": "Sprint_ID",
    },
    "sprint": {
        "table": "Sprint",
        "id": "ID",
        "jira_id": "Jira_ID",
        "name": "Name",
        "start": "Start_Date",
        "end": "End_Date",
        "complete": "Complete_Date",
        "project": "Project_ID",
    },
    "change_log": {
        "table": "Change_Log",
        "issue": "Issue_ID",
        "field": "Field",
        "from_value": "From_Value",
        "to_value": "To_Value",
        "from_string": "From_String",
        "to_string": "To_String",
        "created": "Creation_Date",
    },
    "issue_link": {
        "table": "Issue_Link",
        "issue": "Issue_ID",
        "target": "Target_Issue_ID",
        "name": "Name",
        "direction": "Direction",
    },
}

# Change-log field names (lower-cased) that carry the history we need.
SPRINT_FIELDS = {"sprint"}
ASSIGNEE_FIELDS = {"assignee"}
STORY_POINT_FIELDS = {"story points", "story point estimate", "story_points"}
# Link names that express "X cannot finish before Y".
BLOCKING_LINK_NAMES = {"blocker", "blocks", "dependency", "depends", "depend", "gantt dependency"}


def _read_table(source: str, table: str) -> pd.DataFrame:
    """source = SQLAlchemy URL (mysql+pymysql://...) or a directory of <table>.csv files."""
    if "://" in source:
        from sqlalchemy import create_engine  # imported lazily: only needed for MySQL

        engine = create_engine(source)
        return pd.read_sql_table(table, engine)
    path = Path(source) / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found (export the '{table}' table to CSV, or pass a MySQL URL)")
    return pd.read_csv(path, low_memory=False)


def load_tawos(source: str | None = None, validate: bool = True) -> dict[str, pd.DataFrame]:
    source = source or os.environ.get("TAWOS_SOURCE", "mysql+pymysql://root:root@localhost:3306/tawos")
    tables = {}
    for key, spec in SCHEMA.items():
        df = _read_table(source, spec["table"])
        if validate:
            missing = [c for k, c in spec.items() if k != "table" and c not in df.columns]
            if missing:
                raise KeyError(
                    f"Table {spec['table']} is missing columns {missing}. Real columns: {list(df.columns)}. "
                    f"Update SCHEMA in ml/tawos_io.py."
                )
        rename = {c: k for k, c in spec.items() if k != "table"}
        tables[key] = df.rename(columns=rename)[list(rename.values())]
    for key, cols in (("issue", ["created", "resolved"]), ("sprint", ["start", "end", "complete"]),
                      ("change_log", ["created"])):
        for c in cols:
            tables[key][c] = pd.to_datetime(tables[key][c], errors="coerce", utc=True)
    return tables
