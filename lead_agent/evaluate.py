"""Évaluation de l'extraction et du scoring sur le jeu synthétique annoté.

    python -m lead_agent.evaluate                      # résumé
    python -m lead_agent.evaluate --errors 5           # + exemples d'erreurs
    python -m lead_agent.evaluate --out reports/evaluation.md
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Callable

from .dataset import DEFAULT_OUT, load
from .extractor import extract_with_rules
from .models import LeadInfo
from .scoring import score_lead

FIELDS = ["name", "company", "email", "phone", "need", "budget_tnd", "timeline"]
CATEGORIES = ["chaud", "tiede", "froid"]


def _norm(field: str, value):
    """Valeur comparable, ou None si le champ est absent."""
    if field == "timeline":
        return None if value in (None, "non_precise") else value
    if field == "need":
        if not value:
            return None
        items = value if isinstance(value, list) else value.split(", ")
        return frozenset(items)
    return value or None


def evaluate(records: list[dict], extractor: Callable[[str], LeadInfo] = extract_with_rules) -> dict:
    stats = {f: Counter() for f in FIELDS}
    confusion: Counter = Counter()
    routing_ok = 0
    errors: list[dict] = []

    for rec in records:
        info = extractor(rec["message"])
        wrong: list[str] = []
        for f in FIELDS:
            gold = _norm(f, rec["gold"][f])
            pred = _norm(f, getattr(info, f))
            stats[f]["gold"] += gold is not None
            stats[f]["pred"] += pred is not None
            if gold is not None and gold == pred:
                stats[f]["correct"] += 1
            elif gold != pred:
                wrong.append(f)
        predicted_category = score_lead(info).category
        confusion[(rec["gold_category"], predicted_category)] += 1
        routing_ok += info.has_contact == rec["gold_has_contact"]
        if wrong or predicted_category != rec["gold_category"]:
            errors.append({"id": rec["id"], "message": rec["message"], "wrong_fields": wrong,
                           "gold_category": rec["gold_category"], "pred_category": predicted_category})

    n = len(records)
    fields = {}
    for f, s in stats.items():
        fields[f] = {
            "gold": s["gold"],
            "recall": s["correct"] / s["gold"] if s["gold"] else None,
            "precision": s["correct"] / s["pred"] if s["pred"] else None,
        }
    cat_ok = sum(c for (g, p), c in confusion.items() if g == p)
    return {"n": n, "fields": fields, "category_accuracy": cat_ok / n,
            "routing_accuracy": routing_ok / n, "confusion": confusion, "errors": errors}


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f} %"


def to_markdown(report: dict) -> str:
    lines = [f"Évaluation sur {report['n']} messages synthétiques (extraction par règles).", "",
             "| Champ | Présent dans | Rappel | Précision |", "|---|---:|---:|---:|"]
    for f, s in report["fields"].items():
        lines.append(f"| {f} | {s['gold']} | {_pct(s['recall'])} | {_pct(s['precision'])} |")
    lines += ["", f"- Routage (contact présent / absent) : **{_pct(report['routing_accuracy'])}**",
              f"- Catégorie de lead (chaud / tiède / froid) : **{_pct(report['category_accuracy'])}**", "",
              "Matrice de confusion (lignes = vérité, colonnes = prédiction) :", "",
              "| | " + " | ".join(CATEGORIES) + " |", "|---|" + "---:|" * len(CATEGORIES)]
    for g in CATEGORIES:
        lines.append(f"| {g} | " + " | ".join(str(report["confusion"][(g, p)]) for p in CATEGORIES) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Évalue l'extraction et le scoring")
    parser.add_argument("--data", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--errors", type=int, default=0, help="Nombre d'exemples d'erreurs à afficher")
    parser.add_argument("--out", type=Path, help="Écrire le rapport Markdown dans ce fichier")
    args = parser.parse_args()

    report = evaluate(load(args.data))
    text = to_markdown(report)
    print(text)
    if args.errors:
        print("\n=== Exemples d'erreurs ===")
        for e in report["errors"][: args.errors]:
            print(f"\n#{e['id']} champs faux : {e['wrong_fields']} | catégorie {e['gold_category']} -> {e['pred_category']}")
            print(e["message"])
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nRapport écrit dans {args.out}")


if __name__ == "__main__":
    main()
