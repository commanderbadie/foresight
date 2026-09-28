import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Avatar, Confirm } from "../components/ui";
import type { Member } from "../types";
import { useProject } from "./ProjectLayout";

export default function SettingsPage() {
  const { pid, project, members, isManager, reloadMembers, toast, bump } = useProject();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [cap, setCap] = useState(13);
  const [err, setErr] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function add() {
    setErr(null);
    try {
      await api.addMember(pid, { email, role, capacity_points: cap });
      setEmail("");
      toast("Member added");
      reloadMembers();
      bump();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  }

  async function update(m: Member, body: Partial<Member>) {
    try {
      await api.updateMember(pid, m.user_id, body);
      toast("Saved");
      reloadMembers();
      bump();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <>
      <header className="topbar"><h1>Settings</h1></header>
      <div className="content stack" style={{ maxWidth: 900 }}>
        <section className="card">
          <div className="card-head"><h2>Team</h2><span className="hint">capacity = story points a person can comfortably carry at once</span></div>
          <table className="tbl">
            <thead><tr><th>Member</th><th>Role</th><th>Capacity (pts)</th><th></th></tr></thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.user_id}>
                  <td><div className="row"><Avatar name={m.name} /><div>{m.name}<div className="small muted">{m.email}</div></div></div></td>
                  <td>
                    <select className="input" style={{ width: 120 }} disabled={!isManager} value={m.role}
                      onChange={(e) => update(m, { role: e.target.value as Member["role"] })}>
                      <option value="manager">manager</option><option value="member">member</option>
                    </select>
                  </td>
                  <td>
                    <input className="input num" style={{ width: 90 }} type="number" min={1} max={200} disabled={!isManager}
                      defaultValue={m.capacity_points}
                      onBlur={(e) => { const v = Number(e.target.value); if (v > 0 && v !== m.capacity_points) update(m, { capacity_points: v }); }} />
                  </td>
                  <td>{isManager && <button className="btn sm danger" onClick={() => setRemoving(m)}>Remove</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {isManager && (
            <div className="card-pad" style={{ borderTop: "1px solid var(--line)" }}>
              <div className="row wrap">
                <input className="input" style={{ flex: 2, minWidth: 200 }} placeholder="Email of a registered user" value={email} onChange={(e) => setEmail(e.target.value)} />
                <select className="input" style={{ width: 120 }} value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="member">member</option><option value="manager">manager</option>
                </select>
                <input className="input num" style={{ width: 90 }} type="number" min={1} value={cap} onChange={(e) => setCap(Number(e.target.value))} />
                <button className="btn primary" disabled={!email.includes("@")} onClick={add}>Add member</button>
              </div>
              {err && <div className="small" style={{ color: "var(--overdue)", marginTop: 8 }}>{err}</div>}
            </div>
          )}
        </section>

        {isManager && (
          <section className="card card-pad stack">
            <h2>Danger zone</h2>
            <div className="row between">
              <span className="small muted">Delete “{project.name}” with all tasks, history and predictions.</span>
              <button className="btn danger" onClick={() => setDeleting(true)}>Delete project</button>
            </div>
          </section>
        )}
      </div>
      {removing && (
        <Confirm title="Remove member?" danger confirmLabel="Remove"
          message={`${removing.name} will lose access. Their open tasks become unassigned.`}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            try { await api.removeMember(pid, removing.user_id); toast("Removed"); reloadMembers(); bump(); }
            catch (e) { toast(e instanceof Error ? e.message : "Failed"); }
            setRemoving(null);
          }} />
      )}
      {deleting && (
        <Confirm title="Delete project?" danger confirmLabel="Delete permanently"
          message="This cannot be undone." onCancel={() => setDeleting(false)}
          onConfirm={async () => { await api.deleteProject(pid); nav("/"); }} />
      )}
    </>
  );
}
