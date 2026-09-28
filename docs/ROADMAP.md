# Roadmap and milestones

| # | Milestone | Status | Definition of done |
|---|---|---|---|
| M0 | Analysis & design (datasets, formulation, architecture) | ✅ | docs/ANALYSIS.md, docs/ML.md, docs/DATABASE.md written |
| M1 | Core engine: features, health, workload, flow, recommendations, what-if | ✅ | `tests/test_engine.py` passes |
| M2 | ML pipeline: audit, snapshots, training, calibration, explainer, demo model | ✅ code · ⏳ real run | `ml/tests/test_pipeline.py` passes; **you:** run on TAWOS, commit `ml/reports/audit.md` + metrics |
| M3 | Backend: auth, RBAC, CRUD, dependencies, audit log, intelligence endpoints, seed | ✅ code | `tests/test_api.py` passes on your machine |
| M4 | Assistant: tool-restricted LLM + offline mode | ✅ | answers cite task ids; off-topic questions refused |
| M5 | Frontend: dashboard, board (drag & drop), task drawer, what-if, team, assistant, model page, settings | ✅ code | `npm run build` succeeds; demo script runs end to end |
| M6 | Real model + report | ⏳ you | TAWOS model beats the heuristic baseline on test PR-AUC; plots in report |
| M7 | Evaluation & polish | ⏳ you | usability test with 3–5 classmates (SUS questionnaire), API latency (p95) measured, screenshots, video |

## Suggested evaluation plan (M7)
- **ML:** test PR-AUC / ROC-AUC / Brier vs heuristic baseline; calibration curve; leave-project-out.
- **Functionality:** pytest suite (engine, API, pipeline) — include the count in your report.
- **Recommendations:** acceptance rate from `recommendation_feedback`; average drop in predicted risk for applied reassignments.
- **Usability:** System Usability Scale with 5 users performing 3 tasks (find riskiest task, rebalance, ask assistant).
- **Performance:** time `/overview` for 50, 200, 1000 tasks (seed more tasks; simple script with httpx).

## Possible extensions (only if time remains)
- Skill-aware reassignment (skills on project_members + the skill-assignment dataset for tagging).
- Background re-prediction job and notifications.
- Alembic migrations, refresh tokens, rate limiting.
