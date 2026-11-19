"""Générateur de messages clients synthétiques annotés (français, contexte tunisien).

Chaque message est produit à partir d'une "vérité terrain" (gold) connue, ce qui permet
de mesurer la qualité de l'extraction. Une partie des messages est volontairement
difficile (nom en signature, prénom en minuscules, budget écrit en lettres...).

    python -m lead_agent.dataset --n 300 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import unicodedata
from pathlib import Path

from .models import LeadInfo
from .scoring import score_lead

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic_leads.jsonl"

FIRST = ["Sami", "Amira", "Karim", "Yasmine", "Mohamed", "Ines", "Walid", "Salma", "Anis", "Rania",
         "Hatem", "Nour", "Slim", "Mariem", "Fares", "Syrine", "Oussama", "Chaima", "Bilel", "Emna"]
LAST = ["Ben Ali", "Trabelsi", "Jlassi", "Gharbi", "Mansouri", "Ben Salah", "Bouazizi", "Chaabane",
        "Hamdi", "Maatoug", "Ferchichi", "Zouari", "Khelifi", "Ayari", "Dridi"]
COMPANY_A = ["Medtech", "Délice", "Sahel", "Carthage", "Atlas", "Djerba", "Olivia", "Techno",
             "Nova", "Horizon", "Zitouna", "Médina"]
COMPANY_B = ["Sfax", "Gourmet", "Logistique", "Conseil", "Services", "Digital", "Textile",
             "Agro", "Pharma", "Immobilier"]
PUBLIC_DOMAINS = ["gmail.com", "outlook.com", "yahoo.fr"]

NEEDS = {
    "CRM": ["un CRM sur mesure", "une solution CRM"],
    "ERP": ["un ERP pour la gestion de notre stock"],
    "Site web": ["un site web", "un site vitrine"],
    "E-commerce": ["un site e-commerce", "une boutique en ligne"],
    "Application mobile": ["une application mobile", "une appli mobile"],
    "Chatbot / agent IA": ["un chatbot pour le support client", "un agent IA"],
    "Automatisation": ["l'automatisation de la facturation", "l'automatisation de nos processus internes"],
    "Logiciel sur mesure": ["un logiciel de gestion", "une plateforme de réservation"],
}
BUDGETS = [1500, 3000, 5000, 8000, 12000, 15000, 25000, 40000]
BUDGET_WORDS = {5000: "cinq mille dinars", 15000: "quinze mille dinars"}  # cas difficiles

TIMELINES = {
    "urgent": ["C'est urgent.", "Nous en avons besoin dès que possible.", "Idéalement cette semaine.",
               "Il nous le faut au plus vite."],
    "court_terme": ["Nous visons d'ici 1 mois.", "Ce serait pour ce mois.", "Pour les prochaines semaines."],
    "moyen_terme": ["Plutôt dans 3 mois.", "Pour l'année prochaine.", "Au prochain trimestre."],
}
HARD_TIMELINE = "Avant la fin du mois de décembre."  # gold = court_terme, non détecté par les règles


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return "".join(c for c in text.lower() if c.isalnum())


def _format_budget(rng: random.Random, value: int) -> str:
    options = [
        f"{value:,}".replace(",", " ") + " DT",
        f"{value} TND",
        f"{value:,}".replace(",", ".") + " DT",
        f"{value} dinars",
    ]
    if value % 1000 == 0:
        options.append(f"{value // 1000}k DT")
    return rng.choice(options)


def _format_phone(rng: random.Random, digits: str) -> str:
    a, b, c = digits[:2], digits[2:5], digits[5:]
    return rng.choice([f"{a} {b} {c}", digits, f"+216 {a} {b} {c}", f"{a}.{b}.{c}", f"{a}-{b}-{c}"])


def make_record(rng: random.Random, idx: int) -> dict:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    name = f"{first} {last}"
    company = f"{rng.choice(COMPANY_A)} {rng.choice(COMPANY_B)}"

    has_name = rng.random() < 0.85
    has_company = rng.random() < 0.70
    needs = rng.sample(list(NEEDS), k=1 if rng.random() < 0.8 else 2) if rng.random() < 0.90 else []
    budget = rng.choice(BUDGETS) if rng.random() < 0.60 else None
    timeline = rng.choices(["urgent", "court_terme", "moyen_terme", "non_precise"], weights=[25, 25, 20, 30])[0]
    contact = rng.choices(["both", "email", "phone", "none"], weights=[45, 30, 15, 10])[0]

    domain = rng.choice(PUBLIC_DOMAINS + [f"{_slug(company)}.tn"])
    email = f"{_slug(first)}.{_slug(last)}@{domain}" if contact in ("both", "email") else None
    phone_digits = None
    if contact in ("both", "phone"):
        phone_digits = f"{rng.choice([2, 4, 5, 9])}{rng.randint(0, 9)}{rng.randint(100000, 999999)}"

    parts: list[str] = []
    signature = ""
    if has_name:
        style = rng.choices(["easy", "signature", "lower"], weights=[75, 18, 7])[0]
        if style == "easy":
            parts.append(rng.choice([
                f"Bonjour, je m'appelle {name}.", f"Bonjour, je suis {name}.", f"Salut, moi c'est {name}.",
            ]))
        elif style == "lower":
            parts.append(f"bonjour, je suis {name.lower()}.")
        else:
            parts.append("Bonjour.")
            signature = f"Cordialement, {name}."
    else:
        parts.append("Bonjour.")

    if has_company:
        if rng.random() < 0.85:
            parts.append(rng.choice([
                f"Nous sommes la société {company}.", f"Je travaille chez {company}.",
                f"Notre entreprise {company} cherche à se développer.",
            ]))
        else:
            parts.append(rng.choice([f"Nous dirigeons {company}.", f"C'est pour {company}."]))

    if needs:
        phrases = " et ".join(rng.choice(NEEDS[n]) for n in needs)
        parts.append(rng.choice([f"Nous cherchons {phrases}.", f"Notre besoin : {phrases}.",
                                 f"Nous voulons mettre en place {phrases}."]))
    else:
        parts.append("Pouvez-vous nous donner plus d'informations sur vos services ?")

    if budget:
        if budget in BUDGET_WORDS and rng.random() < 0.4:
            amount = BUDGET_WORDS[budget]
        else:
            amount = _format_budget(rng, budget)
        parts.append(rng.choice([f"Notre budget est de {amount}.", f"Budget : environ {amount}."]))

    if timeline == "court_terme" and rng.random() < 0.15:
        parts.append(HARD_TIMELINE)
    elif timeline != "non_precise":
        parts.append(rng.choice(TIMELINES[timeline]))

    if email and phone_digits:
        parts.append(f"Vous pouvez me joindre à {email} ou au {_format_phone(rng, phone_digits)}.")
    elif email:
        parts.append(f"Mon email : {email}.")
    elif phone_digits:
        parts.append(f"Mon numéro : {_format_phone(rng, phone_digits)}.")
    if signature:
        parts.append(signature)

    gold = {
        "name": name if has_name else None,
        "company": company if has_company else None,
        "email": email,
        "phone": phone_digits,
        "need": needs or None,
        "budget_tnd": float(budget) if budget else None,
        "timeline": timeline,
    }
    gold_info = LeadInfo(
        **{**gold, "need": ", ".join(needs) if needs else None}, source_message=""
    )
    return {
        "id": idx,
        "message": " ".join(parts),
        "gold": gold,
        "gold_category": score_lead(gold_info).category,
        "gold_has_contact": gold_info.has_contact,
    }


def generate(n: int = 300, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    return [make_record(rng, i + 1) for i in range(n)]


def save(records: list[dict], path: Path = DEFAULT_OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load(path: Path = DEFAULT_OUT) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère un jeu de messages clients synthétiques annotés")
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    records = generate(args.n, args.seed)
    save(records, args.out)
    print(f"{len(records)} messages écrits dans {args.out}")


if __name__ == "__main__":
    main()
