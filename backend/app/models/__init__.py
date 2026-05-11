"""ORM model imports for Alembic autogenerate and Base.metadata.create_all."""

from backend.app.models.building import Building
from backend.app.models.device_session import DeviceSession
from backend.app.models.fleet import Fleet, FleetMission, FleetShip, FleetStatus
from backend.app.models.message import Message
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue, QueueType
from backend.app.models.report import Report, ReportType
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense, PlanetShip
from backend.app.models.universe import Universe
from backend.app.models.user import User

all_models = (
    User, Universe, Planet, Building, Research, BuildQueue,
    Message, DeviceSession, PlanetShip, PlanetDefense,
    Fleet, FleetShip, Report,
)

__all__ = [
    "Building",
    "BuildQueue",
    "DeviceSession",
    "Fleet",
    "FleetMission",
    "FleetShip",
    "FleetStatus",
    "Message",
    "Planet",
    "PlanetDefense",
    "PlanetShip",
    "QueueType",
    "Report",
    "ReportType",
    "Research",
    "Universe",
    "User",
    "all_models",
]
