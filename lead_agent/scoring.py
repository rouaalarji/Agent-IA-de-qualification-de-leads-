"""Calcul du score d'un lead (0-100), transparent et explicable.

Barème (total = 100) : budget 30 · besoin 25 · taille de l'entreprise 20 · échéance 15 · contact 10.
Les constantes sont regroupées ici : change-les pour adapter le barème.
"""

from __future__ import annotations

from .models import LeadInfo, ScoreResult

POINTS_BUDGET = [(20_000, 30), (5_000, 20), (1, 10)]  # (seuil en TND, points) -> max 30
POINTS_NEED = 25
POINTS_SIZE = {"grande": 20, "moyenne": 13, "petite": 6}  # -> max 20
POINTS_TIMELINE = {"urgent": 15, "court_terme": 11, "moyen_terme": 5, "non_precise": 0}  # -> max 15
POINTS_EMAIL = 5
POINTS_PHONE = 5  # contact -> max 10

HOT_THRESHOLD = 70
WARM_THRESHOLD = 40


def score_lead(info: LeadInfo) -> ScoreResult:
    score = 0
    reasons: list[str] = []

    if info.budget_tnd:
        for threshold, points in POINTS_BUDGET:
            if info.budget_tnd >= threshold:
                score += points
                reasons.append(f"+{points} budget annoncé ({info.budget_tnd:,.0f} TND)")
                break

    if info.need:
        score += POINTS_NEED
        reasons.append(f"+{POINTS_NEED} besoin précis : {info.need}")

    size = info.company_size
    if size:
        score += POINTS_SIZE[size]
        reasons.append(f"+{POINTS_SIZE[size]} entreprise {size} ({info.employees} personnes)")

    tl_points = POINTS_TIMELINE[info.timeline]
    if tl_points:
        score += tl_points
        reasons.append(f"+{tl_points} échéance : {info.timeline}")

    if info.email:
        score += POINTS_EMAIL
        reasons.append(f"+{POINTS_EMAIL} email fourni")
    if info.phone:
        score += POINTS_PHONE
        reasons.append(f"+{POINTS_PHONE} téléphone fourni")

    score = min(score, 100)
    if score >= HOT_THRESHOLD:
        category = "chaud"
    elif score >= WARM_THRESHOLD:
        category = "tiede"
    else:
        category = "froid"
    if not reasons:
        reasons.append("aucun signal d'intention détecté")
    return ScoreResult(score=score, category=category, reasons=reasons)
