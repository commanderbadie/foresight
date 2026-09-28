"""AI project assistant.

Design (anti-hallucination by construction):
  * The LLM never sees the database and never writes SQL.
  * It can only call a FIXED set of read-only tools below; each tool returns
    facts computed from the live project state, the model and the health engine.
  * The system prompt requires every fact to come from tool output and to cite
    task ids; if the tools do not contain the answer, it must say so.
  * If no local LLM is running (Ollama), a deterministic offline mode maps the
    question to the same tools and answers with templates. The UI shows which
    mode answered.

LLM: any tool-calling model served by Ollama (free, local), e.g. qwen2.5:7b-instruct
or llama3.1:8b. No paid API is required.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from .core.flow import compute_flow
from .core.intelligence import Analysis
from .core.state import ProjectState, as_aware, days_between


@dataclass
class Context:
    state: ProjectState
    analysis: Analysis
    recommendations: list[dict]


def _task_brief(ctx: Context, tid: int) -> dict:
    t = ctx.state.tasks[tid]
    r = ctx.analysis.risks.get(tid)
    return {
        "id": t.id, "title": t.title, "status": t.status, "priority": t.priority,
        "story_points": t.story_points, "assignee": ctx.state.member_name(t.assignee_id),
        "deadline": as_aware(t.deadline).isoformat(timespec="minutes") if t.deadline else None,
        "days_left": round(days_between(ctx.state.now, t.deadline), 1) if t.deadline else None,
        "delay_probability": round(r.probability, 2) if r else None,
        "risk_level": r.level if r else None,
        "risk_factors": [f.label for f in r.factors[:3]] if r else [],
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_project_summary(ctx: Context) -> dict:
    s, h = ctx.state, ctx.analysis.health
    return {
        "project": s.name, "today": as_aware(s.now).date().isoformat(),
        "end_date": as_aware(s.end_date).date().isoformat() if s.end_date else None,
        "open_tasks": len(s.open_tasks()), "done_tasks": len(s.done_tasks()),
        "health_score": h.score, "health_status": h.status, "completion_pct": h.completion_pct,
        "members": [m.name for m in s.members.values()],
    }


def tool_health(ctx: Context) -> dict:
    h = ctx.analysis.health.as_dict()
    return {"score": h["score"], "status": h["status"],
            "reasons": [{"reason": s["label"], "penalty": s["penalty"], "task_ids": s["task_ids"]} for s in h["signals"]],
            "method": "score = 100 - sum of documented penalties; >=75 on track, 50-74 at risk, <50 critical"}


def tool_top_risks(ctx: Context, limit: int = 5) -> dict:
    ranked = sorted(ctx.analysis.risks.values(), key=lambda r: -r.probability)
    return {"tasks": [_task_brief(ctx, r.task_id) for r in ranked[: max(1, min(int(limit), 15))]]}


def tool_workload(ctx: Context) -> dict:
    w = ctx.analysis.workload
    return {"team_median_open_points": w.team_median_points, "unassigned_open_tasks": w.unassigned_open,
            "members": [{"name": m.name, "open_tasks": m.open_tasks, "open_points": m.open_points,
                         "capacity_points": m.capacity_points, "status": m.status, "reasons": m.reasons,
                         "overdue": m.overdue} for m in w.members]}


def tool_overdue(ctx: Context) -> dict:
    return {"tasks": [_task_brief(ctx, t.id) for t in ctx.state.open_tasks() if ctx.state.is_overdue(t)]}


def tool_upcoming(ctx: Context, days: int = 7) -> dict:
    now = ctx.state.now
    ts = [t for t in ctx.state.open_tasks() if t.deadline and 0 <= days_between(now, t.deadline) <= float(days)]
    ts.sort(key=lambda t: t.deadline)
    return {"window_days": days, "tasks": [_task_brief(ctx, t.id) for t in ts]}


def tool_blockers(ctx: Context) -> dict:
    out = []
    for t in ctx.state.open_tasks():
        deps = ctx.state.transitive_dependents(t.id)
        if deps:
            out.append({**_task_brief(ctx, t.id), "blocks": [{"id": d.id, "title": d.title} for d in deps]})
    out.sort(key=lambda x: -len(x["blocks"]))
    return {"blocking_tasks": out[:8]}


def tool_task_details(ctx: Context, task: str = "") -> dict:
    q = str(task).strip().lstrip("#")
    match = None
    if q.isdigit() and int(q) in ctx.state.tasks:
        match = ctx.state.tasks[int(q)]
    else:
        cands = [t for t in ctx.state.tasks.values() if q and q.lower() in t.title.lower()]
        match = cands[0] if cands else None
    if match is None:
        return {"error": f"no task matching '{task}'"}
    d = _task_brief(ctx, match.id)
    d["blocked_by"] = [{"id": b.id, "title": b.title, "status": b.status} for b in ctx.state.open_blockers(match)]
    d["blocks"] = [{"id": x.id, "title": x.title} for x in ctx.state.transitive_dependents(match.id)]
    return d


def tool_member_tasks(ctx: Context, name: str = "") -> dict:
    m = next((m for m in ctx.state.members.values() if name and name.lower() in m.name.lower()), None)
    if m is None:
        return {"error": f"no member matching '{name}'", "members": [x.name for x in ctx.state.members.values()]}
    return {"member": m.name, "tasks": [_task_brief(ctx, t.id) for t in ctx.state.tasks_of(m.id)]}


def tool_recommendations(ctx: Context) -> dict:
    return {"recommendations": [{"title": r["title"], "detail": r["detail"], "severity": r["severity"],
                                 "task_ids": r["task_ids"]} for r in ctx.recommendations]}


def tool_flow(ctx: Context) -> dict:
    return compute_flow(ctx.state)


TOOLS: dict[str, tuple[Callable[..., dict], str, dict]] = {
    "project_summary": (tool_project_summary, "Basic facts: name, dates, task counts, health, members.", {}),
    "health": (tool_health, "Project health score, status and the reasons behind it.", {}),
    "top_risks": (tool_top_risks, "Open tasks ranked by predicted delay probability, with risk factors.",
                  {"limit": {"type": "integer", "description": "how many tasks (1-15)"}}),
    "workload": (tool_workload, "Open points per member, capacity, overloaded/underutilised flags.", {}),
    "overdue_tasks": (tool_overdue, "Open tasks whose deadline has passed.", {}),
    "upcoming_deadlines": (tool_upcoming, "Open tasks due within N days.",
                           {"days": {"type": "integer", "description": "window in days"}}),
    "blocking_tasks": (tool_blockers, "Open tasks that block other tasks (dependency bottlenecks).", {}),
    "task_details": (tool_task_details, "Details, risk and dependencies of one task by id or title words.",
                     {"task": {"type": "string", "description": "task id like 42 or words from its title"}}),
    "member_tasks": (tool_member_tasks, "Open tasks of one team member.",
                     {"name": {"type": "string", "description": "member name"}}),
    "recommendations": (tool_recommendations, "Current data-driven recommendations for the manager.", {}),
    "flow_metrics": (tool_flow, "Throughput, cycle time, deadline adherence over recent weeks.", {}),
}


def run_tool(ctx: Context, name: str, args: dict | None) -> dict:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    fn, _, params = TOOLS[name]
    clean = {k: v for k, v in (args or {}).items() if k in params}
    try:
        return fn(ctx, **clean)
    except Exception as exc:  # never crash the chat because of a bad argument
        return {"error": str(exc)}


def ollama_tool_specs() -> list[dict]:
    return [{"type": "function", "function": {
        "name": n, "description": d,
        "parameters": {"type": "object", "properties": p, "required": []}}} for n, (_, d, p) in TOOLS.items()]


SYSTEM_PROMPT = """You are Foresight, an assistant for a project manager.
Rules:
1. Use ONLY facts returned by the tools. Never invent tasks, people, dates or numbers.
2. Call the tools you need before answering. Prefer one or two tools.
3. Cite tasks as #id. Give probabilities as percentages.
4. If the tools do not contain the answer, say exactly what information is missing.
5. Be brief: at most 6 short bullet points or 5 sentences. Lead with the answer.
6. Delay probabilities come from an ML model; say "predicted" when you use them."""


@dataclass
class Answer:
    answer: str
    mode: str
    tools_used: list[dict] = field(default_factory=list)
    task_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"answer": self.answer, "mode": self.mode, "tools_used": self.tools_used,
                "task_ids": sorted(set(self.task_ids))}


def _collect_ids(obj: Any, out: list[int]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("id", "task_ids") and isinstance(v, int):
                out.append(v)
            elif k == "task_ids" and isinstance(v, list):
                out.extend(i for i in v if isinstance(i, int))
            else:
                _collect_ids(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_ids(v, out)


def ask_llm(ctx: Context, question: str, url: str, model: str, timeout: float) -> Answer:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    used: list[dict] = []
    ids: list[int] = []
    with httpx.Client(timeout=timeout) as client:
        for _ in range(4):
            resp = client.post(f"{url.rstrip('/')}/api/chat", json={
                "model": model, "messages": messages, "tools": ollama_tool_specs(), "stream": False,
                "options": {"temperature": 0.1}})
            resp.raise_for_status()
            msg = resp.json().get("message", {})
            calls = msg.get("tool_calls") or []
            if not calls:
                text = (msg.get("content") or "").strip()
                # Guard: every #id mentioned must exist in the project.
                bad = [int(x) for x in re.findall(r"#(\d+)", text) if int(x) not in ctx.state.tasks]
                if bad:
                    text += f"\n\n⚠️ Note: {', '.join('#' + str(b) for b in bad)} is not a task in this project."
                if not used:
                    text += "\n\n(Answered without consulting project data - treat with caution.)"
                return Answer(text, f"llm:{model}", used, ids)
            messages.append(msg)
            for c in calls:
                fn = c.get("function", {})
                name, args = fn.get("name", ""), fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result = run_tool(ctx, name, args)
                used.append({"tool": name, "args": args})
                _collect_ids(result, ids)
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, default=str)})
    return Answer("I could not complete the analysis within the tool-call limit. Try a more specific question.",
                  f"llm:{model}", used, ids)


# ---------------------------------------------------------------------------
# Offline (no LLM) mode: deterministic intent routing + templates
# ---------------------------------------------------------------------------

def _pct(p):
    return f"{p * 100:.0f}%" if p is not None else "n/a"


def _fmt_task(t: dict) -> str:
    extra = f", predicted delay {_pct(t['delay_probability'])}" if t.get("delay_probability") is not None and t.get("risk_level") != "overdue" else ""
    due = ""
    if t.get("days_left") is not None:
        due = f", overdue by {-t['days_left']:.1f} d" if t["days_left"] < 0 else f", due in {t['days_left']:.1f} d"
    return f"#{t['id']} {t['title']} ({t['assignee']}{due}{extra})"


def ask_offline(ctx: Context, question: str) -> Answer:
    q = question.lower()
    used, ids = [], []

    def call(_tool, **args):
        r = run_tool(ctx, _tool, args)
        used.append({"tool": _tool, "args": args})
        _collect_ids(r, ids)
        return r

    m = re.search(r"#(\d+)", q)
    if m or "task " in q and any(w in q for w in ("why", "detail", "about", "status of")):
        r = call("task_details", task=m.group(1) if m else q.split("task", 1)[1].strip(" ?"))
        if "error" in r:
            return Answer(f"I couldn't find that task ({r['error']}).", "offline", used, ids)
        lines = [f"**#{r['id']} {r['title']}** — {r['status']}, {r['priority']} priority, owner {r['assignee']}."]
        if r.get("delay_probability") is not None:
            lines.append(f"Predicted delay: **{_pct(r['delay_probability'])}** ({r['risk_level']}).")
        if r["risk_factors"]:
            lines.append("Main factors: " + "; ".join(r["risk_factors"]) + ".")
        if r["blocked_by"]:
            lines.append("Waiting on: " + ", ".join(f"#{b['id']} {b['title']}" for b in r["blocked_by"]) + ".")
        if r["blocks"]:
            lines.append(f"It blocks {len(r['blocks'])} task(s): " + ", ".join(f"#{b['id']}" for b in r["blocks"]) + ".")
        return Answer("\n".join(lines), "offline", used, ids)

    if any(w in q for w in ("overload", "workload", "busy", "capacity", "who has", "free", "underutil")):
        r = call("workload")
        over = [x for x in r["members"] if x["status"] == "overloaded"]
        under = [x for x in r["members"] if x["status"] == "underutilised"]
        lines = []
        if over:
            lines += [f"- **{x['name']}** is overloaded: {'; '.join(x['reasons'])}." for x in over]
        else:
            lines.append("- Nobody is overloaded right now.")
        if under:
            lines += [f"- {x['name']} has spare capacity ({x['open_points']:g} open points)." for x in under]
        lines.append(f"- Team median: {r['team_median_open_points']:g} open points per person.")
        return Answer("\n".join(lines), "offline", used, ids)

    if any(w in q for w in ("health", "at risk", "why is", "status of the project", "how is the project")):
        r = call("health")
        lines = [f"Health is **{r['score']:g}/100 ({r['status'].replace('_', ' ')})**."]
        lines += [f"- {x['reason']} (−{x['penalty']:g})" for x in r["reasons"][:5]] or ["- No warning signals."]
        return Answer("\n".join(lines), "offline", used, ids)

    if "overdue" in q or "late" in q and "likely" not in q:
        r = call("overdue_tasks")
        if not r["tasks"]:
            return Answer("No open task is overdue.", "offline", used, ids)
        return Answer("Overdue tasks:\n" + "\n".join("- " + _fmt_task(t) for t in r["tasks"]), "offline", used, ids)

    if any(w in q for w in ("block", "depend", "bottleneck")):
        r = call("blocking_tasks")
        if not r["blocking_tasks"]:
            return Answer("No open task is currently blocking another.", "offline", used, ids)
        return Answer("Biggest bottlenecks:\n" + "\n".join(
            f"- {_fmt_task(t)} → blocks {len(t['blocks'])}" for t in r["blocking_tasks"][:5]), "offline", used, ids)

    if any(w in q for w in ("deadline", "due", "this week", "upcoming", "today", "tomorrow")):
        days = 1 if "today" in q else 2 if "tomorrow" in q else 7
        r = call("upcoming_deadlines", days=days)
        if not r["tasks"]:
            return Answer(f"Nothing is due in the next {days} day(s).", "offline", used, ids)
        return Answer(f"Due in the next {days} day(s):\n" + "\n".join("- " + _fmt_task(t) for t in r["tasks"]),
                      "offline", used, ids)

    if any(w in q for w in ("throughput", "cycle", "velocity", "productiv", "adherence", "trend")):
        r = call("flow_metrics")
        return Answer(
            f"- Deadline adherence: {r['deadline_adherence_pct']}%\n- Median cycle time: {r['median_cycle_time_days']} days\n"
            f"- Completed in the last week: {r['weekly'][-1]['completed']} tasks\n- Work in progress: {r['wip']}",
            "offline", used, ids)

    if any(w in q for w in ("first", "priorit", "focus", "should", "address", "recommend", "what to do", "next")):
        r = call("recommendations")
        if not r["recommendations"]:
            return Answer("No urgent actions right now.", "offline", used, ids)
        return Answer("Address these first:\n" + "\n".join(
            f"{i}. **{x['title']}** — {x['detail']}" for i, x in enumerate(r["recommendations"][:4], 1)),
            "offline", used, ids)

    if any(w in q for w in ("risk", "likely", "delay", "slip")):
        r = call("top_risks", limit=5)
        return Answer("Tasks most likely to be delayed (model prediction):\n" + "\n".join(
            "- " + _fmt_task(t) + (f" — {t['risk_factors'][0]}" if t["risk_factors"] else "")
            for t in r["tasks"]), "offline", used, ids)

    for mem in ctx.state.members.values():
        first = mem.name.split()[0].lower()
        if first in q:
            r = call("member_tasks", name=first)
            return Answer(f"{r['member']} has {len(r['tasks'])} open task(s):\n" + "\n".join(
                "- " + _fmt_task(t) for t in r["tasks"]), "offline", used, ids)

    return Answer(
        "I can only answer from this project's data, and I couldn't map that question to it. Try: "
        "“why is the project at risk?”, “who is overloaded?”, “which tasks are likely to be delayed?”, "
        "“what should I address first?”, “what is due this week?” or “tell me about #12”.",
        "offline", used, ids)


def ask(ctx: Context, question: str, url: str, model: str, timeout: float) -> Answer:
    try:
        return ask_llm(ctx, question, url, model, timeout)
    except (httpx.HTTPError, ValueError, KeyError):
        return ask_offline(ctx, question)
