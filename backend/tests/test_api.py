"""API tests (need the backend requirements installed: pip install -r requirements.txt)."""
import os
import tempfile

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"  # force offline assistant

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        seed(reset=True)
        yield c


def login(client, email="priya@demo.foresight", pw="demo1234"):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_auth_required(client):
    assert client.get("/api/projects").status_code == 401


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "priya@demo.foresight", "password": "nope"})
    assert r.status_code == 401


def test_register_and_empty_projects(client):
    r = client.post("/api/auth/register", json={"email": "new@x.io", "name": "New Person", "password": "longpassword"})
    assert r.status_code == 201
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/projects", headers=h).json() == []


def test_non_member_cannot_see_project(client):
    r = client.post("/api/auth/register", json={"email": "out@x.io", "name": "Outsider", "password": "longpassword"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.get("/api/projects", headers=login(client)).json()[0]["id"]
    assert client.get(f"/api/projects/{pid}/overview", headers=h).status_code == 404


def test_overview_and_whatif(client):
    h = login(client)
    pid = client.get("/api/projects", headers=h).json()[0]["id"]
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert 0 <= ov["health"]["score"] <= 100
    assert ov["top_risks"] and ov["recommendations"]
    assert ov["model"]["is_synthetic"] is True
    tasks = client.get(f"/api/projects/{pid}/tasks", headers=h).json()
    pay = next(t for t in tasks if t["title"].startswith("Payment"))
    members = client.get(f"/api/projects/{pid}/members", headers=h).json()
    meera = next(m for m in members if m["name"].startswith("Meera"))
    sim = client.post(f"/api/projects/{pid}/what-if", headers=h,
                      json={"task_id": pay["id"], "assignee_id": meera["user_id"]}).json()
    assert sim["task"]["after"]["probability"] < sim["task"]["before"]["probability"]
    # simulation must not change the database
    again = client.get(f"/api/tasks/{pay['id']}", headers=h).json()
    assert again["assignee_id"] == pay["assignee_id"]


def test_task_lifecycle_and_dependency_cycle(client):
    h = login(client)
    pid = client.get("/api/projects", headers=h).json()[0]["id"]
    a = client.post(f"/api/projects/{pid}/tasks", headers=h, json={"title": "Task A", "story_points": 3}).json()
    b = client.post(f"/api/projects/{pid}/tasks", headers=h,
                    json={"title": "Task B", "depends_on": [a["id"]]}).json()
    assert b["blocked_by"] == [a["id"]]
    r = client.post(f"/api/tasks/{a['id']}/dependencies", headers=h, json={"depends_on_id": b["id"]})
    assert r.status_code == 422  # cycle
    r = client.patch(f"/api/tasks/{a['id']}", headers=h, json={"status": "done"})
    assert r.json()["completed_at"] is not None
    kinds = [u["kind"] for u in client.get(f"/api/tasks/{a['id']}/updates", headers=h).json()]
    assert "status" in kinds


def test_member_cannot_delete_others_task(client):
    h_mgr = login(client)
    pid = client.get("/api/projects", headers=h_mgr).json()[0]["id"]
    t = client.post(f"/api/projects/{pid}/tasks", headers=h_mgr, json={"title": "Manager task"}).json()
    h_dev = login(client, "dev@demo.foresight")
    assert client.delete(f"/api/tasks/{t['id']}", headers=h_dev).status_code == 403


def test_assistant_offline_answers_with_task_ids(client):
    h = login(client)
    pid = client.get("/api/projects", headers=h).json()[0]["id"]
    r = client.post(f"/api/projects/{pid}/assistant", headers=h, json={"question": "who is overloaded?"}).json()
    assert r["mode"] == "offline" and "Rahul" in r["answer"]
