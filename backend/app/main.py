"""Foresight API - predictive project intelligence.

Run:  uvicorn app.main:app --reload     (from the backend/ folder)
Docs: http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import assistant, auth, intelligence, projects, tasks
from .config import get_settings
from .db import models  # noqa: F401  (register tables)
from .db.session import Base, engine
from .services import predictor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # For a student project `create_all` is enough; use Alembic migrations for schema changes in production.
    Base.metadata.create_all(engine)
    p = predictor()  # load (or build) the model once at startup
    logging.getLogger("foresight").info("Model: %s (%s)", p.version, p.card.get("data_source"))
    yield


app = FastAPI(title="Foresight API", version="1.0.0", lifespan=lifespan,
              description="Predictive project intelligence: delay risk, explainable health, workload and recommendations.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, projects.router, tasks.router, intelligence.router, assistant.router):
    app.include_router(r)


@app.get("/api/health", tags=["meta"])
def health():
    p = predictor()
    return {"status": "ok", "model": p.version, "data_source": p.card.get("data_source")}
