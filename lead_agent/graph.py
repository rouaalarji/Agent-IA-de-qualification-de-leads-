"""Graphe LangGraph de qualification d'un lead.

    extract ─► merge ─► check_fields ─┬─ (ni email ni téléphone) ─► request_contact ─► fin
                                      └─► score ─► summarize ─► human_review ⏸ (interrupt)
                                                                   ├─ approuvé ─► update_crm ─► fin
                                                                   └─ rejeté   ─► reject ─────► fin

`human_review` utilise `interrupt()` : le graphe s'arrête et son état est sauvegardé par le
checkpointer. L'agent n'écrit dans le CRM qu'après `Command(resume="approve")`.
"""

from __future__ import annotations

import uuid
from typing import Callable, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .crm import CRM
from .extractor import extract_lead
from .models import LeadInfo, ScoreResult
from .scoring import score_lead

CATEGORY_LABEL = {"chaud": "🔥 chaud", "tiede": "🌤 tiède", "froid": "❄ froid"}
NEXT_ACTION = {
    "chaud": "Rappeler sous 24 h et proposer un rendez-vous de cadrage.",
    "tiede": "Envoyer une présentation et qualifier le budget / l'échéance.",
    "froid": "Ajouter à la séquence de nurturing (contenu, newsletter).",
}

# Champ manquant -> question de relance à poser au client.
FOLLOW_UP_QUESTIONS = {
    "contact": "Pouvez-vous nous donner une adresse email ou un numéro de téléphone pour vous recontacter ?",
    "need": "Quel est votre besoin précis (CRM, site web, application mobile, automatisation...) ?",
    "budget": "Quel budget envisagez-vous pour ce projet (en TND) ?",
    "timeline": "Pour quand souhaitez-vous démarrer ou livrer le projet ?",
    "company_size": "Combien de personnes travaillent dans votre entreprise ?",
}


class LeadState(TypedDict, total=False):
    # Les objets sont stockés en dictionnaires simples : le checkpointer peut les sérialiser.
    message: str
    info: dict
    result: dict
    summary: str
    missing: list[str]
    questions: list[str]
    decision: str
    crm: dict


def missing_fields(info: LeadInfo) -> list[str]:
    missing = []
    if not info.has_contact:
        missing.append("contact")
    if not info.need:
        missing.append("need")
    if not info.budget_tnd:
        missing.append("budget")
    if info.timeline == "non_precise":
        missing.append("timeline")
    if not info.employees:
        missing.append("company_size")
    return missing


def build_summary(info: LeadInfo, result: ScoreResult) -> str:
    who = info.name or "Contact inconnu"
    if info.company:
        who += f" ({info.company})"
    parts = [f"{who} — lead {CATEGORY_LABEL[result.category]} (score {result.score}/100)."]
    if info.need:
        parts.append(f"Besoin : {info.need}.")
    if info.budget_tnd:
        parts.append(f"Budget : {info.budget_tnd:,.0f} TND.")
    if info.company_size:
        parts.append(f"Entreprise {info.company_size} ({info.employees} personnes).")
    if info.timeline != "non_precise":
        parts.append(f"Échéance : {info.timeline.replace('_', ' ')}.")
    parts.append(f"Action suivante : {NEXT_ACTION[result.category]}")
    return " ".join(parts)


def build_graph(crm: CRM, extractor: Callable[[str], LeadInfo] = extract_lead, checkpointer=None):
    """Construit et compile le graphe. L'extracteur est injectable (tests, LLM...)."""

    def extract(state: LeadState) -> LeadState:
        return {"info": extractor(state["message"]).model_dump()}

    def merge(state: LeadState) -> LeadState:
        # Lead déjà connu : on complète le nouveau message avec la fiche existante,
        # pour que le score et le résumé reflètent tout ce qu'on sait du lead.
        info = LeadInfo(**state["info"])
        row = crm.find(info)
        if not row:
            return {}
        data = info.model_dump()
        for key in ("name", "company", "email", "phone", "need", "budget_tnd", "employees"):
            data[key] = data[key] or row[key]
        if data["timeline"] == "non_precise" and row["timeline"]:
            data["timeline"] = row["timeline"]
        return {"info": data}

    def check_fields(state: LeadState) -> LeadState:
        missing = missing_fields(LeadInfo(**state["info"]))
        return {"missing": missing, "questions": [FOLLOW_UP_QUESTIONS[m] for m in missing]}

    def route_after_check(state: LeadState) -> str:
        # Sans moyen de contact, inutile de créer une fiche : on demande les coordonnées.
        return "request_contact" if "contact" in state["missing"] else "score"

    def request_contact(state: LeadState) -> LeadState:
        return {
            "summary": "Message sans email ni téléphone : demander les coordonnées avant de créer la fiche.",
            "crm": {"action": "contact_requis", "lead_id": None, "status": "en_attente"},
        }

    def score(state: LeadState) -> LeadState:
        return {"result": score_lead(LeadInfo(**state["info"])).model_dump()}

    def summarize(state: LeadState) -> LeadState:
        info, result = LeadInfo(**state["info"]), ScoreResult(**state["result"])
        return {"summary": build_summary(info, result)}

    def human_review(state: LeadState) -> LeadState:
        # Le graphe s'arrête ici jusqu'à ce qu'un humain réponde "approve" ou "reject".
        decision = interrupt({
            "summary": state["summary"],
            "score": state["result"]["score"],
            "category": state["result"]["category"],
            "questions": state["questions"],
        })
        return {"decision": decision}

    def route_after_review(state: LeadState) -> str:
        return "update_crm" if state["decision"] == "approve" else "reject"

    def update_crm(state: LeadState) -> LeadState:
        info, result = LeadInfo(**state["info"]), ScoreResult(**state["result"])
        return {"crm": crm.upsert(info, result, state["summary"])}

    def reject(state: LeadState) -> LeadState:
        return {"crm": {"action": "rejete", "lead_id": None, "status": "rejete"}}

    graph = StateGraph(LeadState)
    for name, fn in [("extract", extract), ("merge", merge), ("check_fields", check_fields),
                     ("request_contact", request_contact), ("score", score), ("summarize", summarize),
                     ("human_review", human_review), ("update_crm", update_crm), ("reject", reject)]:
        graph.add_node(name, fn)

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "merge")
    graph.add_edge("merge", "check_fields")
    graph.add_conditional_edges("check_fields", route_after_check,
                                {"request_contact": "request_contact", "score": "score"})
    graph.add_edge("score", "summarize")
    graph.add_edge("summarize", "human_review")
    graph.add_conditional_edges("human_review", route_after_review,
                                {"update_crm": "update_crm", "reject": "reject"})
    graph.add_edge("request_contact", END)
    graph.add_edge("update_crm", END)
    graph.add_edge("reject", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def start(app, message: str, thread_id: Optional[str] = None) -> tuple[str, LeadState, bool]:
    """Lance le graphe. Retourne (thread_id, état, en_attente_de_validation)."""
    thread_id = thread_id or uuid.uuid4().hex
    app.invoke({"message": message}, _config(thread_id))
    snapshot = app.get_state(_config(thread_id))
    return thread_id, dict(snapshot.values), bool(snapshot.next)


def resume(app, thread_id: str, decision: str) -> LeadState:
    """Reprend un graphe en pause avec la décision humaine ("approve" ou "reject")."""
    if decision not in ("approve", "reject"):
        raise ValueError("decision doit valoir 'approve' ou 'reject'")
    app.invoke(Command(resume=decision), _config(thread_id))
    return dict(app.get_state(_config(thread_id)).values)


def process_message(app, message: str, auto_approve: bool = False) -> LeadState:
    """Raccourci : lance le graphe ; avec auto_approve, valide automatiquement (démo, tests)."""
    thread_id, state, pending = start(app, message)
    if pending and auto_approve:
        return resume(app, thread_id, "approve")
    return state
