# Foresight — Predictive Project Intelligence

> *AI Based Project Management and Team Productivity System* — final-year B.E. project prototype.

Most project tools tell you **what is happening**. Foresight also estimates **what is likely to happen next and why**:
it predicts which tasks will miss their deadline, explains each prediction in plain language, scores project health
with a documented formula, detects workload imbalance, and recommends concrete actions — simulating each action with
the same model before you apply it.

| | |
|---|---|
| **Delay prediction** | Calibrated probability that each open task misses its deadline, trained on real agile data (TAWOS) |
| **Explanations** | Per-task factors: *"assignee carries 24 other open points (typical 8)"* with their impact in % points |
| **What-if simulation** | Reassign a task or move a deadline → see risk and health change *before* saving |
| **Project health** | `100 − Σ documented penalties`, every penalty linked to the tasks/people that caused it |
| **Workload intelligence** | Open points vs capacity and team median; overloaded / under-used detection |
| **Recommendations** | Template-based, grounded in live data, each action pre-simulated; applied/dismissed is logged |
| **Assistant** | Local LLM (Ollama) restricted to 11 read-only tools; offline rule mode when no LLM runs |
| **Evaluation page** | Model card, comparison vs heuristic baseline, calibration curve, leave-project-out results |

## Architecture

```mermaid
flowchart LR
  subgraph Offline["Offline ML pipeline (ml/)"]
    T[(TAWOS MySQL dump)] --> A[audit_tawos.py] --> S[build_tawos_snapshots.py] --> TR[train.py]
  end
  F[[backend/app/core/features.py<br/>ONE feature implementation]]
  S -. uses .-> F
  TR --> M[(model.joblib + metrics.json)]
  subgraph Online["Application"]
    UI[React + TypeScript] -- REST/JWT --> API[FastAPI]
    API --> DB[(PostgreSQL / SQLite)]
    API --> ENG[Intelligence engine<br/>health · workload · recommendations · what-if]
    ENG -. uses .-> F
    ENG --> M
    API --> AS[Assistant: Ollama LLM + fixed tools<br/>or offline rules]
  end
```

The single most important design decision: **the same `features.py` computes features for training (from TAWOS
history) and for live predictions (from the app database)**, so the model never sees differently-defined numbers
in production.

## Data provenance (be explicit with judges)

| Data | Where | Used for |
|---|---|---|
| **TAWOS** (real, 458k Jira issues, 39 OSS projects, Apache-2.0) | you download it | training / validation / test of the delay model |
| **Synthetic demo model** | `backend/app/ml/demo_model.py` | only so the app runs before TAWOS is trained; UI shows a "synthetic" badge |
| **Synthetic demo project** ("Atlas Mobile Launch") | `backend/app/core/demo_data.py` | the live demo; *never* used for training or metrics |
| **Application data** | your database | live predictions, health, workload, analytics |

Kaggle datasets from the original brief were evaluated and **rejected** — see [docs/ANALYSIS.md](docs/ANALYSIS.md).

## Quick start (about 5 minutes)

Requirements: Python 3.11+, Node 18+. Optional: PostgreSQL 15+, [Ollama](https://ollama.com).

```bash
# 1) Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
python -m app.seed              # demo users + demo project (use --reset before each demo for fresh dates)
uvicorn app.main:app --reload   # http://localhost:8000/docs

# 2) Frontend (new terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Sign in with **priya@demo.foresight / demo1234** (manager). Other demo users: rahul, aisha, karan, meera, dev (same password).

**Optional local LLM** for the assistant (free):
```bash
ollama pull qwen2.5:7b-instruct     # or llama3.1:8b
ollama serve
```
Without Ollama the assistant still works in deterministic *offline* mode.

**Docker (PostgreSQL + backend + frontend):** `docker compose up --build` → http://localhost:5173

## Train the real model (TAWOS)

See [docs/ML.md](docs/ML.md) for the full method. Short version:

```bash
pip install sqlalchemy pymysql matplotlib
# restore the TAWOS dump into MySQL 8 (DOI 10.5522/04/21308124), then:
export TAWOS_SOURCE="mysql+pymysql://root:root@localhost:3306/tawos"
python ml/audit_tawos.py                 # STEP 1: audit + decision gate  -> ml/reports/audit.md
python ml/build_tawos_snapshots.py       # STEP 2: leakage-safe snapshots -> ml/data/snapshots.csv.gz
python ml/train.py                       # STEP 3: compare, calibrate, test -> backend/models/tawos/
```
Restart the backend: it picks up `models/tawos/model.joblib` automatically and the synthetic badge disappears.

## Tests

```bash
cd backend
pytest            # engine tests, API tests (auth, RBAC, what-if, cycles), ML pipeline on a fake TAWOS-shaped dataset
```

## Project structure

```
backend/
  app/core/        framework-free intelligence engine (state, features, health, workload, flow, recommendations, what-if)
  app/ml/          predictor + explainer, training/evaluation, synthetic demo model
  app/api/         FastAPI routers (auth, projects, tasks, intelligence, assistant)
  app/db/          SQLAlchemy models (9 tables) and session
  app/assistant.py tool-restricted assistant (Ollama or offline)
  tests/
ml/                TAWOS loader, audit, snapshot builder, training CLI, fake-data tests
frontend/src/      React + TypeScript UI (dashboard, board, team, assistant, model page, settings)
docs/              ANALYSIS · ML · DATABASE · API · DEMO · ROADMAP
```

## Documentation
- [docs/ANALYSIS.md](docs/ANALYSIS.md) — dataset comparison and why TAWOS
- [docs/ML.md](docs/ML.md) — problem formulation, leakage controls, evaluation, explainability
- [docs/DATABASE.md](docs/DATABASE.md) — schema, keys, indexes, constraints
- [docs/API.md](docs/API.md) — endpoints and security model
- [docs/DEMO.md](docs/DEMO.md) — 5-minute demo script
- [docs/ROADMAP.md](docs/ROADMAP.md) — milestones, status and definition of done

## Public capstone demo deployment

**The public demo is not deployed yet.** After Vercel assigns the frontend URL, replace this line with
`[Open the Foresight demo](https://<your-vercel-domain>)`.

The public database is intended to start with only the app-generated **Atlas Mobile Launch** synthetic demo project
and its demo users. Do not enter personal, private, or real project data. The shared demo account is mutable: visitors
can change the sample project, and changes are visible to everyone using that account. Demo credentials are
**priya@demo.foresight / demo1234** (manager); rahul, aisha, karan, meera, and dev use the same password.

The deployment files are `render.yaml` (Render API + PostgreSQL) and `frontend/vercel.json` (React SPA fallback).
The source repository must be available to Vercel and Render through a connected Git provider; this setup does not
publish or deploy the current folder.

### 1. Deploy the frontend once to get its public URL

1. In Vercel, select **Add New... → Project**, import the repository, and set **Root Directory** to `frontend`.
2. Keep the detected Vite settings: install `npm install`, build `npm run build`, output directory `dist`.
3. Do not add `VITE_API_URL` yet. Select **Deploy** and copy the assigned production URL (for example,
   `https://foresight-demo.vercel.app`). The UI can load at this point, but its API will not work until the next steps.

### 2. Deploy the API and database on Render

1. In Render, select **New + → Blueprint**, connect the same repository, and deploy the `render.yaml` Blueprint.
2. When prompted for `CORS_ORIGINS`, enter the exact Vercel origin copied above, with no trailing slash or path,
   such as `https://foresight-demo.vercel.app`. This is an environment value, not a committed URL.
3. The Blueprint creates a Docker web service and PostgreSQL database in Oregon. It generates `JWT_SECRET`
   automatically and links `DATABASE_URL` to the database's internal connection string; do not manually set or
   expose either value.
4. After the service is live, copy its `onrender.com` service URL. Check
   `https://<your-render-service>.onrender.com/api/health` for `{"status":"ok",...}`. The container seeds the one
   synthetic demo project on startup if it is missing.

### 3. Connect Vercel to the Render API

1. In Vercel, open the project **Settings → Environment Variables** and add `VITE_API_URL` for **Production**.
   Set its value to the Render service origin only, e.g. `https://foresight-api-xxxx.onrender.com` (no `/api` and no
   trailing slash).
2. Redeploy the latest production deployment so Vite embeds the new value. Confirm the app can sign in and load
   the demo project.
3. Replace the not-deployed notice near the top of this section with a link to the final Vercel URL.

If the Vercel domain changes, update Render's **CORS_ORIGINS** to the new exact origin and redeploy/restart the API.
For local development, leave `VITE_API_URL` unset; the frontend continues to call relative `/api` paths through the
Vite development proxy.

The free Render PostgreSQL plan is suitable for a short capstone demo, not long-term storage; check Render's current
free-database lifecycle and retention limits before relying on it.

## Honest limitations
- Until you train on TAWOS, predictions come from a **synthetic** model — say so in any demo.
- A model trained on open-source teams may not transfer perfectly to a student or company team (domain shift).
- TAWOS column names in `ml/tawos_io.py` must be verified against the dump (`audit_tawos.py` fails loudly if not).
- Health-score weights are expert-chosen, not learned; they are documented and easy to change.
