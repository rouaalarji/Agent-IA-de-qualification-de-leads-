"""Modèles de données (Pydantic) de l'agent de qualification de leads."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Timeline = Literal["urgent", "court_terme", "moyen_terme", "non_precise"]
Category = Literal["chaud", "tiede", "froid"]
CompanySize = Literal["petite", "moyenne", "grande"]


class LeadInfo(BaseModel):
    """Informations extraites d'un message client."""

    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    need: Optional[str] = None
    budget_tnd: Optional[float] = Field(default=None, ge=0)
    timeline: Timeline = "non_precise"
    employees: Optional[int] = Field(default=None, ge=1)
    source_message: str

    @property
    def has_contact(self) -> bool:
        return bool(self.email or self.phone)

    @property
    def company_size(self) -> Optional[CompanySize]:
        """Petite < 20 personnes, moyenne < 200, grande au-delà."""
        if not self.employees:
            return None
        if self.employees < 20:
            return "petite"
        if self.employees < 200:
            return "moyenne"
        return "grande"


class LLMExtraction(BaseModel):
    """Format JSON strict attendu du LLM (tout le reste est rejeté par Pydantic)."""

    model_config = {"extra": "ignore"}

    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    need: Optional[str] = None
    budget_tnd: Optional[float] = Field(default=None, ge=0)
    timeline: Timeline = "non_precise"
    employees: Optional[int] = Field(default=None, ge=1)


class ScoreResult(BaseModel):
    """Résultat du calcul de score (0-100) avec explications."""

    score: int = Field(ge=0, le=100)
    category: Category
    reasons: list[str]
