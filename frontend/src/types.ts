export type Status = "todo" | "in_progress" | "review" | "done";
export type Priority = "low" | "medium" | "high" | "critical";
export type TaskType = "feature" | "bug" | "chore";
export type RiskLevel = "low" | "medium" | "high" | "overdue";

export interface User { id: number; email: string; name: string }

export interface Factor { feature: string; label: string; impact: number; value: number | null }

export interface Risk {
  task_id: number;
  probability: number;
  level: RiskLevel;
  factors: Factor[];
  mitigating: Factor[];
}

export interface Task {
  id: number;
  project_id: number;
  title: string;
  description: string;
  task_type: TaskType;
  status: Status;
  priority: Priority;
  story_points: number | null;
  assignee_id: number | null;
  assignee_name: string | null;
  start_date: string | null;
  deadline: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  position: number;
  blocked_by: number[];
  blocks: number[];
  is_overdue: boolean;
  risk: Risk | null;
}

export interface ProjectListItem {
  id: number;
  name: string;
  description: string;
  start_date: string | null;
  end_date: string | null;
  is_demo: boolean;
  created_at: string;
  role: "manager" | "member";
  open_tasks: number;
  member_count: number;
  health_score: number | null;
  health_status: string | null;
}

export interface Member {
  user_id: number;
  name: string;
  email: string;
  role: "manager" | "member";
  capacity_points: number;
}

export interface Signal { key: string; label: string; penalty: number; task_ids: number[]; member_ids: number[] }

export interface Health {
  score: number;
  status: "on_track" | "at_risk" | "critical";
  signals: Signal[];
  completion_pct: number;
  time_elapsed_pct: number | null;
}

export interface MemberLoad {
  member_id: number;
  name: string;
  open_tasks: number;
  open_points: number;
  capacity_points: number;
  utilisation: number;
  ratio_to_median: number;
  high_priority_open: number;
  points_due_soon: number;
  overdue: number;
  status: "overloaded" | "balanced" | "underutilised";
  reasons: string[];
  tasks?: Task[];
}

export interface Workload {
  members: MemberLoad[];
  team_median_points: number;
  team_mean_points: number;
  imbalance_ratio: number;
  unassigned_open: number;
}

export interface Flow {
  weekly: { week_ending: string; completed: number; points: number; on_time_pct: number | null }[];
  completed_total: number;
  open_total: number;
  wip: number;
  median_cycle_time_days: number | null;
  median_lead_time_days: number | null;
  deadline_adherence_pct: number | null;
  overdue_rate_pct: number | null;
}

export interface Recommendation {
  id: string;
  kind: string;
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
  evidence: string[];
  task_ids: number[];
  member_ids: number[];
  action: { type: "reassign"; task_id: number; to_member_id: number } | null;
}

export interface ModelBadge {
  version: string;
  data_source: string;
  is_synthetic: boolean;
  algorithm: string;
  warning: string | null;
  thresholds: { high: number; medium: number };
}

export interface Overview {
  project: { id: number; name: string; is_demo: boolean; start_date: string | null; end_date: string | null };
  role: "manager" | "member";
  health: Health;
  health_previous: number | null;
  workload: Workload;
  flow: Flow;
  top_risks: Task[];
  risk_counts: Record<RiskLevel, number>;
  upcoming: Task[];
  recommendations: Recommendation[];
  model: ModelBadge;
}

export interface WhatIfResult {
  task: { task_id: number; before: Risk | null; after: Risk | null };
  changed_tasks: { task_id: number; title: string; before: number | null; after: number | null; level_after: string | null }[];
  health_before: Health;
  health_after: Health;
  health_explanation: string[];
  workload_after: Workload;
}

export interface TaskUpdate {
  id: number;
  kind: string;
  from_value: string | null;
  to_value: string | null;
  comment: string | null;
  user_name: string | null;
  created_at: string;
}

export interface AssistantAnswer {
  answer: string;
  mode: string;
  tools_used: { tool: string; args: Record<string, unknown> }[];
  task_ids: number[];
}

export interface ModelInfo {
  card: Record<string, any>;
  metrics: Record<string, any>;
  thresholds: { high: number; medium: number };
  features: string[];
  reference: Record<string, number>;
}
