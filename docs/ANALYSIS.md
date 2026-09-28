# Dataset analysis

Seven candidate datasets from the project brief were evaluated. Kaggle and Zenodo metadata was inspected; items
marked **(verify)** should be confirmed once the files are downloaded.

| Dataset | What it is | Real? | Verdict |
|---|---|---|---|
| Zenodo 16911234 — HRIS Jira | epic-level records of one HRIS SaaS company, 2024, already feature-engineered; zip is 7.4 kB | real | Not primary: too small for train/valid/test, single company, likely after-the-fact aggregates (leakage). Related work only. |
| Kaggle — Project Management Risk Raw | static project attributes + risk label, tagged "beginner" | likely synthetic (verify) | Rejected: no timestamps/history; would learn the generator |
| Kaggle — Construction PM | construction schedule data | likely synthetic (verify) | Rejected: wrong domain |
| Kaggle — Employee Performance & Productivity | HR table (performance, overtime, satisfaction) (verify) | likely synthetic (verify) | Rejected: HR attrition, not project delivery |
| Kaggle — Workers' Performance Prediction | garment-factory team productivity (verify) | real | Rejected: manufacturing domain |
| Kaggle — Task Turtles vs Sprint Hares | person-level work-style data | likely synthetic (verify) | Rejected: no deadlines or task lifecycle |
| Kaggle — Skill-Based Task Assignment | task descriptions labelled with skills | unclear | Deferred: possible future skill-tagging feature |

**Selected: TAWOS** (Tawosi et al., MSR 2022): 458,232 issues from 39 open-source projects in 12 public Jira
repositories, with sprints, story points, change logs, issue links and UTC timestamps; Apache-2.0; anonymised.
**Backup:** Montgomery et al., Public Jira Dataset (MSR 2022).

**No dataset merging.** One training dataset; workload, flow and health analytics use the application's own data and
are rule-based — ML is used only where prediction is genuinely needed.

## Where our system overlaps with existing tools, and what it adds
Commercial tools (Jira, Asana, ClickUp, Monday.com, Microsoft Planner) increasingly ship AI features such as
summaries, writing help and some risk or workload views; check their current documentation before making any claim
in your report. This project does **not** claim these tools "cannot predict". What it contributes as a prototype:
1. an openly documented, reproducible delay model trained on public data with leakage controls and calibration;
2. per-prediction explanations and a documented health formula;
3. what-if simulation of recommended actions with the same model;
4. a tool-restricted assistant that cannot invent project facts;
5. an evaluation page that reports honest metrics against a baseline.
