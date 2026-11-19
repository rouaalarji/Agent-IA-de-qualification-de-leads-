import pytest

from lead_agent.crm import CRM
from lead_agent.extractor import extract_with_rules
from lead_agent.graph import build_graph, process_message, resume, start
from lead_agent.scoring import score_lead

HOT = (
    "Bonjour, je m'appelle Sami Ben Ali, de la société Medtech Sfax. Nous voulons un CRM, "
    "budget 25 000 DT, c'est urgent. Email : sami@medtech.tn, tél 98 123 456."
)


@pytest.fixture
def app(tmp_path):
    crm = CRM(str(tmp_path / "test.db"))
    # On force l'extraction par règles pour des tests déterministes.
    return build_graph(crm, extractor=extract_with_rules), crm


def test_extraction_rules():
    info = extract_with_rules(HOT)
    assert info.name == "Sami Ben Ali"
    assert info.company == "Medtech Sfax"
    assert info.email == "sami@medtech.tn"
    assert info.phone == "98123456"
    assert info.budget_tnd == 25000
    assert info.timeline == "urgent"
    assert "CRM" in info.need


def test_budget_with_k_suffix():
    assert extract_with_rules("Notre budget est de 15k DT").budget_tnd == 15000


def test_score_hot_lead():
    result = score_lead(extract_with_rules(HOT))
    assert result.category == "chaud"
    assert result.score >= 70


def test_score_empty_message_is_cold():
    result = score_lead(extract_with_rules("Bonjour, vous faites quoi ?"))
    assert result.category == "froid"
    assert result.score == 0


def test_graph_creates_crm_record(app):
    agent, crm = app
    state = process_message(agent, HOT, auto_approve=True)
    assert state["crm"]["action"] == "cree"
    assert state["crm"]["status"] == "a_rappeler_24h"
    assert len(crm.list_leads()) == 1


def test_graph_pauses_before_writing_to_crm(app):
    agent, crm = app
    thread_id, state, pending = start(agent, HOT)
    assert pending is True
    assert crm.list_leads() == []  # rien n'est écrit tant qu'un humain n'a pas validé
    assert "crm" not in state
    assert state["result"]["category"] == "chaud"


def test_human_approval_writes_to_crm(app):
    agent, crm = app
    thread_id, _, _ = start(agent, HOT)
    state = resume(agent, thread_id, "approve")
    assert state["crm"]["action"] == "cree"
    assert len(crm.list_leads()) == 1


def test_human_rejection_writes_nothing(app):
    agent, crm = app
    thread_id, _, _ = start(agent, HOT)
    state = resume(agent, thread_id, "reject")
    assert state["crm"]["action"] == "rejete"
    assert crm.list_leads() == []


def test_resume_rejects_invalid_decision(app):
    agent, _ = app
    thread_id, _, _ = start(agent, HOT)
    with pytest.raises(ValueError):
        resume(agent, thread_id, "peut-etre")


def test_follow_up_questions_for_missing_info(app):
    agent, _ = app
    _, state, pending = start(agent, "Je suis Amira Trabelsi, cherche un site web. Email : amira@x.tn")
    assert pending
    assert set(state["missing"]) == {"budget", "timeline", "company_size"}
    assert len(state["questions"]) == 3
    assert any("budget" in q.lower() for q in state["questions"])


def test_graph_without_contact_asks_for_details(app):
    agent, crm = app
    state = process_message(agent, "Bonjour, je cherche un site web.")
    assert state["crm"]["action"] == "contact_requis"
    assert "contact" in state["missing"]
    assert crm.list_leads() == []


def test_graph_updates_existing_lead(app):
    agent, crm = app
    process_message(agent, "Je suis Amira Trabelsi, cherche un site web. Email : amira@x.tn", auto_approve=True)
    state = process_message(agent, "Budget 8000 DT, urgent. Email : amira@x.tn", auto_approve=True)
    assert state["crm"]["action"] == "mis_a_jour"
    leads = crm.list_leads()
    assert len(leads) == 1
    assert leads[0]["name"] == "Amira Trabelsi"  # conservé du 1er message
    assert leads[0]["budget_tnd"] == 8000
    # Le score tient compte des infos du 1er message (besoin) fusionnées avec le 2e.
    assert state["result"]["score"] == 20 + 25 + 15 + 5  # budget 8000, besoin, urgent, email
    assert "Amira Trabelsi" in state["summary"]
