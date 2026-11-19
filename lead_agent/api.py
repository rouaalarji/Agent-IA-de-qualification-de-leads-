"""API FastAPI de l'agent de qualification de leads.

    uvicorn lead_agent.api:app --reload      # docs interactives : http://127.0.0.1:8000/docs

Flux :
  POST /leads                     message brut -> l'agent propose une fiche (en attente de validation)
  GET  /reviews?status=...        liste des propositions (en_attente / approuve / rejete)
  POST /reviews/{id}/approve      un humain valide -> écriture dans le CRM
  POST /reviews/{id}/reject       un humain refuse -> rien n'est écrit dans le CRM
  GET  /leads                     fiches du CRM (leads validés)
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from dotenv import load_dotenv

from .crm import CRM
from .graph import build_graph, resume, start

load_dotenv()  

app = FastAPI(title="Agent de qualification de leads", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

crm = CRM(os.getenv("CRM_DB", "crm.db"))
# Les pauses (interrupt) sont sauvegardées sur disque : une validation reste possible après un redémarrage.
checkpointer = SqliteSaver(
    sqlite3.connect(os.getenv("CHECKPOINT_DB", "checkpoints.db"), check_same_thread=False)
)
agent = build_graph(crm, checkpointer=checkpointer)


class MessageIn(BaseModel):
    message: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm": "groq" if os.getenv("GROQ_API_KEY") else "regles"}


@app.post("/leads")
def create_lead(payload: MessageIn) -> dict:
    """Analyse un message. La fiche n'entre PAS dans le CRM : elle attend une validation humaine."""
    thread_id, state, pending = start(agent, payload.message)
    info = {k: v for k, v in state["info"].items() if k != "source_message"}
    if pending:
        crm.create_review(thread_id, payload.message, info, state["result"],
                          state["summary"], state["questions"])
    return {
        "thread_id": thread_id,
        "status": "en_attente_validation" if pending else "contact_requis",
        "info": info,
        "score": state.get("result"),
        "summary": state["summary"],
        "questions": state["questions"],
    }


@app.get("/leads")
def list_leads() -> list[dict]:
    return crm.list_leads()


@app.get("/reviews")
def list_reviews(status: Optional[str] = None) -> list[dict]:
    if status and status not in ("en_attente", "approuve", "rejete"):
        raise HTTPException(400, "status doit valoir en_attente, approuve ou rejete")
    return crm.list_reviews(status)


def _decide(thread_id: str, decision: str) -> dict:
    review = crm.get_review(thread_id)
    if not review:
        raise HTTPException(404, "Proposition introuvable")
    if review["status"] != "en_attente":
        raise HTTPException(409, f"Proposition déjà traitée ({review['status']})")
    state = resume(agent, thread_id, decision)
    lead_id = state["crm"].get("lead_id")
    crm.close_review(thread_id, "approuve" if decision == "approve" else "rejete", lead_id)
    return {"thread_id": thread_id, "crm": state["crm"]}


@app.post("/reviews/{thread_id}/approve")
def approve(thread_id: str) -> dict:
    return _decide(thread_id, "approve")


@app.post("/reviews/{thread_id}/reject")
def reject(thread_id: str) -> dict:
    return _decide(thread_id, "reject")
