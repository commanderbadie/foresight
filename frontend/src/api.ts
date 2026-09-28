import type {
  AssistantAnswer, Member, ModelInfo, Overview, ProjectListItem, Task, TaskUpdate, User, WhatIfResult, Workload,
} from "./types";

const TOKEN_KEY = "foresight.token";
const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (res.status === 401 && token) {
    tokenStore.clear();
    window.dispatchEvent(new Event("foresight:logout"));
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail
        : Array.isArray(body.detail) ? body.detail.map((d: any) => d.msg).join("; ") : msg;
    } catch { /* not JSON */ }
    throw new ApiError(res.status, msg || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const post = <T>(p: string, body?: unknown) => request<T>(p, { method: "POST", body: JSON.stringify(body ?? {}) });
const patch = <T>(p: string, body: unknown) => request<T>(p, { method: "PATCH", body: JSON.stringify(body) });
const del = (p: string) => request<void>(p, { method: "DELETE" });

export const api = {
  login: (email: string, password: string) =>
    post<{ access_token: string; user: User }>("/api/auth/login", { email, password }),
  register: (name: string, email: string, password: string) =>
    post<{ access_token: string; user: User }>("/api/auth/register", { name, email, password }),
  me: () => request<User>("/api/auth/me"),

  projects: () => request<ProjectListItem[]>("/api/projects"),
  createProject: (body: { name: string; description?: string; start_date?: string | null; end_date?: string | null }) =>
    post<ProjectListItem>("/api/projects", body),
  deleteProject: (id: number) => del(`/api/projects/${id}`),

  members: (pid: number) => request<Member[]>(`/api/projects/${pid}/members`),
  addMember: (pid: number, body: { email: string; role: string; capacity_points: number }) =>
    post<Member>(`/api/projects/${pid}/members`, body),
  updateMember: (pid: number, uid: number, body: Partial<Pick<Member, "role" | "capacity_points">>) =>
    patch<Member>(`/api/projects/${pid}/members/${uid}`, body),
  removeMember: (pid: number, uid: number) => del(`/api/projects/${pid}/members/${uid}`),

  overview: (pid: number) => request<Overview>(`/api/projects/${pid}/overview`),
  workload: (pid: number) => request<Workload>(`/api/projects/${pid}/workload`),
  tasks: (pid: number) => request<Task[]>(`/api/projects/${pid}/tasks`),
  task: (id: number) => request<Task>(`/api/tasks/${id}`),
  createTask: (pid: number, body: Record<string, unknown>) => post<Task>(`/api/projects/${pid}/tasks`, body),
  updateTask: (id: number, body: Record<string, unknown>) => patch<Task>(`/api/tasks/${id}`, body),
  deleteTask: (id: number) => del(`/api/tasks/${id}`),
  addDependency: (id: number, depends_on_id: number) => post(`/api/tasks/${id}/dependencies`, { depends_on_id }),
  removeDependency: (id: number, dep: number) => del(`/api/tasks/${id}/dependencies/${dep}`),
  updates: (id: number) => request<TaskUpdate[]>(`/api/tasks/${id}/updates`),
  comment: (id: number, comment: string) => post<TaskUpdate>(`/api/tasks/${id}/updates`, { comment }),
  taskRisk: (id: number) => request<any>(`/api/tasks/${id}/risk`),

  whatIf: (pid: number, body: { task_id: number; assignee_id?: number | null; unassign?: boolean; deadline?: string }) =>
    post<WhatIfResult>(`/api/projects/${pid}/what-if`, body),
  feedback: (pid: number, key: string, kind: string, action: "applied" | "dismissed") =>
    post(`/api/projects/${pid}/recommendations/${encodeURIComponent(key)}/feedback`, { kind, action }),
  ask: (pid: number, question: string) => post<AssistantAnswer>(`/api/projects/${pid}/assistant`, { question }),
  model: () => request<ModelInfo>("/api/model"),
};
