#  Agent de qualification de leads CRM (LangGraph + FastAPI + React)

Un agent qui lit un **message client en texte libre**, en extrait les informations clés (LLM Groq ou règles), calcule un **score explicable**, rédige un **résumé commercial** et des **questions de relance**, puis attend la **validation d'un humain** avant d'écrire la fiche dans le CRM (SQLite).

> Projet de démonstration — toutes les données sont fictives. Cas d'usage : qualification de demandes entrantes (agence digitale, éditeur logiciel).

## Fonctionnement

```
message ─► extract ─► merge ─► check_fields ─┬─ (ni email ni téléphone) ─► request_contact ─► fin
                                             └─► score ─► summarize ─► human_review ⏸
                                                                          ├─ Valider ─► update_crm ─► fin
                                                                          └─ Rejeter ─► reject ─────► fin
```

| Étape | Rôle |
|---|---|
| `extract` | Extrait nom, entreprise, email, téléphone, besoin, budget (TND), échéance, effectif. **LLM Groq** (Llama 3.3 70B) si `GROQ_API_KEY` est défini, sinon **règles**. |
| `merge` | Si le lead existe déjà (même email / téléphone), fusionne avec la fiche pour scorer tout ce qu'on sait. |
| `check_fields` | Liste les infos manquantes et prépare une **question de relance** pour chacune. Sans contact : arrêt, on demande les coordonnées. |
| `score` / `summarize` | Score 0-100 avec raisons, résumé et action recommandée. |
| `human_review` | **`interrupt()` LangGraph** : le graphe s'arrête, son état est sauvegardé (checkpointer SQLite). |
| `update_crm` / `reject` | Écriture dans le CRM **uniquement après « Valider »**. Après « Rejeter », rien n'est écrit. |

### Barème du score (total 100)

| Critère | Points |
|---|---|
| Budget ≥ 20 000 / ≥ 5 000 / > 0 TND | 30 / 20 / 10 |
| Besoin précis | 25 |
| Taille de l'entreprise : grande (≥ 200) / moyenne (20-199) / petite (< 20) | 20 / 13 / 6 |
| Échéance : urgent / court terme / moyen terme | 15 / 11 / 5 |
| Contact : email + téléphone | 5 + 5 |

Catégories : **chaud** ≥ 70 · **tiède** ≥ 40 · **froid** < 40. Toutes les valeurs sont des constantes dans `lead_agent/scoring.py`.

## Extraction par LLM (Groq)

```bash
export GROQ_API_KEY=...      # clé gratuite : https://console.groq.com
```

- Le LLM doit répondre en **JSON strict** ; la réponse est validée par Pydantic (`LLMExtraction`) : valeurs hors format, JSON invalide ou erreur réseau ⇒ **repli automatique sur les règles**.
- L'email et le téléphone sont vérifiés par regex : le LLM ne peut pas les inventer.
- Modèle modifiable avec `LEAD_LLM_MODEL` (défaut : `llama-3.3-70b-versatile`).

## Démarrage rapide

### Avec Docker Compose

```bash
cp .env.example .env         # optionnel : y mettre GROQ_API_KEY
docker compose up --build
# Interface : http://localhost:8080      API / docs : http://localhost:8000/docs
```

### Sans Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn lead_agent.api:app --reload                 # API : http://127.0.0.1:8000/docs

cd frontend && npm install && npm run dev           # interface : http://localhost:5173
```

### En ligne de commande

```bash
python -m lead_agent.cli --demo                     # 6 messages d'exemple, validation automatique
python -m lead_agent.cli --message "Bonjour, je suis Sami Ben Ali, société Medtech, besoin d'un CRM, 25 000 DT, urgent. sami@medtech.tn"
python -m lead_agent.evaluate                       # évaluation sur 300 messages annotés
python -m pytest                                    # 33 tests
```

## API

| Route | Rôle |
|---|---|
| `POST /leads` | Analyse un message → proposition **en attente de validation** (`thread_id`, score, résumé, questions de relance). |
| `GET /reviews?status=en_attente\|approuve\|rejete` | Liste des propositions. |
| `POST /reviews/{thread_id}/approve` | Validation humaine → écriture dans le CRM. |
| `POST /reviews/{thread_id}/reject` | Rejet → rien n'est écrit. |
| `GET /leads` | Fiches du CRM (leads validés). |
| `GET /health` | État + mode d'extraction (`groq` ou `regles`). |

Une proposition déjà traitée renvoie `409` ; un identifiant inconnu renvoie `404`. Les pauses sont sauvegardées sur disque : une validation reste possible après un redémarrage du serveur.

## Interface React

Page unique (React + Vite) : zone de saisie du message, puis trois onglets — **À valider** (tableau avec score, contact, besoin, budget, résumé, questions de relance et boutons **Valider / Rejeter**), **CRM** et **Rejetés**.

## Données et évaluation

Les vrais messages clients sont confidentiels : le projet utilise des **données 100 % synthétiques** (`lead_agent/dataset.py`, graine fixe, reproductibles). Chaque message est construit à partir d'une vérité terrain connue, ce qui permet de mesurer l'extraction.

```bash
python -m lead_agent.dataset --n 300 --seed 42
python -m lead_agent.evaluate --errors 5
```

Résultats de l'extraction **par règles** sur 300 messages (`reports/evaluation.md`) :

| Champ | Présent dans | Rappel | Précision |
|---|---:|---:|---:|
| name | 259 | 94.2 % | 100.0 % |
| company | 197 | 85.8 % | 100.0 % |
| email | 231 | 100.0 % | 100.0 % |
| phone | 175 | 100.0 % | 100.0 % |
| need | 264 | 100.0 % | 100.0 % |
| budget_tnd | 175 | 92.6 % | 100.0 % |
| timeline | 222 | 95.9 % | 100.0 % |

- Routage (contact présent / absent) : **100 %**
- Catégorie de lead (chaud / tiède / froid) : **96.3 %**

### Limites connues

- Les règles ne détectent pas un nom en minuscules, un montant en lettres (« quinze mille dinars ») ni une échéance vague (« avant fin décembre ») : c'est là que le LLM apporte le plus.
- Le jeu synthétique ne contient pas l'effectif de l'entreprise : le score maximal y est donc 80/100 et la précision de catégorie (96.3 %) n'est pas comparable à celle de l'ancien barème.
- L'extraction par LLM est testée avec un **faux serveur Groq** (`tests/test_llm.py`) ; l'évaluation chiffrée du LLM sur les 300 messages reste à faire avec une vraie clé.
- Le jeu de test est synthétique et écrit par l'auteur : les scores montrent le comportement de l'agent sur ces cas, pas sur de vrais messages.

## Structure

```
lead_agent/
  models.py      # Pydantic : LeadInfo, LLMExtraction, ScoreResult
  extractor.py   # extraction Groq (JSON strict) + règles en repli
  scoring.py     # barème 30/25/20/15/10
  crm.py         # CRM SQLite + zone d'attente des validations
  graph.py       # graphe LangGraph (questions de relance, interrupt)
  api.py         # API FastAPI
  cli.py         # démo en ligne de commande
  dataset.py / evaluate.py
frontend/        # React + Vite (+ Dockerfile, nginx.conf)
tests/           # agent, scoring, LLM (mocké), API, jeu de données
Dockerfile · docker-compose.yml · .env.example
```

## Pistes d'amélioration

- Passer de SQLite à PostgreSQL (le plan initial le prévoit) ou à un vrai CRM (HubSpot, Odoo, Zoho).
- Envoyer réellement les questions de relance par email.
- Support de l'arabe / dialecte tunisien dans l'extraction.
- Comparer règles et LLM avec le même script d'évaluation.
