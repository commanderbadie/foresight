import { useState } from "react";
import { api } from "../api";
import { useProject } from "../pages/ProjectLayout";
import type { Status } from "../types";
import { Modal, fromLocalInput, useAsync } from "./ui";

export default function NewTaskModal({ onClose, onCreated, initialStatus = "todo" }: {
  onClose: () => void; onCreated: () => void; initialStatus?: Status;
}) {
  const { pid, members, toast } = useProject();
  const tasks = useAsync(() => api.tasks(pid), [pid]);
  const [f, setF] = useState({
    title: "", description: "", task_type: "feature", priority: "medium", story_points: "3",
    assignee_id: "", deadline: "", depends_on: [] as number[],
  });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await api.createTask(pid, {
        title: f.title, description: f.description, task_type: f.task_type, priority: f.priority,
        status: initialStatus, story_points: f.story_points === "" ? null : Number(f.story_points),
        assignee_id: f.assignee_id ? Number(f.assignee_id) : null, deadline: fromLocalInput(f.deadline),
        depends_on: f.depends_on,
      });
      toast("Task created");
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="New task" onClose={onClose}>
      <div className="form-grid">
        <label className="field full">Title
          <input className="input" autoFocus value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={200} />
        </label>
        <label className="field full">Description
          <textarea className="input" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </label>
        <label className="field">Type
          <select className="input" value={f.task_type} onChange={(e) => setF({ ...f, task_type: e.target.value })}>
            <option value="feature">Feature</option><option value="bug">Bug</option><option value="chore">Chore</option>
          </select>
        </label>
        <label className="field">Priority
          <select className="input" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
            <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
          </select>
        </label>
        <label className="field">Estimate (story points)
          <select className="input" value={f.story_points} onChange={(e) => setF({ ...f, story_points: e.target.value })}>
            <option value="">Not estimated</option>
            {[1, 2, 3, 5, 8, 13].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="field">Assignee
          <select className="input" value={f.assignee_id} onChange={(e) => setF({ ...f, assignee_id: e.target.value })}>
            <option value="">Unassigned</option>
            {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
          </select>
        </label>
        <label className="field">Deadline
          <input className="input" type="datetime-local" value={f.deadline} onChange={(e) => setF({ ...f, deadline: e.target.value })} />
        </label>
        <label className="field">Depends on
          <select className="input" multiple size={3} value={f.depends_on.map(String)}
            onChange={(e) => setF({ ...f, depends_on: Array.from(e.target.selectedOptions).map((o) => Number(o.value)) })}>
            {(tasks.data || []).filter((t) => t.status !== "done").map((t) => <option key={t.id} value={t.id}>#{t.id} {t.title}</option>)}
          </select>
        </label>
      </div>
      {err && <div className="small" style={{ color: "var(--overdue)", marginTop: 10 }}>{err}</div>}
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={busy || f.title.trim().length < 2} onClick={save}>{busy ? "Saving…" : "Create task"}</button>
      </div>
    </Modal>
  );
}
