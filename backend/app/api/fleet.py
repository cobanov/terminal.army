"""Fleet endpoints: send / list active / reports."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select

from backend.app.deps import CurrentUser, DBSession
from backend.app.game.constants import ShipType
from backend.app.models.fleet import Fleet, FleetMission, FleetShip, FleetStatus
from backend.app.models.report import Report
from backend.app.services.fleet_service import send_fleet

router = APIRouter(tags=["fleets"])


class FleetSendRequest(BaseModel):
    origin_planet_id: int
    mission: str
    target_galaxy: int = Field(ge=1, le=9)
    target_system: int = Field(ge=1, le=499)
    target_position: int = Field(ge=1, le=15)
    ships: dict[str, int]  # ship_type -> count
    cargo_metal: int = 0
    cargo_crystal: int = 0
    cargo_deuterium: int = 0
    speed_percent: int = Field(default=100, ge=10, le=100)


class FleetShipRead(BaseModel):
    ship_type: str
    count: int


class FleetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mission: str
    status: str
    origin_planet_id: int
    target_galaxy: int
    target_system: int
    target_position: int
    departure_at: datetime
    arrival_at: datetime
    return_at: datetime | None
    cargo_metal: int
    cargo_crystal: int
    cargo_deuterium: int
    fuel_cost: int
    ships: list[FleetShipRead] = []


@router.post("/fleets/send", response_model=FleetRead, status_code=status.HTTP_201_CREATED)
async def send(body: FleetSendRequest, user: CurrentUser, db: DBSession) -> FleetRead:
    try:
        mission = FleetMission(body.mission)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"unknown mission: {body.mission} (use one of: {[m.value for m in FleetMission]})",
        )

    ships: dict[ShipType, int] = {}
    for k, v in body.ships.items():
        try:
            ships[ShipType(k)] = int(v)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"unknown ship type: {k}")

    fleet = await send_fleet(
        db=db,
        user_id=user.id,
        origin_planet_id=body.origin_planet_id,
        mission=mission,
        target_galaxy=body.target_galaxy,
        target_system=body.target_system,
        target_position=body.target_position,
        ships=ships,
        cargo_metal=body.cargo_metal,
        cargo_crystal=body.cargo_crystal,
        cargo_deuterium=body.cargo_deuterium,
        speed_percent=body.speed_percent,
    )

    # Load ships
    ships_res = await db.execute(select(FleetShip).where(FleetShip.fleet_id == fleet.id))
    ship_rows = [FleetShipRead(ship_type=s.ship_type, count=s.count) for s in ships_res.scalars().all()]

    base = FleetRead.model_validate(fleet)
    return FleetRead(**{**base.model_dump(), "ships": ship_rows})


@router.get("/fleets", response_model=list[FleetRead])
async def list_fleets(user: CurrentUser, db: DBSession) -> list[FleetRead]:
    res = await db.execute(
        select(Fleet)
        .where(
            Fleet.owner_id == user.id,
            Fleet.status.in_([FleetStatus.OUTBOUND.value, FleetStatus.RETURNING.value]),
        )
        .order_by(Fleet.arrival_at)
    )
    fleets = res.scalars().all()
    out: list[FleetRead] = []
    for f in fleets:
        ships_res = await db.execute(select(FleetShip).where(FleetShip.fleet_id == f.id))
        ship_rows = [FleetShipRead(ship_type=s.ship_type, count=s.count) for s in ships_res.scalars().all()]
        base = FleetRead.model_validate(f)
        out.append(FleetRead(**{**base.model_dump(), "ships": ship_rows}))
    return out


# ----- Reports --------------------------------------------------------------
class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_type: str
    title: str
    body: str
    target_galaxy: int
    target_system: int
    target_position: int
    created_at: datetime


@router.get("/reports", response_model=list[ReportRead])
async def list_reports(
    user: CurrentUser,
    db: DBSession,
    limit: int = 30,
) -> list[ReportRead]:
    res = await db.execute(
        select(Report)
        .where(Report.owner_id == user.id)
        .order_by(desc(Report.created_at))
        .limit(limit)
    )
    return [ReportRead.model_validate(r) for r in res.scalars().all()]


@router.get("/reports/{report_id}", response_model=ReportRead)
async def get_report(report_id: int, user: CurrentUser, db: DBSession) -> ReportRead:
    rep = await db.get(Report, report_id)
    if rep is None or rep.owner_id != user.id:
        raise HTTPException(status_code=404, detail="report not found")
    return ReportRead.model_validate(rep)
