import { useEffect, useState } from "react";
import { api } from "../api";
import type { WhatIfResult } from "../types";
import { HealthRing, Loading, pct } from "./ui";

/** Before/after comparison of a proposed change, computed by the same model - nothing is saved. */
export default function WhatIfPreview({ pid, taskId, assigneeId, deadline, onResult }: {
  pid: number; taskId: number; assigneeId?: number | null; deadline?: string | null;
  onResult?: (r: WhatIfResult | null) => void;
}) {
  const [res, setRes] = useState<WhatIfResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setRes(null);
    setErr(null);
    const body: any = { task_id: taskId };
    if (assigneeId === null) body.unassign = true;
    else if (assigneeId !== undefined) body.assignee_id = assigneeId;
    if (deadline) body.deadline = deadline;
    api.whatIf(pid, body)
      .then((r) => { if (live) { setRes(r); onResult?.(r); } })
      .catch((e) => live && setErr(e.message));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, taskId, assigneeId, deadline]);

  if (err) return <div className="small" style={{ color: "var(--overdue)" }}>{err}</div>;
  if (!res) return <Loading label="Simulating with the model…" />;
  const b = res.task.before, a = res.task.after;
  const delta = res.health_after.score - res.health_before.score;
  return (
    <div className="stack">
      {b && a && (
        <div className="card card-pad compare">
          <div><div className="muted small">Delay risk now</div><div className="big-prob" style={{ color: "var(--ink-2)" }}>{pct(b.probability)}</div></div>
          <div style={{ fontSize: 22, color: "var(--ink-3)" }}>→</div>
          <div><div className="muted small">After change</div>
            <div className="big-prob" style={{ color: a.probability < b.probability ? "var(--low)" : "var(--high)" }}>{pct(a.probability)}</div></div>
        </div>
      )}
      <div className="card card-pad row" style={{ gap: 18 }}>
        <HealthRing score={res.health_after.score} status={res.health_after.status} size={96} />
        <div className="grow">
          <div style={{ fontWeight: 700 }}>
            Project health {res.health_before.score.toFixed(0)} → {res.health_after.score.toFixed(0)}{" "}
            <span className="num" style={{ color: delta >= 0 ? "var(--low)" : "var(--overdue)" }}>({delta >= 0 ? "+" : ""}{delta.toFixed(0)})</span>
          </div>
          {res.health_explanation.length ? (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18 }} className="small">
              {res.health_explanation.map((l) => <li key={l}>{l}</li>)}
            </ul>
          ) : <div className="small muted">No change in the health signals.</div>}
        </div>
      </div>
      {res.changed_tasks.length > 1 && (
        <div className="small">
          <div className="muted" style={{ marginBottom: 4 }}>Other tasks affected (workload shifts):</div>
          {res.changed_tasks.filter((c) => c.task_id !== taskId).slice(0, 5).map((c) => (
            <div key={c.task_id} className="row between">
              <span className="ellipsis">#{c.task_id} {c.title}</span>
              <span className="num">{pct(c.before)} → {pct(c.after)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
