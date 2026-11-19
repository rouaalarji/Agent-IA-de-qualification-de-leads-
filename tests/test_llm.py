import json

import httpx
import pytest

from lead_agent.extractor import extract_lead, extract_with_llm

MESSAGE = "bonjour, je suis amira trabelsi (amira@x.tn), il nous faut un CRM, quinze mille dinars, dans 3 mois"


def fake_groq(content: str, status: int = 200) -> httpx.Client:
    """Faux serveur Groq : aucun appel réseau, aucune clé réelle nécessaire."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert body["temperature"] == 0
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")


def test_llm_valid_json_is_parsed():
    content = json.dumps({"name": "Amira Trabelsi", "company": None, "email": "amira@x.tn", "phone": None,
                          "need": "CRM", "budget_tnd": 15000, "timeline": "moyen_terme", "employees": 40})
    info = extract_with_llm(MESSAGE, client=fake_groq(content))
    assert info.name == "Amira Trabelsi"
    assert info.budget_tnd == 15000
    assert info.timeline == "moyen_terme"
    assert info.company_size == "moyenne"


def test_llm_invalid_values_are_rejected_by_pydantic():
    content = json.dumps({"timeline": "bientot", "budget_tnd": -5})
    with pytest.raises(ValueError):
        extract_with_llm(MESSAGE, client=fake_groq(content))


def test_llm_non_json_is_rejected():
    with pytest.raises(ValueError):
        extract_with_llm(MESSAGE, client=fake_groq("Voici le résultat : pas du JSON"))


def test_email_is_verified_by_regex_not_invented_by_llm():
    content = json.dumps({"email": "invente@faux.tn", "need": "CRM"})
    info = extract_with_llm(MESSAGE, client=fake_groq(content))
    assert info.email == "amira@x.tn"  # l'email réellement présent dans le message


def test_fallback_to_rules_when_llm_fails(monkeypatch):
    def boom(message, client=None):
        raise httpx.ConnectError("réseau coupé")
    monkeypatch.setattr("lead_agent.extractor.extract_with_llm", boom)
    info = extract_lead("Je suis Sami Ben Ali, besoin d'un CRM, sami@x.tn")
    assert info.name == "Sami Ben Ali"  # extrait par les règles


def test_no_key_uses_rules(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    def never(*a, **k):
        raise AssertionError("le LLM ne doit pas être appelé sans clé")
    monkeypatch.setattr("lead_agent.extractor.extract_with_llm", never)
    assert extract_lead("Besoin d'un CRM. a@b.tn").need == "CRM"
