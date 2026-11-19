from lead_agent.dataset import generate, load, save
from lead_agent.evaluate import evaluate
from lead_agent.extractor import extract_with_rules


def test_dataset_is_deterministic():
    assert generate(50, seed=1) == generate(50, seed=1)
    assert generate(50, seed=1) != generate(50, seed=2)


def test_saved_dataset_roundtrip(tmp_path):
    records = generate(20, seed=3)
    path = tmp_path / "d.jsonl"
    save(records, path)
    assert load(path) == records


def test_gold_is_consistent_with_message():
    for rec in generate(100, seed=5):
        gold = rec["gold"]
        if gold["email"]:
            assert gold["email"] in rec["message"]
        assert rec["gold_has_contact"] == bool(gold["email"] or gold["phone"])


def test_signature_name_is_extracted():
    info = extract_with_rules("Bonjour. Besoin d'un CRM. Mon email : a@b.tn. Cordialement, Anis Khelifi.")
    assert info.name == "Anis Khelifi"


def test_extraction_quality_thresholds():
    """Garde-fou : une régression de l'extraction fera échouer ce test."""
    report = evaluate(generate(300, seed=42))
    fields = report["fields"]
    for f in ("email", "phone", "need"):
        assert fields[f]["recall"] >= 0.97
    assert fields["name"]["recall"] >= 0.85
    assert fields["budget_tnd"]["recall"] >= 0.85
    assert report["routing_accuracy"] >= 0.97
    assert report["category_accuracy"] >= 0.80
    # Les règles ne doivent jamais inventer de valeurs fausses.
    assert all(s["precision"] >= 0.95 for s in fields.values() if s["precision"] is not None)
