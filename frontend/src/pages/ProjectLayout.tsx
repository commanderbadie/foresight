import { createContext, useCallback, useContext, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import TaskDrawer from "../components/TaskDrawer";
import { ErrorState, Loading, Logo, initials, useAsync, useToast } from "../components/ui";
import type { Member, ProjectListItem } from "../types";

interface ProjectCtx {
  pid: number;
  project: ProjectListItem;
  members: Member[];
  isManager: boolean;
  openTask: (id: number) => void;
  /** increments whenever data changes, so pages can refetch */
  version: number;
  bump: () => void;
  toast: (m: string) => void;
  reloadMembers: () => void;
}

const Ctx = createContext<ProjectCtx | null>(null);
export const useProject = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error("useProject outside ProjectLayout");
  return c;
};

const NAV = [
  { to: "", label: "Overview", icon: "◎", end: true },
  { to: "board", label: "Board", icon: "▦" },
  { to: "team", label: "Team workload", icon: "≋" },
  { to: "assistant", label: "Ask Foresight", icon: "✦" },
  { to: "model", label: "Model & evaluation", icon: "∿" },
  { to: "settings", label: "Settings", icon: "⚙" },
];

export default function ProjectLayout() {
  const pid = Number(useParams().pid);
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [taskId, setTaskId] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  const toast = useToast();

  const projects = useAsync(() => api.projects(), []);
  const members = useAsync(() => api.members(pid), [pid]);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  if (projects.loading || members.loading) return <Loading />;
  if (projects.error || members.error)
    return <ErrorState message={projects.error || members.error || ""} onRetry={() => { projects.reload(); members.reload(); }} />;
  const project = projects.data!.find((p) => p.id === pid);
  if (!project) return <ErrorState message="Project not found or you are not a member." onRetry={() => nav("/")} />;

  const ctx: ProjectCtx = {
    pid, project, members: members.data!, isManager: project.role === "manager",
    openTask: setTaskId, version, bump, toast: toast.show, reloadMembers: () => members.reload(true),
  };

  return (
    <Ctx.Provider value={ctx}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand"><Logo /> Foresight</div>
          <NavLink to="/" className="nav-item">← All projects</NavLink>
          <div className="nav-label ellipsis" title={project.name}>{project.name}</div>
          {NAV.map((n) => (
            <NavLink key={n.label} to={n.to} end={n.end} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
              <span style={{ width: 18, textAlign: "center" }}>{n.icon}</span>{n.label}
            </NavLink>
          ))}
          <div className="sidebar-foot">
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="avatar">{initials(user?.name)}</span>
              <div className="grow ellipsis">{user?.name}<div className="small">{project.role}</div></div>
            </div>
            <button className="nav-item" style={{ padding: "4px 0" }} onClick={logout}>Sign out</button>
          </div>
        </aside>
        <main className="main">
          <Outlet />
        </main>
      </div>
      {taskId != null && <TaskDrawer taskId={taskId} onClose={() => setTaskId(null)} />}
      {toast.node}
    </Ctx.Provider>
  );
}
