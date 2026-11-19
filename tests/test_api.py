import pytest
from fastapi.testclient import TestClient

HOT = ("Bonjour, je m'appelle Sami Ben Ali, de la société Medtech Sfax. Nous voulons un CRM, "
       "budget 25 000 DT, c'est urgent. Email : sami@medtech.tn")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_DB", str(tmp_path / "crm.db"))
    monkeypatch.setenv("CHECKPOINT_DB", str(tmp_path / "cp.db"))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import importlib
    from lead_agent import api
    importlib.reload(api)  # recrée le CRM et le checkpointer dans le dossier temporaire
    return TestClient(api.app)


def test_post_lead_waits_for_validation(client):
    r = client.post("/leads", json={"message": HOT})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "en_attente_validation"
    assert client.get("/leads").json() == []  # pas encore dans le CRM
    pending = client.get("/reviews", params={"status": "en_attente"}).json()
    assert len(pending) == 1 and pending[0]["thread_id"] == body["thread_id"]


def test_approve_writes_to_crm(client):
    tid = client.post("/leads", json={"message": HOT}).json()["thread_id"]
    r = client.post(f"/reviews/{tid}/approve")
    assert r.status_code == 200 and r.json()["crm"]["action"] == "cree"
    leads = client.get("/leads").json()
    assert len(leads) == 1 and leads[0]["name"] == "Sami Ben Ali"
    assert client.get("/reviews", params={"status": "approuve"}).json()[0]["lead_id"] == leads[0]["id"]


def test_reject_keeps_crm_empty(client):
    tid = client.post("/leads", json={"message": HOT}).json()["thread_id"]
    assert client.post(f"/reviews/{tid}/reject").json()["crm"]["action"] == "rejete"
    assert client.get("/leads").json() == []
    assert len(client.get("/reviews", params={"status": "rejete"}).json()) == 1


def test_cannot_decide_twice(client):
    tid = client.post("/leads", json={"message": HOT}).json()["thread_id"]
    client.post(f"/reviews/{tid}/approve")
    assert client.post(f"/reviews/{tid}/reject").status_code == 409


def test_unknown_review_is_404(client):
    assert client.post("/reviews/inconnu/approve").status_code == 404


def test_message_without_contact_asks_for_details(client):
    body = client.post("/leads", json={"message": "Bonjour, je cherche un site web."}).json()
    assert body["status"] == "contact_requis"
    assert any("email" in q for q in body["questions"])
    assert client.get("/reviews").json() == []
