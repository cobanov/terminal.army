"""Fleet endpoints: send / list active / reports."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select

from backend.app.deps import CurrentUser, DBSession
from backend.app.game.constants import ShipType
from backend.app.models.fleet import Fleet, FleetMission, FleetShip, FleetStatus
from backend.app.models.report import Report
from backend.app.rate_limit import limiter
from backend.app.services.fleet_service import send_fleet

router = APIRouter(tags=["fleets"])


class FleetSendRequest(BaseModel):
    origin_planet_id: int
    mission: str
    target_galaxy: int = Field(ge=1, le=9)
    target_system: int = Field(ge=1, le=499)
    target_position: int = Field(ge=1, le=15)
    ships: dict[str, int]  # ship_type -> count
    cargo_metal: int = Field(default=0, ge=0)
    cargo_crystal: int = Field(default=0, ge=0)
    cargo_deuterium: int = Field(default=0, ge=0)
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
@limiter.limit("30/minute")
async def send(
    request: Request, body: FleetSendRequest, user: CurrentUser, db: DBSession
) -> FleetRead:
    try:
        mission = FleetMission(body.mission)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"unknown mission: {body.mission} (use one of: {[m.value for m in FleetMission]})",
        ) from exc

    ships: dict[ShipType, int] = {}
    for k, v in body.ships.items():
        try:
            ships[ShipType(k)] = int(v)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"unknown ship type: {k}") from exc

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
    ship_rows = [
        FleetShipRead(ship_type=s.ship_type, count=s.count) for s in ships_res.scalars().all()
    ]

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
        ship_rows = [
            FleetShipRead(ship_type=s.ship_type, count=s.count) for s in ships_res.scalars().all()
        ]
        base = FleetRead.model_validate(f)
        out.append(FleetRead(**{**base.model_dump(), "ships": ship_rows}))
    return out


class IncomingFleet(BaseModel):
    """Hostile / external fleet inbound to one of my planets."""

    fleet_id: int
    mission: str
    sender_username: str
    target_planet_id: int
    target_galaxy: int
    target_system: int
    target_position: int
    arrival_at: datetime
    is_hostile: bool  # True for attack / espionage


@router.get("/fleets/incoming", response_model=list[IncomingFleet])
async def list_incoming(user: CurrentUser, db: DBSession) -> list[IncomingFleet]:
    """Fleets owned by OTHER players that target one of MY planets and
    haven't arrived yet. Used to surface attack/espionage warnings in
    the TUI right panel."""
    from backend.app.models.planet import Planet
    from backend.app.models.user import User

    my_planets_res = await db.execute(select(Planet).where(Planet.owner_user_id == user.id))
    my_planets = list(my_planets_res.scalars().all())
    if not my_planets:
        return []

    coord_to_planet = {(p.galaxy, p.system, p.position): p for p in my_planets}

    res = await db.execute(
        select(Fleet)
        .where(
            Fleet.owner_id != user.id,
            Fleet.status == FleetStatus.OUTBOUND.value,
        )
        .order_by(Fleet.arrival_at)
    )
    incoming: list[IncomingFleet] = []
    hostile_missions = {FleetMission.ATTACK.value, FleetMission.ESPIONAGE.value}
    for f in res.scalars().all():
        key = (f.target_galaxy, f.target_system, f.target_position)
        target_planet = coord_to_planet.get(key)
        if target_planet is None:
            continue
        sender_res = await db.execute(select(User).where(User.id == f.owner_id))
        sender = sender_res.scalar_one_or_none()
        incoming.append(
            IncomingFleet(
                fleet_id=f.id,
                mission=f.mission,
                sender_username=sender.username if sender else "?",
                target_planet_id=target_planet.id,
                target_galaxy=f.target_galaxy,
                target_system=f.target_system,
                target_position=f.target_position,
                arrival_at=f.arrival_at,
                is_hostile=f.mission in hostile_missions,
            )
        )
    return incoming


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
