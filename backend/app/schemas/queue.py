from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QueueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planet_id: int
    queue_type: str
    item_key: str
    target_level: int
    cost_metal: int
    cost_crystal: int
    cost_deuterium: int
    started_at: datetime
    finished_at: datetime
    cancelled: bool
    applied: bool
