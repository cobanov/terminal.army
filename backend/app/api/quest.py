"""Onboarding quest endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.deps import CurrentUser, DBSession
from backend.app.services.quests import user_quest_status

router = APIRouter(tags=["quest"])


class QuestRead(BaseModel):
    id: str
    title: str
    hint: str


class QuestStatus(BaseModel):
    completed: list[QuestRead]
    current: QuestRead | None
    total: int
    done_count: int


@router.get("/quests", response_model=QuestStatus)
async def get_quests(user: CurrentUser, db: DBSession) -> QuestStatus:
    status = await user_quest_status(db, user.id)
    return QuestStatus(
        completed=[QuestRead(id=q.id, title=q.title, hint=q.hint) for q in status["completed"]],
        current=(
            QuestRead(
                id=status["current"].id,
                title=status["current"].title,
                hint=status["current"].hint,
            )
            if status["current"]
            else None
        ),
        total=status["total"],
        done_count=status["done_count"],
    )
