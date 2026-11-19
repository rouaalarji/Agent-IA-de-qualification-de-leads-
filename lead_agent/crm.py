"""CRM simulé (SQLite) : création / mise à jour des fiches leads."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .models import LeadInfo, ScoreResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, company TEXT, email TEXT, phone TEXT,
    need TEXT, budget_tnd REAL, timeline TEXT, employees INTEGER,
    score INTEGER, category TEXT, status TEXT, summary TEXT,
    created_at TEXT, updated_at TEXT
);
-- Zone d'attente : propositions de l'agent, en attente de validation humaine.
-- Rien n'entre dans `leads` (le CRM) tant qu'un humain n'a pas approuvé.
CREATE TABLE IF NOT EXISTS reviews (
    thread_id TEXT PRIMARY KEY,
    message TEXT, info_json TEXT, score INTEGER, category TEXT,
    summary TEXT, questions_json TEXT,
    status TEXT NOT NULL DEFAULT 'en_attente',   -- en_attente | approuve | rejete
    lead_id INTEGER, created_at TEXT, decided_at TEXT
);
"""

STATUS_BY_CATEGORY = {
    "chaud": "a_rappeler_24h",
    "tiede": "a_qualifier",
    "froid": "nurturing",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CRM:
    def __init__(self, path: str = "crm.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # Migration douce : bases créées avant l'ajout de la colonne `employees`.
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(leads)")}
        if "employees" not in cols:
            self.conn.execute("ALTER TABLE leads ADD COLUMN employees INTEGER")
            self.conn.commit()

    def find(self, info: LeadInfo) -> Optional[sqlite3.Row]:
        """Retrouve une fiche existante par email, sinon par téléphone."""
        if info.email:
            row = self.conn.execute("SELECT * FROM leads WHERE email = ?", (info.email,)).fetchone()
            if row:
                return row
        if info.phone:
            return self.conn.execute("SELECT * FROM leads WHERE phone = ?", (info.phone,)).fetchone()
        return None

    def upsert(self, info: LeadInfo, result: ScoreResult, summary: str) -> dict:
        """Crée la fiche, ou la met à jour si l'email / le téléphone existe déjà."""
        status = STATUS_BY_CATEGORY[result.category]
        existing = self.find(info)
        now = _now()
        if existing:
            # On conserve les valeurs déjà connues quand le nouveau message ne les contient pas.
            merged = {
                k: getattr(info, k) or existing[k]
                for k in ("name", "company", "email", "phone", "need", "budget_tnd", "employees")
            }
            timeline = info.timeline if info.timeline != "non_precise" else existing["timeline"]
            self.conn.execute(
                "UPDATE leads SET name=?, company=?, email=?, phone=?, need=?, budget_tnd=?, employees=?, "
                "timeline=?, score=?, category=?, status=?, summary=?, updated_at=? WHERE id=?",
                (*merged.values(), timeline, result.score, result.category, status, summary, now, existing["id"]),
            )
            self.conn.commit()
            return {"action": "mis_a_jour", "lead_id": existing["id"], "status": status}

        cur = self.conn.execute(
            "INSERT INTO leads (name, company, email, phone, need, budget_tnd, employees, timeline, "
            "score, category, status, summary, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (info.name, info.company, info.email, info.phone, info.need, info.budget_tnd,
             info.employees, info.timeline, result.score, result.category, status, summary, now, now),
        )
        self.conn.commit()
        return {"action": "cree", "lead_id": cur.lastrowid, "status": status}

    def list_leads(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM leads ORDER BY score DESC, id").fetchall()
        return [dict(r) for r in rows]

    # ---- Zone d'attente (validation humaine) ----

    def create_review(self, thread_id: str, message: str, info: dict, result: dict,
                      summary: str, questions: list[str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO reviews (thread_id, message, info_json, score, category, summary, "
            "questions_json, status, created_at) VALUES (?,?,?,?,?,?,?,'en_attente',?)",
            (thread_id, message, json.dumps(info, ensure_ascii=False), result["score"],
             result["category"], summary, json.dumps(questions, ensure_ascii=False), _now()),
        )
        self.conn.commit()

    @staticmethod
    def _review_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["info"] = json.loads(d.pop("info_json") or "{}")
        d["questions"] = json.loads(d.pop("questions_json") or "[]")
        return d

    def get_review(self, thread_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM reviews WHERE thread_id = ?", (thread_id,)).fetchone()
        return self._review_to_dict(row) if row else None

    def list_reviews(self, status: Optional[str] = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM reviews WHERE status = ? ORDER BY score DESC, created_at", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
        return [self._review_to_dict(r) for r in rows]

    def close_review(self, thread_id: str, status: str, lead_id: Optional[int] = None) -> None:
        self.conn.execute(
            "UPDATE reviews SET status=?, lead_id=?, decided_at=? WHERE thread_id=?",
            (status, lead_id, _now(), thread_id),
        )
        self.conn.commit()
