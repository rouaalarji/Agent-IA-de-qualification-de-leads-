"""Extraction des informations d'un message client.

Deux modes :
- LLM Groq (Llama 3.3 70B) : activé si GROQ_API_KEY est défini. Le LLM doit répondre en JSON
  strict, validé par Pydantic (LLMExtraction). Toute erreur (réseau, JSON invalide, valeurs
  hors format) déclenche un repli automatique sur les règles ;
- règles (regex + mots-clés) : par défaut, sans clé API, déterministe et testable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx
from pydantic import ValidationError

from .models import LeadInfo, LLMExtraction

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?216[\s.-]?)?(\d{2}[\s.-]?\d{3}[\s.-]?\d{3})(?!\d)")
NAME_RE = re.compile(
    r"(?i:je m'appelle|je me présente|moi c'est|je suis)\s+"
    r"([A-ZÀ-Ý][\wÀ-ÿ'-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'-]+){0,2})"
)
SIGNATURE_RE = re.compile(
    r"(?i:cordialement|bien cordialement|bien à vous|salutations|merci d'avance)[,\s]+"
    r"([A-ZÀ-Ý][\wÀ-ÿ'-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'-]+){0,2})"
)
COMPANY_RE = re.compile(
    r"(?i:société|entreprise|chez|de la société|pour la société)\s+"
    r"([A-ZÀ-Ý][\wÀ-ÿ&-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ&-]+){0,2})"
)
EMPLOYEES_RE = re.compile(
    r"(\d[\d\s]*)\s*(?:employés|employes|salariés|salaries|collaborateurs|personnes|ingénieurs|ingenieurs)",
    re.IGNORECASE,
)
BUDGET_RE = re.compile(
    r"(\d[\d\s.,]*)\s*(k|mille)?\s*(?:dt|tnd|dinars?)\b", re.IGNORECASE
)

NEED_KEYWORDS = {
    "CRM": ["crm"],
    "ERP": ["erp"],
    "Site web": ["site web", "site vitrine", "site internet"],
    "E-commerce": ["e-commerce", "boutique en ligne", "site marchand"],
    "Application mobile": ["application mobile", "appli mobile", "app mobile"],
    "Chatbot / agent IA": ["chatbot", "agent ia", "assistant virtuel", "intelligence artificielle"],
    "Automatisation": ["automatisation", "automatiser", "workflow"],
    "Logiciel sur mesure": ["logiciel", "application web", "plateforme"],
}

URGENT_WORDS = ["urgent", "au plus vite", "dès que possible", "des que possible", "cette semaine", "demain", "immédiatement"]
SHORT_WORDS = ["ce mois", "d'ici 1 mois", "dans 2 semaines", "dans 3 semaines", "prochaines semaines", "dans un mois"]
MEDIUM_WORDS = ["trimestre", "dans 2 mois", "dans 3 mois", "dans 6 mois", "l'année prochaine", "prochain semestre"]


def _parse_budget(text: str) -> Optional[float]:
    match = BUDGET_RE.search(text)
    if not match:
        return None
    raw = re.sub(r"[\s.]", "", match.group(1)).replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if match.group(2):
        value *= 1000
    return value


def _parse_timeline(lower: str) -> str:
    if any(w in lower for w in URGENT_WORDS):
        return "urgent"
    if any(w in lower for w in SHORT_WORDS):
        return "court_terme"
    if any(w in lower for w in MEDIUM_WORDS):
        return "moyen_terme"
    return "non_precise"


def _parse_need(lower: str) -> Optional[str]:
    found = [label for label, kws in NEED_KEYWORDS.items() if any(k in lower for k in kws)]
    return ", ".join(found) if found else None


def _parse_employees(text: str) -> Optional[int]:
    match = EMPLOYEES_RE.search(text)
    if not match:
        return None
    value = int(re.sub(r"\s", "", match.group(1)))
    return value if value >= 1 else None


def extract_with_rules(message: str) -> LeadInfo:
    lower = message.lower()
    email = EMAIL_RE.search(message)
    phone = PHONE_RE.search(message)
    name = NAME_RE.search(message) or SIGNATURE_RE.search(message)
    company = COMPANY_RE.search(message)
    return LeadInfo(
        name=name.group(1).strip() if name else None,
        company=company.group(1).strip() if company else None,
        email=email.group(0).lower() if email else None,
        phone=re.sub(r"[\s.-]", "", phone.group(1)) if phone else None,
        need=_parse_need(lower),
        budget_tnd=_parse_budget(message),
        timeline=_parse_timeline(lower),
        employees=_parse_employees(message),
        source_message=message,
    )


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Tu es un extracteur d'informations pour un CRM. Réponds UNIQUEMENT avec un objet JSON \
ayant exactement ces clés :
- name : nom de la personne (string ou null)
- company : nom de l'entreprise (string ou null)
- email : adresse email (string ou null)
- phone : téléphone, chiffres seulement (string ou null)
- need : besoin du client en quelques mots (string ou null)
- budget_tnd : budget en dinars tunisiens, nombre (ex. 15000) ou null ; convertis « 15k » et « quinze mille »
- timeline : "urgent" | "court_terme" (moins de 2 mois) | "moyen_terme" (2 mois ou plus) | "non_precise"
- employees : nombre de personnes dans l'entreprise (entier ou null)
N'invente JAMAIS une valeur absente du message : utilise null. Pas de texte autour du JSON."""


def extract_with_llm(message: str, client: Optional[httpx.Client] = None) -> LeadInfo:
    """Extraction via l'API Groq (Llama 3.3 70B). Lève une exception si la réponse est invalide."""
    api_key = os.environ["GROQ_API_KEY"]
    payload = {
        "model": os.getenv("LEAD_LLM_MODEL", GROQ_MODEL),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
    }
    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.post(GROQ_URL, json=payload, headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    finally:
        if owns_client:
            client.close()
    # Validation stricte : JSON invalide ou valeurs hors format => exception => repli sur les règles.
    data = LLMExtraction.model_validate(json.loads(content))
    info = LeadInfo(**data.model_dump(), source_message=message)
    # Filet de sécurité : email / téléphone se vérifient mieux par regex que par LLM.
    rules = extract_with_rules(message)
    return info.model_copy(update={
        "email": rules.email or (info.email if info.email and EMAIL_RE.fullmatch(info.email) else None),
        "phone": rules.phone or info.phone,
    })


def extract_lead(message: str) -> LeadInfo:
    """Point d'entrée : Groq si GROQ_API_KEY est défini, sinon (ou en cas d'erreur) les règles."""
    if os.getenv("GROQ_API_KEY"):
        try:
            return extract_with_llm(message)
        except (httpx.HTTPError, KeyError, IndexError, ValueError, ValidationError) as exc:
            logger.warning("Extraction LLM échouée (%s), repli sur les règles", exc)
    return extract_with_rules(message)
