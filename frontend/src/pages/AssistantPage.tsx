import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AssistantAnswer } from "../types";
import { useProject } from "./ProjectLayout";

const SUGGESTIONS = [
  "Why is this project at risk?",
  "Which tasks are most likely to be delayed?",
  "Who is overloaded?",
  "What should the manager address first?",
  "What is due this week?",
  "What is blocking progress?",
];

type Msg = { role: "user"; text: string } | { role: "bot"; a: AssistantAnswer } | { role: "err"; text: string };

/** Renders **bold** and #id links without dangerouslySetInnerHTML. */
function Rich({ text, onTask }: { text: string; onTask: (id: number) => void }) {
  const parts = text.split(/(\*\*[^*]+\*\*|#\d+)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (/^#\d+$/.test(p)) return <a key={i} href="#" onClick={(e) => { e.preventDefault(); onTask(Number(p.slice(1))); }}>{p}</a>;
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

export default function AssistantPage() {
  const { pid, openTask } = useProject();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, busy]);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const a = await api.ask(pid, question);
      setMsgs((m) => [...m, { role: "bot", a }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "err", text: e instanceof Error ? e.message : "Failed" }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="topbar">
        <div>
          <h1>Ask Foresight</h1>
          <div className="muted small">Answers come only from this project's data through a fixed set of read-only tools. Task numbers are clickable.</div>
        </div>
      </header>
      <div className="content" style={{ maxWidth: 860 }}>
        <div className="chat">
          {msgs.length === 0 && (
            <div className="card card-pad stack">
              <strong>Try one of these</strong>
              <div className="row wrap">{SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}</div>
            </div>
          )}
          {msgs.map((m, i) =>
            m.role === "user" ? <div key={i} className="bubble user">{m.text}</div>
            : m.role === "err" ? <div key={i} className="bubble bot" style={{ color: "var(--overdue)" }}>{m.text}</div>
            : (
              <div key={i} className="bubble bot">
                <Rich text={m.a.answer} onTask={openTask} />
                <div className="small muted" style={{ marginTop: 8 }}>
                  {m.a.mode === "offline" ? "offline rule mode" : m.a.mode} · data used: {m.a.tools_used.map((t) => t.tool).join(", ") || "none"}
                </div>
              </div>
            ))}
          {busy && <div className="bubble bot row"><div className="spinner" /> Looking at the project data…</div>}
          <div ref={end} />
        </div>
        <form className="row" style={{ marginTop: 16 }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <input className="input" placeholder="Ask about risks, workload, deadlines, a task like #42…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={1000} />
          <button className="btn primary" disabled={busy || q.trim().length < 2}>Ask</button>
        </form>
        {msgs.length > 0 && (
          <div className="row wrap" style={{ marginTop: 10 }}>
            {SUGGESTIONS.slice(0, 4).map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}
          </div>
        )}
      </div>
    </>
  );
}
