"""Onboarding quest endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.deps import CurrentUser, DBSession
from backend.app.services.quests import Quest, user_quest_status

router = APIRouter(tags=["quest"])


class QuestRead(BaseModel):
    id: str
    title: str
    hint: str


class QuestStatus(BaseModel):
    completed: list[QuestRead]
    current: QuestRead | None
    upcoming: list[QuestRead]
    total: int
    done_count: int


def _q(q: Quest) -> QuestRead:
    return QuestRead(id=q.id, title=q.title, hint=q.hint)


@router.get("/quests", response_model=QuestStatus)
async def get_quests(user: CurrentUser, db: DBSession) -> QuestStatus:
    status = await user_quest_status(db, user.id)
    return QuestStatus(
        completed=[_q(q) for q in status["completed"]],
        current=_q(status["current"]) if status["current"] else None,
        upcoming=[_q(q) for q in status.get("upcoming", [])],
        total=status["total"],
        done_count=status["done_count"],
    )
