"""CLI : traiter un message ou lancer la démo sur des messages d'exemple.

    python -m lead_agent.cli --message "Bonjour, je suis Sami Ben Ali ..."
    python -m lead_agent.cli --demo            # valide automatiquement chaque proposition
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .crm import CRM
from .graph import build_graph, resume, start

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "sample_messages.json"


def _print_result(message: str, state: dict) -> None:
    result = state.get("result")
    print("-" * 70)
    print("Message :", message[:110] + ("..." if len(message) > 110 else ""))
    if result:
        print(f"Score   : {result['score']}/100 ({result['category']})")
        print("Détail  :", "; ".join(result["reasons"]))
    print("Résumé  :", state["summary"])
    for question in state.get("questions", []):
        print("Relance :", question)
    print("CRM     :", json.dumps(state.get("crm", {"action": "en_attente_validation"}), ensure_ascii=False))


def _process(app, message: str, auto_approve: bool) -> None:
    thread_id, state, pending = start(app, message)
    if pending:
        if auto_approve:
            decision = "approve"
        else:
            _print_result(message, state)
            decision = "approve" if input("Valider cette fiche dans le CRM ? [o/N] ").lower() in ("o", "y") else "reject"
        state = resume(app, thread_id, decision)
    _print_result(message, state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent de qualification de leads")
    parser.add_argument("--message", help="Message client à traiter")
    parser.add_argument("--demo", action="store_true", help="Traiter les messages d'exemple (validation automatique)")
    parser.add_argument("--db", default="crm.db", help="Chemin de la base SQLite (CRM simulé)")
    args = parser.parse_args()

    crm = CRM(args.db)
    app = build_graph(crm)

    if args.demo:
        for message in json.loads(SAMPLES.read_text(encoding="utf-8")):
            _process(app, message, auto_approve=True)
    elif args.message:
        _process(app, args.message, auto_approve=False)
    else:
        parser.error("utilise --message ou --demo")

    print("\n=== Fiches CRM (triées par score) ===")
    for lead in crm.list_leads():
        print(f"#{lead['id']} {lead['score']:>3} {lead['category']:<5} {lead['status']:<15} "
              f"{lead['name'] or '?'} | {lead['company'] or '-'} | {lead['email'] or lead['phone']}")


if __name__ == "__main__":
    main()
