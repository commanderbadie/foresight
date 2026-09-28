import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import NewTaskModal from "../components/NewTaskModal";
import WhatIfPreview from "../components/WhatIfPreview";
import {
  Empty, ErrorState, HealthRing, Modal, RiskBadge, RiskBar, Skeleton, fmtDate, pct, relDays, useAsync,
} from "../components/ui";
import type { Overview, Recommendation } from "../types";
import { useProject } from "./ProjectLayout";

export default function DashboardPage() {
  const { pid, project, openTask, version, bump, toast, members } = useProject();
  const { data, error, loading, reload } = useAsync(() => api.overview(pid), [pid, version]);
  const [preview, setPreview] = useState<Recommendation | null>(null);
  const [applying, setApplying] = useState(false);
  const [newTask, setNewTask] = useState(false);

  async function apply(rec: Recommendation) {
    if (!rec.action) return;
    setApplying(true);
    try {
      await api.updateTask(rec.action.task_id, { assignee_id: rec.action.to_member_id });
      await api.feedback(pid, rec.id, rec.kind, "applied");
      setPreview(null);
      toast("Change applied — risk and health recalculated");
      bump();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed");
    } finally {
      setApplying(false);
    }
  }

  async function dismiss(rec: Recommendation) {
    await api.feedback(pid, rec.id, rec.kind, "dismissed");
    toast("Dismissed for 2 days");
    reload(true);
  }

  return (
    <>
      <header className="topbar">
        <div>
          <h1>{project.name}</h1>
          {data && (
            <div className="muted small">
              {fmtDate(data.project.start_date)} → {fmtDate(data.project.end_date)} · {data.flow.open_total} open tasks ·{" "}
              {data.flow.completed_total} done
            </div>
          )}
        </div>
        <div className="row">
          {data?.model.is_synthetic && (
            <span className="badge synthetic tip" data-tip={data.model.warning || ""}>demo model · synthetic data</span>
          )}
          <button className="btn primary" onClick={() => setNewTask(true)}>+ Task</button>
        </div>
      </header>
      <div className="content">
        {loading && !data && <div className="grid grid-dash"><div className="span-7"><Skeleton h={220} /></div><div className="span-5"><Skeleton h={220} /></div></div>}
        {error && <ErrorState message={error} onRetry={reload} />}
        {data && <Dashboard data={data} openTask={openTask} onPreview={setPreview} onDismiss={dismiss} />}
      </div>
      {preview && preview.action && (
        <Modal title="Preview recommendation" onClose={() => setPreview(null)}>
          <p style={{ marginTop: 0 }}><strong>{preview.title}</strong></p>
          <p className="small muted">
            Reassign #{preview.action.task_id} to{" "}
            {members.find((m) => m.user_id === preview.action!.to_member_id)?.name}. This preview is computed by the same model; nothing is saved yet.
          </p>
          <WhatIfPreview pid={pid} taskId={preview.action.task_id} assigneeId={preview.action.to_member_id} />
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
            <button className="btn" onClick={() => setPreview(null)}>Cancel</button>
            <button className="btn primary" disabled={applying} onClick={() => apply(preview)}>
              {applying ? "Applying…" : "Apply change"}
            </button>
          </div>
        </Modal>
      )}
      {newTask && <NewTaskModal onClose={() => setNewTask(false)} onCreated={() => { setNewTask(false); bump(); }} />}
    </>
  );
}

function Dashboard({ data, openTask, onPreview, onDismiss }: {
  data: Overview; openTask: (id: number) => void; onPreview: (r: Recommendation) => void; onDismiss: (r: Recommendation) => void;
}) {
  const h = data.health;
  const delta = data.health_previous != null ? h.score - data.health_previous : null;
  const maxPts = Math.max(...data.workload.members.map((m) => Math.max(m.open_points, m.capacity_points)), 1);
  const weekly = data.flow.weekly.map((w) => ({ ...w, label: fmtDate(w.week_ending) }));

  return (
    <div className="grid grid-dash">
      {/* Health */}
      <section className="card span-7">
        <div className="card-head">
          <h2>Project health</h2>
          <span className="hint tip" data-tip="100 minus documented penalties: overdue ×8, urgent ×5, blocked ×4, high ML risk ×5, overloaded member ×8, schedule lag. Capped per signal.">
            how is this calculated?
          </span>
        </div>
        <div className="card-pad health">
          <HealthRing score={h.score} status={h.status} />
          <div className="grow">
            {delta != null && Math.abs(delta) >= 1 && (
              <div className="small" style={{ marginBottom: 8, color: delta > 0 ? "var(--low)" : "var(--overdue)", fontWeight: 700 }}>
                {delta > 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(0)} since last check
              </div>
            )}
            {h.signals.length === 0 ? <div className="muted">No warning signals. Nice.</div> : (
              <ul className="health-reasons">
                {h.signals.map((s) => (
                  <li key={s.key}>
                    <span className="penalty">−{s.penalty.toFixed(0)}</span>
                    <span>
                      {s.label}
                      {s.task_ids.length > 0 && (
                        <span className="small"> · {s.task_ids.slice(0, 4).map((id) => (
                          <a key={id} href="#" onClick={(e) => { e.preventDefault(); openTask(id); }} style={{ marginRight: 6 }}>#{id}</a>
                        ))}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      {/* KPIs */}
      <section className="span-5 kpis" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card kpi"><div className="label">Completion (by points)</div>
          <div className="value">{h.completion_pct.toFixed(0)}%</div>
          <div className="sub">{h.time_elapsed_pct != null ? `${h.time_elapsed_pct.toFixed(0)}% of time used` : "no project dates"}</div></div>
        <div className="card kpi"><div className="label">Deadline adherence</div>
          <div className="value">{data.flow.deadline_adherence_pct ?? "—"}{data.flow.deadline_adherence_pct != null && "%"}</div>
          <div className="sub">done on or before deadline</div></div>
        <div className="card kpi"><div className="label">Predicted at risk</div>
          <div className="value" style={{ color: "var(--high)" }}>{data.risk_counts.high}</div>
          <div className="sub">{data.risk_counts.medium} medium · {data.risk_counts.overdue} overdue</div></div>
        <div className="card kpi"><div className="label">Median cycle time</div>
          <div className="value">{data.flow.median_cycle_time_days ?? "—"}<span style={{ fontSize: 14 }}> d</span></div>
          <div className="sub">start → done · WIP {data.flow.wip}</div></div>
      </section>

      {/* Recommendations */}
      <section className="card span-7">
        <div className="card-head"><h2>Recommended actions</h2><span className="hint">generated from live project data + model</span></div>
        {data.recommendations.length === 0 ? <Empty title="Nothing needs attention right now" /> : (
          <div>
            {data.recommendations.map((r) => (
              <div key={r.id} className={`rec ${r.severity}`}>
                <div className="bar" />
                <div className="grow">
                  <div style={{ fontWeight: 700 }}>{r.title}</div>
                  <div className="small" style={{ color: "var(--ink-2)", marginTop: 2 }}>{r.detail}</div>
                  {r.evidence.length > 0 && (
                    <div className="small muted" style={{ marginTop: 4 }}>Evidence: {r.evidence.slice(0, 3).join(" · ")}</div>
                  )}
                  <div className="row wrap" style={{ marginTop: 8 }}>
                    {r.action && <button className="btn sm primary" onClick={() => onPreview(r)}>Preview & apply</button>}
                    {r.task_ids.slice(0, 1).map((id) => <button key={id} className="btn sm" onClick={() => openTask(id)}>Open #{id}</button>)}
                    <button className="btn sm ghost" onClick={() => onDismiss(r)}>Dismiss</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Top risks */}
      <section className="card span-5">
        <div className="card-head"><h2>Most likely to slip</h2><span className="hint">predicted delay probability</span></div>
        {data.top_risks.length === 0 ? <Empty title="No open tasks with deadlines" /> : (
          <div className="list">
            {data.top_risks.map((t) => (
              <div key={t.id} className="list-item" onClick={() => openTask(t.id)} role="button" tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && openTask(t.id)}>
                <div className="grow">
                  <div className="row between">
                    <span className="ellipsis" style={{ fontWeight: 700 }}>#{t.id} {t.title}</span>
                    <RiskBadge risk={t.risk} />
                  </div>
                  {t.risk && t.risk.level !== "overdue" && <div style={{ margin: "6px 0 4px" }}><RiskBar p={t.risk.probability} level={t.risk.level} /></div>}
                  <div className="small muted ellipsis">
                    {t.assignee_name || "Unassigned"} · {relDays(t.deadline)}
                    {t.risk?.factors[0] && t.risk.level !== "overdue" ? ` · ${t.risk.factors[0].label}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Workload */}
      <section className="card span-6">
        <div className="card-head"><h2>Workload</h2><span className="hint">open story points · line = capacity</span></div>
        <div style={{ padding: "8px 0" }}>
          {data.workload.members.map((m) => (
            <div key={m.member_id} className="load-row" title={m.reasons.join("; ")}>
              <span className="ellipsis" style={{ fontWeight: 600 }}>{m.name}</span>
              <div className="load-track">
                <div className={`load-fill ${m.status}`} style={{ width: `${(m.open_points / maxPts) * 100}%` }} />
                <div className="load-cap" style={{ left: `${(m.capacity_points / maxPts) * 100}%` }} />
              </div>
              <span className="small num" style={{ textAlign: "right", color: m.status === "overloaded" ? "var(--high)" : undefined }}>
                {m.open_points} pts{m.status === "overloaded" ? " ⚠" : ""}
              </span>
            </div>
          ))}
          {data.workload.unassigned_open > 0 && (
            <div className="small muted" style={{ padding: "6px 18px" }}>{data.workload.unassigned_open} open task(s) unassigned</div>
          )}
        </div>
      </section>

      {/* Flow */}
      <section className="card span-6">
        <div className="card-head"><h2>Delivery trend</h2><span className="hint">tasks completed per week · % on time</span></div>
        <div style={{ height: 230, padding: "12px 12px 4px 0" }}>
          <ResponsiveContainer>
            <ComposedChart data={weekly}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-3)" }} axisLine={false} tickLine={false} />
              <YAxis yAxisId="l" allowDecimals={false} tick={{ fontSize: 11, fill: "var(--ink-3)" }} axisLine={false} tickLine={false} width={32} />
              <YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: "var(--ink-3)" }} axisLine={false} tickLine={false} width={36} unit="%" />
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8 }} />
              <Bar yAxisId="l" dataKey="completed" name="Completed" fill="var(--brand)" radius={[4, 4, 0, 0]} />
              <Line yAxisId="r" dataKey="on_time_pct" name="On time %" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Upcoming */}
      <section className="card span-12">
        <div className="card-head"><h2>Upcoming deadlines</h2></div>
        {data.upcoming.length === 0 ? <Empty title="No upcoming deadlines" /> : (
          <table className="tbl">
            <thead><tr><th>Task</th><th>Owner</th><th>Due</th><th>Status</th><th>Risk</th></tr></thead>
            <tbody>
              {data.upcoming.map((t) => (
                <tr key={t.id} onClick={() => openTask(t.id)} style={{ cursor: "pointer" }}>
                  <td><strong>#{t.id}</strong> {t.title}</td>
                  <td>{t.assignee_name || <span className="muted">Unassigned</span>}</td>
                  <td>{relDays(t.deadline)}</td>
                  <td className="small">{t.status.replace("_", " ")}</td>
                  <td><RiskBadge risk={t.risk} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <div className="span-12 small muted">
        Model: {data.model.algorithm} · {data.model.data_source} · thresholds high ≥ {pct(data.model.thresholds.high)}, medium ≥ {pct(data.model.thresholds.medium)}
      </div>
    </div>
  );
}
