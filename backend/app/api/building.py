from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.deps import CurrentUser, DBSession
from backend.app.game.constants import BuildingType
from backend.app.game.formulas import build_time_seconds, building_cost
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue
from backend.app.models.universe import Universe
from backend.app.schemas.building import BuildingRead, BuildingsResponse, UpgradeResponse
from backend.app.schemas.queue import QueueItemRead
from backend.app.services.build_service import cancel_queue_item, queue_building_upgrade

router = APIRouter(tags=["buildings"])


@router.get("/planets/{planet_id}/buildings", response_model=BuildingsResponse)
async def list_buildings(planet_id: int, user: CurrentUser, db: DBSession) -> BuildingsResponse:
    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planet not found")

    universe = await db.get(Universe, planet.universe_id)
    speed = float(universe.speed_economy) if universe else 1.0

    result = await db.execute(select(Building).where(Building.planet_id == planet_id))
    rows = {b.building_type: b.level for b in result.scalars().all()}

    robotics = rows.get(BuildingType.ROBOTICS_FACTORY.value, 0)
    nanite = rows.get(BuildingType.NANITE_FACTORY.value, 0)

    out: list[BuildingRead] = []
    for bt in BuildingType:
        level = rows.get(bt.value, 0)
        target = level + 1
        cm, cc, cd = building_cost(bt, target)
        seconds = build_time_seconds(cm, cc, robotics, nanite, speed)
        out.append(
            BuildingRead(
                building_type=bt.value,
                level=level,
                next_cost_metal=cm,
                next_cost_crystal=cc,
                next_cost_deuterium=cd,
                next_build_seconds=seconds,
            )
        )
    return BuildingsResponse(planet_id=planet_id, buildings=out)


@router.post(
    "/planets/{planet_id}/buildings/{building_type}/upgrade",
    response_model=UpgradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upgrade_building(
    planet_id: int,
    building_type: str,
    user: CurrentUser,
    db: DBSession,
) -> UpgradeResponse:
    try:
        bt = BuildingType(building_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown building type: {exc}"
        ) from exc

    queue = await queue_building_upgrade(db, planet_id, user.id, bt)
    return UpgradeResponse(
        queue_id=queue.id,
        item_key=queue.item_key,
        target_level=queue.target_level,
        finished_at=queue.finished_at.isoformat(),
        cost_metal=queue.cost_metal,
        cost_crystal=queue.cost_crystal,
        cost_deuterium=queue.cost_deuterium,
    )


@router.get("/planets/{planet_id}/queue", response_model=list[QueueItemRead])
async def get_queue(planet_id: int, user: CurrentUser, db: DBSession) -> list[QueueItemRead]:
    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planet not found")
    result = await db.execute(
        select(BuildQueue)
        .where(
            BuildQueue.planet_id == planet_id,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
        .order_by(BuildQueue.finished_at)
    )
    return [QueueItemRead.model_validate(q) for q in result.scalars().all()]


@router.delete("/queue/{queue_id}", response_model=QueueItemRead)
async def cancel_queue(queue_id: int, user: CurrentUser, db: DBSession) -> QueueItemRead:
    queue = await cancel_queue_item(db, queue_id, user.id)
    return QueueItemRead.model_validate(queue)
