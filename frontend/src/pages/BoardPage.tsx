import { useMemo, useState } from "react";
import { api } from "../api";
import NewTaskModal from "../components/NewTaskModal";
import { Avatar, ErrorState, RiskBadge, STATUS_LABEL, Skeleton, relDays, useAsync } from "../components/ui";
import type { Status, Task } from "../types";
import { useProject } from "./ProjectLayout";

const COLUMNS: Status[] = ["todo", "in_progress", "review", "done"];

export default function BoardPage() {
  const { pid, openTask, version, bump, toast, members } = useProject();
  const { data, error, loading, reload, setData } = useAsync(() => api.tasks(pid), [pid, version]);
  const [dragId, setDragId] = useState<number | null>(null);
  const [over, setOver] = useState<Status | null>(null);
  const [who, setWho] = useState("");
  const [riskyOnly, setRiskyOnly] = useState(false);
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);

  const filtered = useMemo(() => (data || []).filter((t) =>
    (!who || String(t.assignee_id ?? "none") === who) &&
    (!riskyOnly || (t.risk && ["high", "overdue"].includes(t.risk.level))) &&
    (!q || t.title.toLowerCase().includes(q.toLowerCase()) || String(t.id) === q.replace("#", ""))), [data, who, riskyOnly, q]);

  async function move(taskId: number, status: Status) {
    const t = data?.find((x) => x.id === taskId);
    if (!t || t.status === status) return;
    setData((d) => d ? d.map((x) => x.id === taskId ? { ...x, status } : x) : d); // optimistic
    try {
      await api.updateTask(taskId, { status });
      toast(`Moved to ${STATUS_LABEL[status]}`);
      bump();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not move task");
      reload(true);
    }
  }

  return (
    <>
      <header className="topbar">
        <h1>Board</h1>
        <div className="row wrap">
          <input className="input" style={{ width: 180 }} placeholder="Search or #id" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input" style={{ width: 170 }} value={who} onChange={(e) => setWho(e.target.value)} aria-label="Filter by assignee">
            <option value="">Everyone</option>
            <option value="none">Unassigned</option>
            {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
          </select>
          <label className="row small" style={{ fontWeight: 600 }}>
            <input type="checkbox" checked={riskyOnly} onChange={(e) => setRiskyOnly(e.target.checked)} /> High risk only
          </label>
          <button className="btn primary" onClick={() => setCreating(true)}>+ Task</button>
        </div>
      </header>
      <div className="content">
        {loading && !data && <div className="board">{COLUMNS.map((c) => <Skeleton key={c} h={300} />)}</div>}
        {error && <ErrorState message={error} onRetry={reload} />}
        {data && (
          <div className="board">
            {COLUMNS.map((col) => {
              const items = filtered.filter((t) => t.status === col)
                .sort((a, b) => col === "done"
                  ? (b.completed_at || "").localeCompare(a.completed_at || "")
                  : (b.risk?.probability ?? -1) - (a.risk?.probability ?? -1));
              return (
                <div key={col} className={`column${over === col ? " drop" : ""}`}
                  onDragOver={(e) => { e.preventDefault(); setOver(col); }}
                  onDragLeave={() => setOver(null)}
                  onDrop={(e) => { e.preventDefault(); setOver(null); if (dragId != null) move(dragId, col); setDragId(null); }}>
                  <div className="column-head"><span>{STATUS_LABEL[col]}</span><span className="muted num">{items.length}</span></div>
                  {items.length === 0 && <div className="small muted" style={{ padding: 8 }}>Drop tasks here</div>}
                  {(col === "done" ? items.slice(0, 15) : items).map((t) => (
                    <TaskCard key={t.id} t={t} onOpen={() => openTask(t.id)} onDrag={() => setDragId(t.id)} />
                  ))}
                  {col === "done" && items.length > 15 && <div className="small muted" style={{ padding: 6 }}>+{items.length - 15} more done</div>}
                </div>
              );
            })}
          </div>
        )}
      </div>
      {creating && <NewTaskModal onClose={() => setCreating(false)} onCreated={() => { setCreating(false); bump(); }} />}
    </>
  );
}

function TaskCard({ t, onOpen, onDrag }: { t: Task; onOpen: () => void; onDrag: () => void }) {
  const lvl = t.risk?.level;
  return (
    <div className={`tcard${lvl && lvl !== "low" ? ` risk-${lvl}` : ""}`} draggable onDragStart={onDrag} onClick={onOpen}
      role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onOpen()}>
      <div className="row between">
        <span className="small muted num">#{t.id}</span>
        {t.status !== "done" && <RiskBadge risk={t.risk} />}
      </div>
      <div className="title">{t.title}</div>
      <div className="row between small">
        <span className="row" style={{ gap: 6 }}>
          <Avatar name={t.assignee_name} />
          <span className={t.is_overdue ? "" : "muted"} style={t.is_overdue ? { color: "var(--overdue)", fontWeight: 700 } : undefined}>
            {t.status === "done" ? "done" : relDays(t.deadline)}
          </span>
        </span>
        <span className="row" style={{ gap: 6 }}>
          {t.blocked_by.length > 0 && t.status !== "done" && <span title="Waiting on prerequisites" className="badge">⛓ {t.blocked_by.length}</span>}
          {t.story_points != null && <span className="badge num">{t.story_points}</span>}
        </span>
      </div>
    </div>
  );
}
