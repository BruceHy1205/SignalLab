from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from signal_api.notify_util import get_notify

router = APIRouter()


class TestNotifyReq(BaseModel):
    title: str = "signal 测试通知"
    body: str = Field(default="这是一条测试消息")


@router.post("/test")
def test_notify(req: TestNotifyReq) -> dict:
    return get_notify().send(req.title, req.body)
