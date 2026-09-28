import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Empty, ErrorState, Logo, Modal, Skeleton, fmtDate, fromLocalInput, useAsync } from "../components/ui";

export default function ProjectsPage() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const { data, error, loading, reload } = useAsync(() => api.projects(), []);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", start: "", end: "" });
  const [formErr, setFormErr] = useState<string | null>(null);

  async function create() {
    setFormErr(null);
    try {
      const p = await api.createProject({
        name: form.name, description: form.description,
        start_date: fromLocalInput(form.start), end_date: fromLocalInput(form.end),
      });
      nav(`/p/${p.id}`);
    } catch (e) {
      setFormErr(e instanceof Error ? e.message : "Failed");
    }
  }

  const healthColor = (s: string | null) =>
    s === "on_track" ? "var(--low)" : s === "at_risk" ? "var(--medium)" : s === "critical" ? "var(--overdue)" : "var(--ink-3)";

  return (
    <div style={{ minHeight: "100%" }}>
      <header className="topbar">
        <div className="row" style={{ gap: 10, fontWeight: 800, fontSize: 17 }}><Logo /> Foresight</div>
        <div className="row">
          <span className="muted small">{user?.email}</span>
          <button className="btn sm" onClick={logout}>Sign out</button>
        </div>
      </header>
      <div className="content" style={{ maxWidth: 1100, margin: "0 auto", width: "100%" }}>
        <div className="row between" style={{ marginBottom: 18 }}>
          <div>
            <h1>Your projects</h1>
            <div className="muted">Pick a project to see its health, risks and recommendations.</div>
          </div>
          <button className="btn primary" onClick={() => setCreating(true)}>+ New project</button>
        </div>
        {loading && <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))" }}><Skeleton /><Skeleton /></div>}
        {error && <ErrorState message={error} onRetry={reload} />}
        {data && data.length === 0 && (
          <div className="card"><Empty title="No projects yet">
            Create one, or load the demo project with <code>python -m app.seed</code> and sign in as priya@demo.foresight.
          </Empty></div>
        )}
        {data && data.length > 0 && (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))" }}>
            {data.map((p) => (
              <Link key={p.id} to={`/p/${p.id}`} className="card card-pad" style={{ color: "inherit", textDecoration: "none" }}>
                <div className="row between">
                  <h2 className="ellipsis">{p.name}</h2>
                  {p.is_demo && <span className="badge synthetic" title="Synthetic demo data">demo</span>}
                </div>
                <p className="muted small" style={{ minHeight: 40 }}>{p.description.slice(0, 120) || "No description"}</p>
                <div className="row between small">
                  <span>{p.open_tasks} open · {p.member_count} people · ends {fmtDate(p.end_date)}</span>
                  <span className="num" style={{ color: healthColor(p.health_status), fontWeight: 700 }}>
                    {p.health_score != null ? `${Math.round(p.health_score)}/100` : "—"}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
      {creating && (
        <Modal title="New project" onClose={() => setCreating(false)}>
          <div className="form-grid">
            <label className="field full">Name
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus />
            </label>
            <label className="field full">Description
              <textarea className="input" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            <label className="field">Start
              <input className="input" type="datetime-local" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />
            </label>
            <label className="field">Planned end
              <input className="input" type="datetime-local" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} />
            </label>
          </div>
          {formErr && <div className="small" style={{ color: "var(--overdue)", marginTop: 10 }}>{formErr}</div>}
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
            <button className="btn" onClick={() => setCreating(false)}>Cancel</button>
            <button className="btn primary" disabled={form.name.trim().length < 2} onClick={create}>Create</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
