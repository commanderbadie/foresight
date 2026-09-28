import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { Priority, Risk, RiskLevel } from "../types";

// ---------------- formatting ----------------
export const pct = (p: number | null | undefined, digits = 0) =>
  p == null ? "—" : `${(p * 100).toFixed(digits)}%`;

export function relDays(iso: string | null): string {
  if (!iso) return "no deadline";
  const d = (new Date(iso).getTime() - Date.now()) / 86_400_000;
  if (d < 0) return `${Math.abs(d) < 1 ? Math.round(-d * 24) + " h" : (-d).toFixed(1) + " d"} overdue`;
  if (d < 1) return `due in ${Math.max(1, Math.round(d * 24))} h`;
  return `due in ${d.toFixed(d < 10 ? 1 : 0)} d`;
}

export const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "—";

export const fmtDateTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

/** ISO string -> value for <input type="datetime-local"> in the user's local time. */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60_000).toISOString().slice(0, 16);
}
export const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);

export const initials = (name: string | null | undefined) =>
  (name || "?").split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();

export const levelColor = (l: RiskLevel | string | undefined) =>
  l === "overdue" ? "var(--overdue)" : l === "high" ? "var(--high)" : l === "medium" ? "var(--medium)" : "var(--low)";

// ---------------- data hook ----------------
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      setData(await fnRef.current());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, deps);
  return { data, error, loading, reload, setData };
}

// ---------------- small components ----------------
export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="16" r="12.5" fill="none" stroke="#3fb3a8" strokeWidth="3.5" />
      <path d="M16 3.5a12.5 12.5 0 0 1 12.5 12.5" fill="none" stroke="#E8590C" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="16" cy="16" r="3.2" fill="#fff" />
    </svg>
  );
}

export function RiskBadge({ risk, showProb = true }: { risk: Risk | null | undefined; showProb?: boolean }) {
  if (!risk) return <span className="badge">no deadline</span>;
  if (risk.level === "overdue") return <span className="badge overdue">overdue</span>;
  return (
    <span className={`badge ${risk.level}`} title="Predicted probability of missing the deadline">
      {risk.level}{showProb && <span className="num">{pct(risk.probability)}</span>}
    </span>
  );
}

export function RiskBar({ p, level }: { p: number; level: string }) {
  return (
    <div className="riskbar" aria-label={`delay risk ${pct(p)}`}>
      <span style={{ width: `${Math.max(3, p * 100)}%`, background: levelColor(level) }} />
    </div>
  );
}

export function PriorityTag({ p }: { p: Priority }) {
  return <span className={`row small prio-${p}`} style={{ gap: 5, fontWeight: 700 }}><span className="dot" />{p}</span>;
}

export function Avatar({ name }: { name: string | null }) {
  return <span className="avatar" title={name || "Unassigned"}>{name ? initials(name) : "–"}</span>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="state"><div className="spinner" /><span>{label}</span></div>;
}

export function Skeleton({ h = 120 }: { h?: number }) {
  return <div className="skeleton" style={{ height: h }} />;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state error">
      <strong>Something went wrong</strong>
      <span>{message}</span>
      {onRetry && <button className="btn sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="state"><strong style={{ color: "var(--ink-2)" }}>{title}</strong>{children}</div>;
}

export function Modal({ onClose, children, title }: { onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
      <div className="overlay modal-overlay" onClick={onClose} />
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="row between" style={{ marginBottom: 14 }}>
          <h2>{title}</h2>
          <button className="btn ghost sm" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </>
  );
}

export function Confirm({ title, message, confirmLabel = "Confirm", danger, onConfirm, onCancel }: {
  title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p style={{ marginTop: 0, color: "var(--ink-2)" }}>{message}</p>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onCancel}>Cancel</button>
        <button className={`btn ${danger ? "danger" : "primary"}`} onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </Modal>
  );
}

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 2600);
    return () => clearTimeout(t);
  }, [msg]);
  return { show: setMsg, node: msg ? <div className="toast" role="status">{msg}</div> : null };
}

/** Ring gauge for the health score. */
export function HealthRing({ score, status, size = 132 }: { score: number; status: string; size?: number }) {
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r;
  const color = status === "on_track" ? "var(--low)" : status === "at_risk" ? "var(--medium)" : "var(--overdue)";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`health ${score} of 100`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth="10" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
        strokeDasharray={`${(score / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray .6s ease" }} />
      <text x="50%" y="48%" textAnchor="middle" fontFamily="var(--mono)" fontSize={size * 0.24} fontWeight="600" fill="var(--ink)">
        {Math.round(score)}
      </text>
      <text x="50%" y="66%" textAnchor="middle" fontSize="11" fill="var(--ink-3)" fontWeight="700" letterSpacing="0.06em">
        {status.replace("_", " ").toUpperCase()}
      </text>
    </svg>
  );
}

export const STATUS_LABEL: Record<string, string> = {
  todo: "To do", in_progress: "In progress", review: "Review", done: "Done",
};
