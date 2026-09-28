import { api } from "../api";
import { Avatar, Empty, ErrorState, RiskBadge, Skeleton, relDays, useAsync } from "../components/ui";
import { useProject } from "./ProjectLayout";

export default function TeamPage() {
  const { pid, version, openTask } = useProject();
  const { data, error, loading, reload } = useAsync(() => api.workload(pid), [pid, version]);

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Team workload</h1>
          <div className="muted small">Capacity is measured in open story points. This view is about balancing work, not rating people.</div>
        </div>
      </header>
      <div className="content">
        {loading && !data && <Skeleton h={300} />}
        {error && <ErrorState message={error} onRetry={reload} />}
        {data && (
          <div className="stack">
            <div className="kpis">
              <div className="card kpi"><div className="label">Team median load</div><div className="value">{data.team_median_points}</div><div className="sub">open points per person</div></div>
              <div className="card kpi"><div className="label">Imbalance</div><div className="value">{data.imbalance_ratio}×</div><div className="sub">heaviest load ÷ median</div></div>
              <div className="card kpi"><div className="label">Overloaded</div><div className="value" style={{ color: "var(--high)" }}>{data.members.filter((m) => m.status === "overloaded").length}</div><div className="sub">&gt;1.5× median and over capacity</div></div>
              <div className="card kpi"><div className="label">Unassigned</div><div className="value">{data.unassigned_open}</div><div className="sub">open tasks without an owner</div></div>
            </div>
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
              {data.members.map((m) => (
                <section key={m.member_id} className="card">
                  <div className="card-head">
                    <div className="row"><Avatar name={m.name} /><h3>{m.name}</h3></div>
                    <span className={`badge ${m.status === "overloaded" ? "high" : m.status === "underutilised" ? "" : "low"}`}>{m.status}</span>
                  </div>
                  <div className="card-pad stack" style={{ gap: 8 }}>
                    <div className="row between small">
                      <span><strong className="num">{m.open_points}</strong> / {m.capacity_points} pts capacity</span>
                      <span className="num">{Math.round(m.utilisation * 100)}%</span>
                    </div>
                    <div className="load-track">
                      <div className={`load-fill ${m.status}`} style={{ width: `${Math.min(100, m.utilisation * 100)}%` }} />
                    </div>
                    <div className="small muted">
                      {m.open_tasks} open · {m.high_priority_open} high-priority · {m.points_due_soon} pts due ≤3 days · {m.overdue} overdue
                    </div>
                    {m.reasons.length > 0 && <div className="small" style={{ color: "var(--ink-2)" }}>{m.reasons.join(" · ")}</div>}
                  </div>
                  {(m.tasks || []).length === 0 ? <Empty title="No open tasks" /> : (
                    <div className="list" style={{ borderTop: "1px solid var(--line)" }}>
                      {(m.tasks || []).map((t) => (
                        <div key={t.id} className="list-item" onClick={() => openTask(t.id)}>
                          <div className="grow ellipsis"><strong>#{t.id}</strong> {t.title}
                            <div className="small muted">{t.story_points ?? "?"} pts · {relDays(t.deadline)}</div></div>
                          <RiskBadge risk={t.risk} />
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
