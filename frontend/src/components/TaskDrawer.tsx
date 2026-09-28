import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import { useProject } from "../pages/ProjectLayout";
import type { Status, Task } from "../types";
import WhatIfPreview from "./WhatIfPreview";
import {
  Confirm, ErrorState, Loading, PriorityTag, RiskBadge, STATUS_LABEL, fmtDateTime, fromLocalInput, pct, relDays,
  toLocalInput, useAsync,
} from "./ui";

export default function TaskDrawer({ taskId, onClose }: { taskId: number; onClose: () => void }) {
  const { pid, members, bump, toast, isManager, version } = useProject();
  const task = useAsync(() => api.task(taskId), [taskId, version]);
  const risk = useAsync(() => api.taskRisk(taskId), [taskId, version]);
  const updates = useAsync(() => api.updates(taskId), [taskId, version]);
  const allTasks = useAsync(() => api.tasks(pid), [pid]);
  const [whatIfAssignee, setWhatIfAssignee] = useState<string>("");
  const [comment, setComment] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [depPick, setDepPick] = useState("");

  async function patch(body: Record<string, unknown>, msg = "Saved") {
    try {
      await api.updateTask(taskId, body);
      toast(msg);
      bump();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed");
    }
  }

  if (task.loading && !task.data) return <Shell onClose={onClose}><Loading /></Shell>;
  if (task.error) return <Shell onClose={onClose}><ErrorState message={task.error} onRetry={task.reload} /></Shell>;
  const t = task.data as Task;
  const r = risk.data?.risk ?? t.risk;
  const maxImpact = Math.max(0.01, ...(r?.factors ?? []).map((f: any) => Math.abs(f.impact)), ...(r?.mitigating ?? []).map((f: any) => Math.abs(f.impact)));

  return (
    <Shell onClose={onClose} title={`#${t.id}`}>
      <div>
        <div className="row wrap" style={{ marginBottom: 6 }}>
          <RiskBadge risk={r} />
          <PriorityTag p={t.priority} />
          <span className="badge">{t.task_type}</span>
          {t.story_points != null && <span className="badge">{t.story_points} pts</span>}
        </div>
        <h2 style={{ fontSize: 19 }}>{t.title}</h2>
        {t.description && <p className="small" style={{ color: "var(--ink-2)", whiteSpace: "pre-wrap" }}>{t.description.slice(0, 600)}</p>}
      </div>

      <div className="form-grid">
        <label className="field">Status
          <select className="input" value={t.status} onChange={(e) => patch({ status: e.target.value as Status }, "Status updated")}>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field">Assignee
          <select className="input" value={t.assignee_id ?? ""} onChange={(e) =>
            patch(e.target.value ? { assignee_id: Number(e.target.value) } : { unassign: true }, "Reassigned")}>
            <option value="">Unassigned</option>
            {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
          </select>
        </label>
        <label className="field">Deadline <span className="muted">({relDays(t.deadline)})</span>
          <input className="input" type="datetime-local" defaultValue={toLocalInput(t.deadline)} key={t.deadline ?? "none"}
            onBlur={(e) => { const v = fromLocalInput(e.target.value); if (v !== t.deadline) patch({ deadline: v }, "Deadline updated"); }} />
        </label>
        <label className="field">Estimate
          <select className="input" value={t.story_points ?? ""} onChange={(e) => patch({ story_points: e.target.value === "" ? null : Number(e.target.value) })}>
            <option value="">Not estimated</option>
            {[1, 2, 3, 5, 8, 13, 21].map((n) => <option key={n} value={n}>{n} pts</option>)}
          </select>
        </label>
      </div>

      {/* Explanation */}
      {r && r.level !== "overdue" && (
        <section className="card card-pad">
          <div className="row between">
            <h3>Why {pct(r.probability)} delay risk?</h3>
            <span className="small muted tip" data-tip="Each bar = how much the predicted probability changes if this factor were at its typical value (training median). Red pushes risk up, green pulls it down.">method</span>
          </div>
          {r.factors.length === 0 && r.mitigating.length === 0 && <div className="small muted">No single factor stands out; this task looks typical.</div>}
          {r.factors.map((f: any) => (
            <div key={f.feature} className="factor">
              <span className="small">{f.label}</span>
              <div className="row" style={{ gap: 6 }}>
                <div className="impact" style={{ width: `${(Math.abs(f.impact) / maxImpact) * 90}px` }} />
                <span className="small num">+{(f.impact * 100).toFixed(0)}</span>
              </div>
            </div>
          ))}
          {r.mitigating.map((f: any) => (
            <div key={f.feature} className="factor">
              <span className="small">{f.label}</span>
              <div className="row" style={{ gap: 6 }}>
                <div className="impact down" style={{ width: `${(Math.abs(f.impact) / maxImpact) * 90}px` }} />
                <span className="small num">{(f.impact * 100).toFixed(0)}</span>
              </div>
            </div>
          ))}
          {risk.data?.model?.is_synthetic && <div className="small" style={{ color: "var(--medium)", marginTop: 6 }}>Demo model trained on synthetic data.</div>}
        </section>
      )}
      {r?.level === "overdue" && (
        <div className="banner" style={{ background: "var(--overdue-soft)", color: "var(--overdue)" }}>
          This task is already past its deadline, so there is nothing to predict. Agree a new date or re-scope it.
        </div>
      )}

      {/* What-if */}
      {t.status !== "done" && t.deadline && (
        <section className="card card-pad stack">
          <h3>What if…</h3>
          <label className="field">…this task were assigned to
            <select className="input" value={whatIfAssignee} onChange={(e) => setWhatIfAssignee(e.target.value)}>
              <option value="">choose a teammate</option>
              {members.filter((m) => m.user_id !== t.assignee_id).map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
            </select>
          </label>
          {whatIfAssignee && (
            <>
              <WhatIfPreview pid={pid} taskId={t.id} assigneeId={Number(whatIfAssignee)} />
              <button className="btn primary" onClick={() => { patch({ assignee_id: Number(whatIfAssignee) }, "Reassigned"); setWhatIfAssignee(""); }}>
                Apply this reassignment
              </button>
            </>
          )}
        </section>
      )}

      {/* Dependencies */}
      <section className="stack" style={{ gap: 6 }}>
        <h3>Dependencies</h3>
        {(risk.data?.blocked_by ?? []).length === 0 && <div className="small muted">Not waiting on anything.</div>}
        {(risk.data?.blocked_by ?? []).map((b: any) => (
          <div key={b.id} className="row between small">
            <span>Waits for <strong>#{b.id}</strong> {b.title} <span className="muted">({b.status.replace("_", " ")})</span></span>
            <button className="btn ghost sm" onClick={async () => { await api.removeDependency(t.id, b.id); bump(); }}>remove</button>
          </div>
        ))}
        {(risk.data?.blocks ?? []).length > 0 && (
          <div className="small">Blocks {risk.data.blocks.length} task(s): {risk.data.blocks.map((b: any) => `#${b.id}`).join(", ")}</div>
        )}
        <div className="row">
          <select className="input" value={depPick} onChange={(e) => setDepPick(e.target.value)}>
            <option value="">Add prerequisite…</option>
            {(allTasks.data || []).filter((x) => x.id !== t.id && !t.blocked_by.includes(x.id)).map((x) => (
              <option key={x.id} value={x.id}>#{x.id} {x.title}</option>
            ))}
          </select>
          <button className="btn" disabled={!depPick} onClick={async () => {
            try { await api.addDependency(t.id, Number(depPick)); setDepPick(""); bump(); } catch (e) { toast(e instanceof Error ? e.message : "Failed"); }
          }}>Add</button>
        </div>
      </section>

      {/* Activity */}
      <section className="stack" style={{ gap: 8 }}>
        <h3>Activity</h3>
        <div className="row">
          <input className="input" placeholder="Add an update…" value={comment} onChange={(e) => setComment(e.target.value)}
            onKeyDown={async (e) => { if (e.key === "Enter" && comment.trim()) { await api.comment(t.id, comment.trim()); setComment(""); updates.reload(true); } }} />
          <button className="btn" disabled={!comment.trim()} onClick={async () => { await api.comment(t.id, comment.trim()); setComment(""); updates.reload(true); }}>Post</button>
        </div>
        {(updates.data || []).map((u) => (
          <div key={u.id} className="small" style={{ borderLeft: "2px solid var(--line-strong)", paddingLeft: 10 }}>
            <span className="muted">{fmtDateTime(u.created_at)} · {u.user_name || "system"}</span>
            <div>{u.kind === "comment" ? u.comment : u.kind === "status" ? `status ${u.from_value} → ${u.to_value}` :
              u.kind === "assignee" ? "reassigned" : u.kind === "created" ? "created the task" : `${u.kind} ${u.from_value ?? ""} → ${u.to_value ?? ""}`}</div>
          </div>
        ))}
      </section>

      {isManager && (
        <button className="btn danger" onClick={() => setConfirmDelete(true)}>Delete task</button>
      )}
      {confirmDelete && (
        <Confirm title="Delete task?" danger confirmLabel="Delete"
          message={`“${t.title}” and its history will be permanently removed.`}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={async () => { await api.deleteTask(t.id); toast("Task deleted"); bump(); onClose(); }} />
      )}
    </Shell>
  );
}

function Shell({ onClose, children, title }: { onClose: () => void; children: ReactNode; title?: string }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Task details">
        <div className="card-head" style={{ background: "var(--surface)" }}>
          <strong className="num">{title}</strong>
          <button className="btn ghost sm" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}
