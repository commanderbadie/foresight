"""SYNTHETIC demo project used for the live demonstration.

This is application-generated demo data, NOT a public dataset and NOT used for
training. It is designed to contain realistic situations the system should
detect: an overloaded member, an overdue task blocking others, an urgent
unstarted task, an unassigned task and a history of past (sometimes late) work.
All dates are relative to "now" so the demo always looks current.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .state import MemberState, ProjectState, TaskState, utcnow

MEMBERS = [
    # key, name, email, role, capacity (story points), historical lateness tendency
    ("priya", "Priya Shah", "priya@demo.foresight", "manager", 13, 0.15),
    ("rahul", "Rahul Mehta", "rahul@demo.foresight", "member", 13, 0.25),
    ("aisha", "Aisha Khan", "aisha@demo.foresight", "member", 13, 0.20),
    ("karan", "Karan Patel", "karan@demo.foresight", "member", 13, 0.45),
    ("meera", "Meera Iyer", "meera@demo.foresight", "member", 13, 0.15),
    ("dev", "Dev Joshi", "dev@demo.foresight", "member", 10, 0.30),
]

HISTORY_TITLES = [
    "Set up CI pipeline", "Design login screen", "Auth API endpoints", "Password reset flow",
    "Onboarding carousel", "Profile screen", "Push notification service", "Settings screen",
    "Crash reporting setup", "Analytics events v1", "Search API", "Search results UI",
    "Image upload service", "Image cropping UI", "Unit tests for auth", "Dark mode theme",
    "Localization framework", "Hindi translations", "Accessibility audit fixes", "Cart API",
    "Cart screen", "Wishlist API", "Wishlist screen", "Order history API", "Order history UI",
    "Rate limiting middleware", "Caching layer for catalog", "Catalog listing UI",
    "Product detail screen", "Reviews API", "Reviews UI", "Error states design",
    "Empty states design", "Deep linking", "App icon & splash", "Feature flags service",
    "Load test auth service", "Fix token refresh bug", "Fix image upload crash on Android",
    "Fix cart total rounding bug", "Refactor network layer", "API docs v1",
]

# key, title, type, priority, points, assignee, status, start_offset_days, deadline_offset_days, blocked_by(keys), desc_len
OPEN_TASKS = [
    ("db_migration", "Database migration to v2 schema", "chore", "critical", 8, "rahul", "in_progress", -9, -1, [], 900),
    ("api_v2", "API v2 endpoints for orders", "feature", "high", 5, "aisha", "todo", -2, 6, ["db_migration"], 600),
    ("offline_sync", "Offline sync for cart", "feature", "high", 8, "karan", "todo", -1, 8, ["db_migration"], 450),
    ("data_export", "User data export (GDPR)", "feature", "medium", 3, "dev", "todo", 0, 9, ["api_v2"], 300),
    ("payment", "Payment gateway integration", "feature", "critical", 8, "rahul", "in_progress", -6, 1.5, [], 1100),
    ("coupon", "Coupon codes at checkout", "feature", "medium", 5, "rahul", "todo", -1, 7, ["payment"], 250),
    ("receipt_email", "Order receipt emails", "feature", "low", 3, "rahul", "todo", 0, 10, [], 120),
    ("perf_catalog", "Catalog scroll performance", "chore", "medium", 3, "rahul", "todo", 0, 12, [], 80),
    ("admin_refunds", "Admin refunds panel", "feature", "medium", 5, "rahul", "todo", 1, 14, [], 200),
    ("push_prefs", "Notification preferences", "feature", "low", 2, "meera", "in_progress", -2, 4, [], 150),
    ("a11y_checkout", "Accessibility pass on checkout", "chore", "medium", 3, "meera", "todo", 0, 11, ["payment"], 300),
    ("crash_ios", "Fix crash on iOS 17 when opening camera", "bug", "high", 3, "karan", "in_progress", -3, 2, [], 700),
    ("address_book", "Saved addresses", "feature", "medium", 5, "karan", "review", -5, 3, [], 350),
    ("delivery_tracking", "Delivery tracking screen", "feature", "high", 8, "aisha", "in_progress", -4, 5, [], 520),
    ("tracking_api", "Tracking webhook ingestion", "feature", "medium", 5, "aisha", "todo", 0, 9, [], 260),
    ("store_screens", "App store screenshots & listing", "chore", "high", 2, None, "todo", 0, 5, [], 90),
    ("release_notes", "Release notes & changelog", "chore", "low", 1, "priya", "todo", 3, 18, [], 60),
    ("beta_rollout", "Beta rollout to 5% users", "chore", "high", 3, "priya", "todo", 5, 16, ["payment", "db_migration"], 400),
    ("qa_regression", "Full QA regression run", "chore", "high", 5, "dev", "todo", 7, 15, ["api_v2", "payment"], 380),
    ("bug_cart_badge", "Cart badge count out of sync", "bug", "medium", 2, "dev", "in_progress", -2, 3, [], 210),
    ("bug_rtl", "Layout breaks in RTL languages", "bug", "low", 2, "meera", "todo", 0, 13, [], 180),
]


def build_demo_spec(now: datetime | None = None, seed: int = 11) -> dict:
    """Return plain dicts (used both for DB seeding and for tests)."""
    now = now or utcnow()
    rng = random.Random(seed)
    project = {
        "name": "Atlas Mobile Launch",
        "description": "Shopping app v2 launch: checkout, delivery tracking and data-platform migration. "
                       "(Synthetic demo data generated by Foresight.)",
        "start_date": now - timedelta(days=42),
        "end_date": now + timedelta(days=21),
    }
    members = [{"key": k, "name": n, "email": e, "role": r, "capacity_points": c, "late_tendency": lt}
               for k, n, e, r, c, lt in MEMBERS]
    workers = [m for m in members if m["key"] != "priya"] + [members[0]]
    tasks = []
    for i, title in enumerate(HISTORY_TITLES):
        m = workers[i % len(workers)]
        created = now - timedelta(days=42 - i * 0.8 + rng.uniform(0, 2))
        start = created + timedelta(days=rng.uniform(0, 1))
        window = rng.choice([3, 4, 5, 7, 7, 10])
        deadline = start + timedelta(days=window)
        pts = rng.choice([1, 2, 3, 3, 5, 5, 8])
        late = rng.random() < m["late_tendency"] + (0.15 if pts >= 8 else 0)
        completed = deadline + timedelta(days=rng.uniform(0.5, 3)) if late else deadline - timedelta(days=rng.uniform(0, window * 0.5))
        completed = min(completed, now - timedelta(hours=2))
        started = start + timedelta(days=rng.uniform(0, 1.5))
        if started >= completed:
            started = completed - timedelta(hours=6)
        tasks.append({
            "key": f"h{i}", "title": title, "task_type": "bug" if title.startswith("Fix") else "feature",
            "priority": rng.choice(["low", "medium", "medium", "high"]), "story_points": pts,
            "assignee": m["key"], "status": "done", "created_at": created, "start_date": start,
            "deadline": deadline, "started_at": started, "completed_at": completed,
            "description": f"{title}. " * rng.randint(2, 12), "blocked_by": [], "reassign_count": 0,
        })
    for key, title, typ, prio, pts, who, status, s_off, d_off, blocked, dlen in OPEN_TASKS:
        start = now + timedelta(days=s_off)
        created = start - timedelta(days=rng.uniform(0.5, 3))
        tasks.append({
            "key": key, "title": title, "task_type": typ, "priority": prio, "story_points": pts,
            "assignee": who, "status": status, "created_at": created, "start_date": start,
            "deadline": now + timedelta(days=d_off),
            "started_at": (now - timedelta(days=max(-s_off - 0.5, 0.2))) if status in ("in_progress", "review") else None,
            "completed_at": None, "description": ("Details. " * (dlen // 9)), "blocked_by": blocked,
            "reassign_count": 1 if key == "payment" else 0,
        })
    return {"project": project, "members": members, "tasks": tasks}


def build_demo_state(now: datetime | None = None) -> ProjectState:
    spec = build_demo_spec(now)
    now = now or utcnow()
    ids = {m["key"]: i + 1 for i, m in enumerate(spec["members"])}
    tids = {t["key"]: i + 1 for i, t in enumerate(spec["tasks"])}
    members = {ids[m["key"]]: MemberState(ids[m["key"]], m["name"], m["capacity_points"]) for m in spec["members"]}
    tasks = {}
    for t in spec["tasks"]:
        tasks[tids[t["key"]]] = TaskState(
            id=tids[t["key"]], title=t["title"], status=t["status"], priority=t["priority"],
            task_type=t["task_type"], story_points=t["story_points"],
            assignee_id=ids.get(t["assignee"]) if t["assignee"] else None,
            created_at=t["created_at"], deadline=t["deadline"], start_date=t["start_date"],
            started_at=t["started_at"], completed_at=t["completed_at"],
            description_len=len(t["description"]), reassign_count=t["reassign_count"],
            blocked_by=[tids[b] for b in t["blocked_by"]],
        )
    p = spec["project"]
    return ProjectState(1, p["name"], now, members, tasks, p["start_date"], p["end_date"])
