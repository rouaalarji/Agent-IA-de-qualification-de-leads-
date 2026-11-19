from lead_agent.models import LeadInfo
from lead_agent.scoring import score_lead


def lead(**kw) -> LeadInfo:
    return LeadInfo(source_message="", **kw)


def test_maximum_score_is_100():
    info = lead(email="a@b.tn", phone="98123456", need="CRM", budget_tnd=50_000,
                timeline="urgent", employees=500)
    result = score_lead(info)
    assert result.score == 100  # 30 + 25 + 20 + 15 + 10
    assert result.category == "chaud"


def test_budget_tiers():
    assert score_lead(lead(budget_tnd=25_000)).score == 30
    assert score_lead(lead(budget_tnd=8_000)).score == 20
    assert score_lead(lead(budget_tnd=1_000)).score == 10


def test_company_size_categories():
    assert lead(employees=5).company_size == "petite"
    assert lead(employees=50).company_size == "moyenne"
    assert lead(employees=500).company_size == "grande"
    assert lead().company_size is None
    assert score_lead(lead(employees=500)).score == 20
    assert score_lead(lead(employees=50)).score == 13
    assert score_lead(lead(employees=5)).score == 6


def test_reasons_explain_the_score():
    result = score_lead(lead(need="CRM", employees=300))
    assert any("besoin" in r for r in result.reasons)
    assert any("grande" in r for r in result.reasons)
