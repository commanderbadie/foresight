from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..assistant import Context, ask
from ..config import get_settings
from ..db.session import get_db
from ..deps import ProjectAccess, get_project_access
from ..schemas import AskIn
from ..services import run_analysis

router = APIRouter(tags=["assistant"])


@router.post("/api/projects/{project_id}/assistant")
async def ask_assistant(body: AskIn, acc: ProjectAccess = Depends(get_project_access), db: Session = Depends(get_db)):
    state, analysis, recs = run_analysis(db, acc.project, persist=False)
    s = get_settings()
    answer = await run_in_threadpool(ask, Context(state, analysis, recs), body.question,
                                     s.ollama_url, s.ollama_model, s.llm_timeout_seconds)
    return answer.as_dict()
