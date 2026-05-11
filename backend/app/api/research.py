from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.app.deps import CurrentUser, DBSession
from backend.app.game.constants import TechType
from backend.app.game.formulas import research_cost, research_time_seconds
from backend.app.game.tech_tree import check_research_prerequisites
from backend.app.schemas.building import UpgradeResponse
from backend.app.schemas.research import ResearchesResponse, ResearchRead
from backend.app.services.research_service import (
    get_max_research_lab_level,
    get_user_tech_levels,
    queue_research,
)

router = APIRouter(tags=["research"])


@router.get("/researches", response_model=ResearchesResponse)
async def list_researches(user: CurrentUser, db: DBSession) -> ResearchesResponse:
    tech_levels = await get_user_tech_levels(db, user.id)
    max_lab = await get_max_research_lab_level(db, user.id)

    out: list[ResearchRead] = []
    for tt in TechType:
        level = tech_levels.get(tt, 0)
        target = level + 1
        cm, cc, cd = research_cost(tt, target)
        seconds = research_time_seconds(cm, cc, max_lab, 1.0)
        ok, missing = check_research_prerequisites(tt, max_lab, tech_levels)
        out.append(
            ResearchRead(
                tech_type=tt.value,
                level=level,
                next_cost_metal=cm,
                next_cost_crystal=cc,
                next_cost_deuterium=cd,
                next_research_seconds=seconds,
                prereq_met=ok,
                prereq_missing=missing,
            )
        )
    return ResearchesResponse(user_id=user.id, researches=out)


@router.post(
    "/researches/{tech_type}/upgrade",
    response_model=UpgradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upgrade_research(
    tech_type: str,
    planet_id: int,
    user: CurrentUser,
    db: DBSession,
) -> UpgradeResponse:
    try:
        tt = TechType(tech_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown tech: {exc}"
        ) from exc

    queue = await queue_research(db, user.id, planet_id, tt)
    return UpgradeResponse(
        queue_id=queue.id,
        item_key=queue.item_key,
        target_level=queue.target_level,
        finished_at=queue.finished_at.isoformat(),
        cost_metal=queue.cost_metal,
        cost_crystal=queue.cost_crystal,
        cost_deuterium=queue.cost_deuterium,
    )
