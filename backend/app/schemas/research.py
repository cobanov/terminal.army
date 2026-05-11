from __future__ import annotations

from pydantic import BaseModel


class ResearchRead(BaseModel):
    tech_type: str
    level: int
    next_cost_metal: int
    next_cost_crystal: int
    next_cost_deuterium: int
    next_research_seconds: int
    prereq_met: bool
    prereq_missing: list[str]


class ResearchesResponse(BaseModel):
    user_id: int
    researches: list[ResearchRead]
